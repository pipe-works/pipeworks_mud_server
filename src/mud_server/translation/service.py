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
                       time (i.e. before any axis mutations)

A ledger write failure is **never fatal** — the game interaction
completes and only the audit record is lost.  See
``TODO(ledger-hardening)`` comments in :func:`_emit_translation_event`.

The event is **not** emitted when the character profile cannot be
resolved (``profile is None``) — there is no character data to record.

Pre-axis-engine era: events carry ``meta: {"phase": "pre_axis_engine"}``
while ``ipc_hash`` is always ``None``.  See the IPC hash section below.

IPC hash and deterministic mode (FUTURE — axis engine integration)
------------------------------------------------------------------
``translate()`` accepts an optional ``ipc_hash: str | None`` parameter.
When the axis engine is integrated it will compute::

    ipc_hash = axis_engine.compute_ipc(world_id, entity_a, entity_b, turn)

and pass it here.  The service will then:
1. Convert ``ipc_hash[:16]`` to ``int`` to obtain the Ollama seed.
2. Call ``self._renderer.set_deterministic(seed_int)``.
3. Log the seed to the ledger event.

Until that point ``ipc_hash`` is always ``None`` and deterministic mode
is silently skipped, even if ``config.deterministic = True``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from mud_server.ledger import append_event as _ledger_append
from mud_server.translation.config import TranslationLayerConfig
from mud_server.translation.profile_builder import CharacterProfileBuilder
from mud_server.translation.renderer import OllamaRenderer
from mud_server.translation.validator import OutputValidator

logger = logging.getLogger(__name__)


# ── Module-level helpers ──────────────────────────────────────────────────────


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
    (e.g. ``character_name``, ``channel``) are silently ignored.

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
        When ``ipc_hash`` is ``None`` (which is always the case until the
        axis engine is integrated in Phase 4) the event carries
        ``meta: {"phase": "pre_axis_engine"}``.  This marker lets replay
        tooling distinguish null-hash-era events from post-integration
        ones.

        TODO(axis-engine): when ``ipc_hash`` is non-None, set
        ``meta: {"phase": "axis_engine_live"}`` instead — or omit meta
        entirely and let the non-null ipc_hash itself serve as the
        provenance signal.

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
                        in the pre-axis-engine era.
    """
    # Mark pre-axis-engine events explicitly so they are distinguishable
    # from post-integration events during replay or ledger analysis.
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
        2. Arm deterministic mode if ``ipc_hash`` is provided and
           ``config.deterministic`` is ``True``.
        3. Render the system prompt from the profile + template.
        4. Call Ollama via the renderer.
        5. Validate the raw output.
        6. Emit a ``chat.translation`` ledger event (success or fallback).

        On any failure at steps 1–5 the method returns ``None`` and the
        caller falls back to the original OOC message.  Step 6 always
        executes on the success/fallback paths (steps 4–5 only) — it is
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
            ipc_hash:       Optional IPC hash produced by the axis engine.
                            When provided and ``config.deterministic=True``,
                            deterministic mode is armed on the renderer.

                            CURRENT STATUS: always ``None`` — the axis engine
                            is not yet integrated.  When it is, the engine
                            will pass the hash here and deterministic mode
                            will activate automatically.  See module docstring
                            for the full integration plan.

        Returns:
            IC dialogue string on success, ``None`` on any failure.
        """
        if not self._config.enabled:
            return None

        # ── Step 1: Build character profile ───────────────────────────────────
        profile = self._profile_builder.build(character_name)
        if profile is None:
            # Warning already logged by ProfileBuilder.
            return None

        # Inject channel so templates can vary tone by delivery mode.
        profile["channel"] = channel

        # ── Step 2: Deterministic mode (requires axis engine — see docstring) ─
        #
        # TODO(axis-engine): when the axis engine is integrated and ipc_hash is
        # no longer None, this block will arm deterministic rendering using a
        # seed derived from the hash.  For now it is always skipped.
        if self._config.deterministic and ipc_hash is not None:
            seed_int = int(ipc_hash[:16], 16)
            self._renderer.set_deterministic(seed_int)
            logger.debug(
                "OOCToICTranslationService: deterministic mode armed " "(ipc_hash=%s..., seed=%d)",
                ipc_hash[:8],
                seed_int,
            )

        # ── Step 3: Render system prompt ──────────────────────────────────────
        system_prompt = self._render_system_prompt(profile, ooc_message)

        # ── Step 4: Call Ollama ────────────────────────────────────────────────
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

        # ── Step 5: Validate output ───────────────────────────────────────────
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

        # ── Step 6: Emit success event ────────────────────────────────────────
        # Record the successful translation.  The event captures what the
        # player said (ooc_input), what the character said (ic_output), the
        # character's mechanical state at translation time (axis_snapshot),
        # and whether this is a pre-axis-engine event (meta.phase).
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

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_prompt_template(self, world_root: Path) -> str:
        """Load the system prompt template from the world package.

        Reads ``config.prompt_template_path`` relative to ``world_root``.
        Falls back to a minimal built-in template if the file is missing,
        so that the service degrades gracefully rather than raising at init.

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

        Args:
            profile:     Flat profile dict from ``CharacterProfileBuilder``.
            ooc_message: OOC message text.

        Returns:
            Fully-rendered system prompt string.
        """
        rendered = self._prompt_template
        for key, value in profile.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        rendered = rendered.replace("{{ooc_message}}", ooc_message)
        return rendered
