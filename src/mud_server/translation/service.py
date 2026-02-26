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

Ledger integration (FUTURE — not yet implemented)
--------------------------------------------------
Each successful or failed translation call should emit a
``chat.translation`` event to a JSONL ledger file.  The event envelope
includes the axis snapshot (taken at translation time, before any
mechanical mutation), the translation config actually used, both the OOC
input and IC output, and a status string
(``success`` / ``fallback.api_error`` / ``fallback.validation_failed``).

When the ledger is built, emit the event at the end of ``translate()``,
regardless of success or failure.  See::

    _working/translation_layer/ooc_to_ic_ledger_event_schema.md

for the full event schema and storage options.

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
from pathlib import Path

from mud_server.translation.config import TranslationLayerConfig
from mud_server.translation.profile_builder import CharacterProfileBuilder
from mud_server.translation.renderer import OllamaRenderer
from mud_server.translation.validator import OutputValidator

logger = logging.getLogger(__name__)


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
            raise ValueError(
                "OOCToICTranslationService requires an explicit world_id."
            )

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
            "OOCToICTranslationService initialised for world %r "
            "(model=%s, deterministic=%s)",
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

        On any failure at steps 1–5 the method returns ``None`` and the
        caller falls back to the original OOC message.

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
                "OOCToICTranslationService: deterministic mode armed "
                "(ipc_hash=%s..., seed=%d)",
                ipc_hash[:8],
                seed_int,
            )

        # ── Step 3: Render system prompt ──────────────────────────────────────
        system_prompt = self._render_system_prompt(profile, ooc_message)

        # ── Step 4: Call Ollama ────────────────────────────────────────────────
        ic_raw = self._renderer.render(system_prompt, ooc_message)
        if ic_raw is None:
            # Renderer already logged the specific failure reason.
            # FUTURE(ledger): emit fallback.api_error event here.
            return None

        # ── Step 5: Validate output ───────────────────────────────────────────
        ic_text = self._validator.validate(ic_raw)
        if ic_text is None:
            # FUTURE(ledger): emit fallback.validation_failed event here.
            return None

        # FUTURE(ledger): emit success event here with axis_snapshot,
        # translation_config, ooc_input, ic_output.
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
