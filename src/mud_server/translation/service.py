"""OOC→IC translation service.

``OOCToICTranslationService`` is the single public entry-point for the
translation layer.  It orchestrates ``CharacterProfileBuilder``,
``OllamaRenderer``, and ``OutputValidator`` to produce in-character
dialogue from a raw player message.

Caller contract
---------------
``translate()`` always returns either:

- A non-empty IC string on success.
- ``None`` on any failure (missing profile, Ollama error, validation
  failure).

The caller (``GameEngine.chat/yell/whisper``) treats ``None`` as a signal
to use the original OOC message.  This is the graceful-degradation
guarantee: the layer never breaks the game.

Profile summary injection
--------------------------
Each world's ``ic_prompt.txt`` template uses a single ``{{profile_summary}}``
placeholder to embed the character's current axis state as a formatted block.
Before ``_render_system_prompt`` substitutes placeholders, ``translate()``
calls :func:`_build_profile_summary` to produce this block and injects it
into the profile dict under the key ``profile_summary``.  Without this step,
``{{profile_summary}}`` would reach the LLM as a literal unresolved string
and the model would have no character context.

Ledger integration
------------------
Every ``translate()`` call — success or failure — emits a
``chat.translation`` event to the world's JSONL ledger via
:func:`~mud_server.ledger.append_event`.

Events record:

- ``status``:          ``"success"`` | ``"fallback.api_error"``
                       | ``"fallback.validation_failed"``
- ``character_name``:  the character whose voice was translated
- ``channel``:         ``"say"`` | ``"yell"`` | ``"whisper"``
- ``ooc_input``:       the raw OOC message from the player
- ``ic_output``:       the final IC text, or ``null`` on fallback
- ``axis_snapshot``:   ``{axis_name: {score, label}}`` for every axis
                       present in the character's profile at translation
                       time

A ledger write failure is **never fatal** — the game interaction
completes and only the audit record is lost.  See
``TODO(ledger-hardening)`` comments in :func:`_emit_translation_event`.

The event is **not** emitted when the character profile cannot be
resolved (``profile is None``) — there is no character data to record.

IPC hash and deterministic mode
---------------------------------
``translate()`` accepts an optional ``ipc_hash: str | None`` parameter.
The axis engine (``core/engine.py``) computes this hash via
``AxisEngine.resolve_chat_interaction()`` and passes it here.

When ``ipc_hash`` is provided and ``config.deterministic`` is ``True``:

1. ``ipc_hash[:16]`` is converted to an integer seed.
2. ``self._renderer.set_deterministic(seed_int)`` is called, clamping
   temperature to 0.0 and forwarding the seed to Ollama.
3. Identical game state + identical OOC input → identical IC output
   (subject to Ollama model determinism at seed=constant, temp=0.0).

When ``ipc_hash`` is ``None`` (solo-room interactions, axis resolution
disabled, or axis engine failure), deterministic mode is silently skipped
and the renderer uses the configured temperature.

Pre-axis-engine era
-------------------
Events emitted before the axis engine was integrated carry
``meta: {"phase": "pre_axis_engine"}`` to distinguish them from
post-integration events during ledger replay or analysis.
Post-integration events with a real ``ipc_hash`` carry ``meta: {}``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mud_server.ledger import append_event as _ledger_append
from mud_server.translation.config import TranslationLayerConfig
from mud_server.translation.profile_builder import CharacterProfileBuilder
from mud_server.translation.renderer import OllamaRenderer
from mud_server.translation.validator import OutputValidator

logger = logging.getLogger(__name__)


@dataclass
class LabTranslateResult:
    """Result returned by ``OOCToICTranslationService.translate_with_axes``.

    Carries the full research context the Axis Descriptor Lab needs to
    display results: the IC text, outcome status, the profile_summary block
    as the server formatted it, and the fully-rendered system prompt that
    was actually sent to Ollama.

    Attributes:
        ic_text:        Validated IC dialogue on success, ``None`` on any
                        fallback path.
        status:         Outcome string — ``"success"``,
                        ``"fallback.api_error"``, or
                        ``"fallback.validation_failed"``.
        profile_summary: The ``{{profile_summary}}`` block as formatted by
                        the server (canonical format).
        rendered_prompt: The fully-rendered system prompt sent to Ollama,
                        with all placeholders resolved.
    """

    ic_text: str | None
    status: str
    profile_summary: str
    rendered_prompt: str


# ── Module-level helpers ──────────────────────────────────────────────────────


def _build_profile_summary(profile: dict) -> str:
    """Format a character's axis state into a human-readable summary block.

    Scans the profile dict for ``{axis_name}_label`` and
    ``{axis_name}_score`` key pairs (in insertion order, which matches the
    ``active_axes`` ordering from the world config) and builds a multi-line
    text block suitable for injection as the ``{{profile_summary}}``
    placeholder in a system prompt template.

    The character name is always included as the first line.  Axis scores
    are formatted to two decimal places so the LLM receives clean, readable
    values rather than floating-point noise (``0.07`` rather than
    ``0.06875230399999996``).  Axis names are title-cased with underscores
    replaced by spaces (``facial_signal`` → ``Facial Signal``), which
    reads more naturally in a prompt block.

    The ``channel`` key (injected into the profile dict by ``translate()``
    before calling this function) is intentionally excluded from the
    summary.  It is handled by the separate ``{{channel}}`` placeholder
    in the template.

    Insertion-order guarantee:
        ``CharacterProfileBuilder.build()`` iterates ``active_axes`` in
        world-configured order and inserts keys in that order.  Python 3.7+
        dicts preserve insertion order, so the summary axes appear in the
        same sequence as ``active_axes`` without any additional sorting.

    Args:
        profile: Flat profile dict from ``CharacterProfileBuilder.build()``,
                 after ``channel`` has been injected by ``translate()``.
                 Keys with ``_label`` / ``_score`` suffixes are treated as
                 axis data; all other keys are silently ignored.

    Returns:
        Multi-line string suitable for use as the ``{{profile_summary}}``
        placeholder value.  A profile with no axis data produces a
        single-line string containing only the character name.

    Example::

        profile = {
            "character_name": "Ddishfew Withnop",
            "channel": "say",
            "demeanor_label": "timid",
            "demeanor_score": 0.069,
            "health_label": "scarred",
            "health_score": 0.655,
        }
        _build_profile_summary(profile)
        # →
        #   Character: Ddishfew Withnop
        #   Demeanor: timid (0.07)
        #   Health: scarred (0.65)
    """
    # Start with the character name line — always present regardless of
    # whether any axis data exists.
    lines: list[str] = [f"  Character: {profile.get('character_name', 'unknown')}"]

    # Walk the profile dict in insertion order to collect axis names.
    # We look for _label keys as the canonical presence signal (every axis
    # built by CharacterProfileBuilder has both _label and _score).
    # Using a seen set prevents duplicate lines if the dict ever has
    # unexpected duplicate axis entries.
    seen_axes: set[str] = set()
    for key in profile:
        if not key.endswith("_label"):
            # Skip non-axis keys (character_name, channel, profile_summary
            # itself if re-entrant, etc.).
            continue

        axis_name = key[: -len("_label")]

        if axis_name in seen_axes:
            # Guard against the same axis appearing twice — should not
            # happen with CharacterProfileBuilder, but defensive is correct.
            continue
        seen_axes.add(axis_name)

        label = profile.get(f"{axis_name}_label", "unknown")
        score = float(profile.get(f"{axis_name}_score", 0.0))

        # Convert snake_case axis names to Title Case words for prompt
        # readability.  "facial_signal" → "Facial Signal" reads naturally
        # in a character sheet block.  The LLM does not need to know the
        # internal axis key name.
        display_name = axis_name.replace("_", " ").title()

        # Two decimal places: "0.07" conveys axis magnitude clearly without
        # the floating-point noise that accumulates after repeated axis
        # engine delta applications (e.g. "0.06875230399999996").
        lines.append(f"  {display_name}: {label} ({score:.2f})")

    return "\n".join(lines)


def _extract_snapshot(profile: dict) -> dict:
    """Extract axis score/label pairs from a character profile dict.

    Scans the profile for keys matching the patterns ``{axis_name}_score``
    and ``{axis_name}_label`` and groups them into a nested dict::

        {axis_name: {"score": float, "label": str}, ...}

    This shape is stored in ``data.axis_snapshot`` in every
    ``chat.translation`` ledger event so that analysts can reconstruct
    the character's mechanical state at the exact moment of translation —
    before any axis mutations are applied by the axis engine.

    Keys that do not follow the ``_score`` / ``_label`` suffix convention
    (e.g. ``character_name``, ``channel``, ``profile_summary``) are
    silently ignored.

    Args:
        profile: Flat dict from
                 :class:`~mud_server.translation.profile_builder.CharacterProfileBuilder`.
                 Keys with ``_score`` suffix hold ``float`` values; keys
                 with ``_label`` suffix hold ``str`` values.

    Returns:
        Nested snapshot dict.  Empty dict if the profile contains no
        ``_score`` / ``_label`` keys.

    Example::

        profile = {
            "character_name": "Mira",
            "channel": "say",
            "demeanor_score": 0.87,
            "demeanor_label": "proud",
            "health_score": 0.72,
            "health_label": "scarred",
        }
        _extract_snapshot(profile)
        # → {"demeanor": {"score": 0.87, "label": "proud"},
        #    "health":   {"score": 0.72, "label": "scarred"}}
    """
    snapshot: dict = {}
    for key, value in profile.items():
        if key.endswith("_score"):
            # Strip the "_score" suffix to obtain the axis name.
            # "demeanor_score" → axis "demeanor", field "score".
            axis_name = key[: -len("_score")]
            snapshot.setdefault(axis_name, {})["score"] = value
        elif key.endswith("_label"):
            # Strip the "_label" suffix to obtain the axis name.
            # "demeanor_label" → axis "demeanor", field "label".
            axis_name = key[: -len("_label")]
            snapshot.setdefault(axis_name, {})["label"] = value
    return snapshot


def _emit_translation_event(
    append_fn: Callable[..., str],
    *,
    world_id: str,
    status: str,
    character_name: str,
    channel: str,
    ooc_message: str,
    ic_output: str | None,
    profile: dict,
    ipc_hash: str | None,
) -> None:
    """Emit a ``chat.translation`` event to the world ledger.

    This is a fire-and-forget helper — it **never raises**.  If the
    ledger write fails (disk full, permissions, etc.) the failure is
    logged at WARNING level and the game interaction continues unaffected.

    This is an explicit PoC trade-off: durability of the audit record is
    sacrificed in favour of gameplay continuity.
    TODO(ledger-hardening): in production, replace the bare ``except``
    with a write-ahead buffer or retry queue so that ledger events are
    not silently dropped.

    The ``append_fn`` parameter is the callable used to write the event.
    It defaults to :func:`~mud_server.ledger.append_event` in normal
    operation and is replaced by a mock in unit tests, avoiding any
    writes to the real ``data/ledger/`` directory during testing.

    Pre-axis-engine era behaviour:
        When ``ipc_hash`` is ``None`` the event carries
        ``meta: {"phase": "pre_axis_engine"}``.  This marker lets replay
        tooling distinguish null-hash-era events from post-integration
        ones.  A non-``None`` ``ipc_hash`` means the axis engine ran
        for this interaction; ``meta`` is left empty so the hash itself
        serves as the provenance signal.

    Args:
        append_fn:      Callable with the same signature as
                        :func:`~mud_server.ledger.append_event`.
                        Injected for testability; defaults to
                        ``_ledger_append`` at every call site.
        world_id:       World the event belongs to.
        status:         Outcome string: ``"success"``,
                        ``"fallback.api_error"``, or
                        ``"fallback.validation_failed"``.
        character_name: Name of the character whose voice was translated.
        channel:        Chat channel (``"say"``, ``"yell"``,
                        ``"whisper"``).
        ooc_message:    The raw OOC input from the player.
        ic_output:      The final validated IC text, or ``None`` on any
                        fallback path.  The unvalidated raw output is
                        intentionally not stored to avoid persisting
                        partial or unsafe model output.
        profile:        Character profile dict from
                        :class:`~mud_server.translation.profile_builder.CharacterProfileBuilder`.
                        Used by :func:`_extract_snapshot` to build the
                        ``axis_snapshot`` field.
        ipc_hash:       IPC hash produced by the axis engine, or ``None``
                        when the axis engine did not run (solo-room
                        interaction, engine disabled, or engine failure).
    """
    # Mark pre-axis-engine events explicitly so they are distinguishable
    # from post-integration events during replay or ledger analysis.
    # A non-None ipc_hash means the axis engine ran; meta is empty in
    # that case because the hash itself is the provenance signal.
    meta: dict = {"phase": "pre_axis_engine"} if ipc_hash is None else {}

    # Build the axis snapshot from the profile dict.  This captures the
    # character's mechanical state at translation time — before any axis
    # mutations that might be applied by the axis engine after this call
    # returns.  The snapshot is stored so that replay tooling can
    # reconstruct the full decision context for any given translation.
    axis_snapshot = _extract_snapshot(profile)

    try:
        append_fn(
            world_id=world_id,
            event_type="chat.translation",
            ipc_hash=ipc_hash,
            meta=meta,
            data={
                "status": status,
                "character_name": character_name,
                "channel": channel,
                "ooc_input": ooc_message,
                "ic_output": ic_output,
                "axis_snapshot": axis_snapshot,
            },
        )
    except Exception:
        # Ledger failure is non-fatal.  The game interaction completes;
        # only the audit record is lost.  Explicit PoC trade-off.
        # TODO(ledger-hardening): replace with retry queue for production.
        logger.warning(
            "chat.translation ledger write failed for world %r — "
            "interaction continues without audit record.",
            world_id,
            exc_info=True,
        )


class OOCToICTranslationService:
    """Orchestrates profile building, rendering, and validation.

    One instance is created per ``World`` when the world's
    ``translation_layer.enabled`` is ``True``.  It is cached on the
    ``World`` object and reused for every chat call in that world.

    Attributes:
        _world_id:        World this service is scoped to.
        _config:          Frozen translation config from ``world.json``.
        _profile_builder: Builds the character context dict.
        _renderer:        Calls the Ollama API.
        _validator:       Validates/cleans the raw LLM output.
        _prompt_template: System prompt template text, loaded once at init.
    """

    def __init__(
        self,
        *,
        world_id: str,
        config: TranslationLayerConfig,
        world_root: Path,
    ) -> None:
        """Initialise the service.

        Args:
            world_id:   World this service is scoped to.  Required.
            config:     Frozen config from ``world.json``.
            world_root: Path to the world package directory, used to load
                        the system prompt template.

        Raises:
            ValueError: If ``world_id`` is empty (same guard as
                        ``CharacterProfileBuilder``).
        """
        if not world_id or not world_id.strip():
            raise ValueError("OOCToICTranslationService requires an explicit world_id.")

        self._world_id = world_id
        self._config = config

        self._profile_builder = CharacterProfileBuilder(
            world_id=world_id,
            active_axes=config.active_axes,
        )
        self._renderer = OllamaRenderer(
            api_endpoint=config.api_endpoint,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
            keep_alive=config.keep_alive,
        )
        self._validator = OutputValidator(
            strict_mode=config.strict_mode,
            max_output_chars=config.max_output_chars,
        )
        self._prompt_template: str = self._load_prompt_template(world_root)

        logger.info(
            "OOCToICTranslationService initialised for world %r " "(model=%s, deterministic=%s)",
            world_id,
            config.model,
            config.deterministic,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def translate(
        self,
        character_name: str,
        ooc_message: str,
        *,
        channel: str = "say",
        ipc_hash: str | None = None,
    ) -> str | None:
        """Translate an OOC message to in-character dialogue.

        Full pipeline:

        1. Build character axis profile (DB lookup).
        2. Inject ``channel`` and ``profile_summary`` into the profile dict
           so that ``{{channel}}`` and ``{{profile_summary}}`` placeholders
           in the world's ``ic_prompt.txt`` resolve correctly.
        3. Arm deterministic mode if ``ipc_hash`` is provided and
           ``config.deterministic`` is ``True``.
        4. Render the system prompt from the profile + template.
        5. Call Ollama via the renderer.
        6. Validate the raw output.
        7. Emit a ``chat.translation`` ledger event (success or fallback).

        On any failure at steps 1–6 the method returns ``None`` and the
        caller falls back to the original OOC message.  Step 7 always
        executes on the success/fallback paths (steps 5–6 only) — it is
        skipped when the profile cannot be resolved (step 1 failure)
        because there is no character data to record.

        Args:
            character_name: Name of the character speaking (must exist in
                            ``self._world_id``; world-scoped lookup is used).
            ooc_message:    The raw, unsanitised message from the player.
            channel:        Chat channel context (``"say"``, ``"yell"``,
                            ``"whisper"``).  Injected into the profile dict
                            as ``channel`` so that prompt templates can tailor
                            tone by delivery mode.
            ipc_hash:       Optional IPC hash produced by the axis engine for
                            this interaction.  When provided and
                            ``config.deterministic=True``, deterministic mode
                            is armed: temperature is clamped to 0.0 and a
                            seed derived from the hash is forwarded to Ollama,
                            ensuring identical game state + OOC input always
                            produces identical IC output.  When ``None``
                            (solo-room interaction, axis engine disabled, or
                            engine failure), deterministic mode is skipped
                            silently.

        Returns:
            IC dialogue string on success, ``None`` on any failure.
        """
        if not self._config.enabled:
            return None

        # ── Step 1: Build character profile ───────────────────────────────────
        # Fetches the character's current axis scores and resolved threshold
        # labels from the DB (world-scoped lookup — see CharacterProfileBuilder
        # docstring for why world-scoping is non-negotiable).
        profile = self._profile_builder.build(character_name)
        if profile is None:
            # Warning already logged by ProfileBuilder.
            # No ledger event — there is no character data to record.
            return None

        # ── Step 2: Inject channel and profile_summary into the profile ────────
        #
        # channel: injected so the {{channel}} placeholder in ic_prompt.txt
        # resolves to the delivery mode ("say", "yell", "whisper"), allowing
        # the template to vary tone instructions per channel.
        profile["channel"] = channel

        # profile_summary: injected so the {{profile_summary}} placeholder in
        # ic_prompt.txt resolves to a formatted multi-line block describing the
        # character's current axis state.  Without this injection, the literal
        # string "{{profile_summary}}" would be forwarded to the LLM unchanged,
        # making the model blind to all character axis data.
        profile["profile_summary"] = _build_profile_summary(profile)

        # ── Step 3: Deterministic mode ─────────────────────────────────────────
        # When the axis engine provides an ipc_hash and config.deterministic is
        # True, arm the renderer with a seed derived from the first 16 hex
        # characters of the hash.  This ensures that the same game state always
        # produces the same IC output, making translation events replayable.
        if self._config.deterministic and ipc_hash is not None:
            seed_int = int(ipc_hash[:16], 16)
            self._renderer.set_deterministic(seed_int)
            logger.debug(
                "OOCToICTranslationService: deterministic mode armed " "(ipc_hash=%s..., seed=%d)",
                ipc_hash[:8],
                seed_int,
            )

        # ── Step 4: Render system prompt ──────────────────────────────────────
        # Substitute all {{key}} placeholders in the loaded template with
        # their corresponding values from the profile dict.  At this point the
        # profile contains: all axis _label/_score fields, channel, and the
        # pre-formatted profile_summary block.
        system_prompt = self._render_system_prompt(profile, ooc_message)

        # ── Step 5: Call Ollama ────────────────────────────────────────────────
        ic_raw = self._renderer.render(system_prompt, ooc_message)
        if ic_raw is None:
            # Renderer already logged the specific failure reason.
            # Emit a ledger event recording the api_error fallback so the
            # audit trail includes every translation attempt, not just
            # successes.  The emit is fire-and-forget and never raises.
            _emit_translation_event(
                _ledger_append,
                world_id=self._world_id,
                status="fallback.api_error",
                character_name=character_name,
                channel=channel,
                ooc_message=ooc_message,
                ic_output=None,
                profile=profile,
                ipc_hash=ipc_hash,
            )
            return None

        # ── Step 6: Validate output ───────────────────────────────────────────
        ic_text = self._validator.validate(ic_raw)
        if ic_text is None:
            # Validation rejected the raw output (e.g. PASSTHROUGH sentinel,
            # output too long, or empty string).  Record the failure before
            # returning.  ic_output is None — the failed raw text is
            # intentionally not stored to avoid persisting partial or unsafe
            # model output.
            _emit_translation_event(
                _ledger_append,
                world_id=self._world_id,
                status="fallback.validation_failed",
                character_name=character_name,
                channel=channel,
                ooc_message=ooc_message,
                ic_output=None,
                profile=profile,
                ipc_hash=ipc_hash,
            )
            return None

        # ── Step 7: Emit success event ────────────────────────────────────────
        # Record the successful translation.  The event captures what the
        # player said (ooc_input), what the character said (ic_output), the
        # character's mechanical state at translation time (axis_snapshot),
        # and the ipc_hash linking this event to the preceding axis resolution.
        _emit_translation_event(
            _ledger_append,
            world_id=self._world_id,
            status="success",
            character_name=character_name,
            channel=channel,
            ooc_message=ooc_message,
            ic_output=ic_text,
            profile=profile,
            ipc_hash=ipc_hash,
        )
        return ic_text

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def config(self) -> TranslationLayerConfig:
        """Return the world's frozen translation layer configuration."""
        return self._config

    # ── Lab API ───────────────────────────────────────────────────────────────

    def translate_with_axes(
        self,
        axes: dict[str, dict],
        ooc_message: str,
        *,
        character_name: str = "Lab Subject",
        channel: str = "say",
        seed: int | None = None,
        temperature: float = 0.7,
    ) -> LabTranslateResult:
        """Translate an OOC message using raw axis values — no DB lookup.

        This is the entry point for the Axis Descriptor Lab.  It accepts a
        caller-supplied axis dict instead of looking up a character in the
        database, then runs steps 2–6 of the standard ``translate()``
        pipeline (profile injection, prompt rendering, Ollama call,
        validation).  No ledger event is emitted — lab calls are research
        runs, not production game interactions.

        The server filters ``axes`` to its configured ``active_axes`` before
        building the profile, so the caller may supply all 11 known axes and
        the server will silently use only the ones its world is configured
        for.  The response includes ``world_config`` so the lab can see
        exactly which axes were applied.

        A fresh ``OllamaRenderer`` is created for each call to avoid
        polluting the persistent game renderer's deterministic-mode state.

        Args:
            axes:           Dict of ``{axis_name: {"label": str, "score": float}}``.
                            Keys not in ``active_axes`` are silently ignored.
            ooc_message:    The raw OOC message to translate.
            character_name: Display name used in the ``profile_summary`` first
                            line.  Defaults to ``"Lab Subject"``.
            channel:        Chat channel context (``"say"``, ``"yell"``,
                            ``"whisper"``).
            seed:           Integer seed for deterministic Ollama output.
                            ``None`` means non-deterministic (random).
            temperature:    Sampling temperature forwarded to Ollama.
                            Ignored when ``seed`` is provided (clamped to
                            0.0 for determinism).

        Returns:
            :class:`LabTranslateResult` with the IC text, status, canonical
            profile_summary, and fully-rendered system prompt.
        """
        # ── Build profile from raw axes, filtered to active_axes ──────────────
        profile: dict = {"character_name": character_name}
        for axis_name in self._config.active_axes:
            if axis_name not in axes:
                continue
            ax = axes[axis_name]
            profile[f"{axis_name}_label"] = str(ax.get("label", "unknown"))
            profile[f"{axis_name}_score"] = float(ax.get("score", 0.0))

        profile["channel"] = channel
        profile["profile_summary"] = _build_profile_summary(profile)

        # ── Render system prompt ───────────────────────────────────────────────
        system_prompt = self._render_system_prompt(profile, ooc_message)

        # ── Per-call renderer (avoids state pollution with the game renderer) ──
        # The game renderer's set_deterministic() state is sticky for its
        # lifetime.  Creating a fresh instance here means lab calls never
        # affect in-progress game turns.
        renderer = OllamaRenderer(
            api_endpoint=self._config.api_endpoint,
            model=self._config.model,
            timeout_seconds=self._config.timeout_seconds,
            temperature=temperature,
            keep_alive=self._config.keep_alive,
        )
        if seed is not None:
            renderer.set_deterministic(seed)

        # ── Call Ollama ────────────────────────────────────────────────────────
        ic_raw = renderer.render(system_prompt, ooc_message)
        if ic_raw is None:
            return LabTranslateResult(
                ic_text=None,
                status="fallback.api_error",
                profile_summary=profile["profile_summary"],
                rendered_prompt=system_prompt,
            )

        # ── Validate output ────────────────────────────────────────────────────
        ic_text = self._validator.validate(ic_raw)
        if ic_text is None:
            return LabTranslateResult(
                ic_text=None,
                status="fallback.validation_failed",
                profile_summary=profile["profile_summary"],
                rendered_prompt=system_prompt,
            )

        return LabTranslateResult(
            ic_text=ic_text,
            status="success",
            profile_summary=profile["profile_summary"],
            rendered_prompt=system_prompt,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_prompt_template(self, world_root: Path) -> str:
        """Load the system prompt template from the world package.

        Reads ``config.prompt_template_path`` relative to ``world_root``.
        Falls back to a minimal built-in template if the file is missing,
        so that the service degrades gracefully rather than raising at init.

        The built-in fallback uses the individual ``{{demeanor_label}}``
        placeholder (not ``{{profile_summary}}``) so that it remains
        functional without any world-specific prompt file.

        Args:
            world_root: Path to the world package directory.

        Returns:
            Template text as a string.
        """
        template_path = world_root / self._config.prompt_template_path
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")

        logger.warning(
            "OOCToICTranslationService: prompt template not found at %s; "
            "using built-in fallback.  Create %s in the world package to "
            "customise the tone for this world.",
            template_path,
            self._config.prompt_template_path,
        )
        # Minimal fallback template.  Uses {{demeanor_label}} (a single axis
        # key that exists in every profile) rather than {{profile_summary}}
        # so it works without the profile_summary injection step.  This path
        # should only be hit during development or misconfiguration — every
        # production world must have its own ic_prompt.txt.
        return (
            "You are a character in a text-based RPG.\n"
            "Translate the following OOC message into a single line of IC "
            "dialogue consistent with a character whose demeanor is "
            "{{demeanor_label}}.\n\n"
            "Rules:\n"
            "1. Output exactly one line of spoken dialogue. No stage directions.\n"
            "2. If the OOC message cannot be rendered as IC dialogue, output "
            "only the word: PASSTHROUGH\n\n"
            "OOC MESSAGE:\n{{ooc_message}}"
        )

    def _render_system_prompt(self, profile: dict, ooc_message: str) -> str:
        """Substitute ``{{key}}`` placeholders in the template.

        Uses simple string replacement rather than a template engine to
        avoid an additional dependency.  All ``{{key}}`` placeholders in
        the template are replaced with the corresponding value from
        ``profile``, then ``{{ooc_message}}`` is substituted last.

        By the time this method is called, ``profile`` has been enriched
        by ``translate()`` to include both ``channel`` and
        ``profile_summary`` keys, ensuring those placeholders resolve.
        Any placeholder with no matching key is left unchanged in the
        output (e.g. ``{{unknown_key}}`` remains as-is), which is useful
        during prompt development — unresolved placeholders are visible
        rather than silently empty.

        Args:
            profile:     Flat profile dict from ``CharacterProfileBuilder``,
                         enriched with ``channel`` and ``profile_summary``.
            ooc_message: OOC message text.

        Returns:
            Fully-rendered system prompt string.
        """
        rendered = self._prompt_template
        # Substitute every profile key — includes axis fields, channel, and
        # the profile_summary block.
        for key, value in profile.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        # Substitute the OOC message last so that player text containing
        # {{...}} patterns cannot accidentally collide with profile keys.
        rendered = rendered.replace("{{ooc_message}}", ooc_message)
        return rendered
