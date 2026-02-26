"""Translation layer configuration.

``TranslationLayerConfig`` is a frozen dataclass that mirrors the
``translation_layer`` block inside each world's ``world.json``.  It is
loaded once when the World is initialised and never mutated at runtime.

Configuration precedence (locked)
----------------------------------
1. If server-level ``ollama_translation.enabled = false``
   → translation is OFF globally (enforced in World._init_translation_service).
2. Else if world.json ``translation_layer.enabled = true``
   → translation is ON for that world.
3. Otherwise → OFF.

World config may override individual field values (model, timeout, etc.),
but it cannot override the server master switch.

Deterministic mode
------------------
When ``deterministic = true`` the renderer will clamp temperature to 0.0
and use an integer seed derived from the IPC hash.

IPC hash sourcing (FUTURE — axis engine integration)
----------------------------------------------------
Currently ``translate()`` accepts an optional ``ipc_hash: str | None``
parameter.  When it is ``None`` (the default) deterministic mode is
skipped even if ``deterministic = true`` in config, because there is no
seed available yet.

Once the axis engine is built and integrated, it will call::

    ipc_hash = axis_engine.compute_ipc(world_id, entity_a, entity_b, turn)

and pass that hash to ``service.translate(..., ipc_hash=ipc_hash)``.  At
that point deterministic mode will activate automatically when
``deterministic = true`` and the hash is provided.

See ``_working/translation_layer/ooc_ic_translator_design_principles.md``
section 3 (Determinism Mode) for the full specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TranslationLayerConfig:
    """Immutable, world-scoped configuration for the OOC→IC translation layer.

    Loaded from the ``translation_layer`` block in a world's ``world.json``
    and frozen after construction so that no runtime code can mutate it.

    Attributes:
        enabled:              Master switch.  If ``False`` the service will
                              not be instantiated and the layer is inactive.
        model:                Ollama model tag (e.g. ``"gemma2:2b"``).
        ollama_base_url:      Base URL of the running Ollama instance.
                              The ``/api/chat`` path is appended automatically.
        timeout_seconds:      HTTP request timeout for Ollama calls.  On
                              expiry the service returns ``None`` and the
                              caller falls back to the OOC message.
        strict_mode:          When ``True``, any non-compliant LLM output
                              (multi-line, forbidden patterns, over-length)
                              triggers an immediate fallback rather than a
                              best-effort cleanup.
        max_output_chars:     Hard ceiling on IC output length.  Responses
                              exceeding this are rejected (strict) or
                              truncated (non-strict).
        prompt_template_path: Path *relative to the world root* for the
                              ``ic_prompt.txt`` system prompt template.
        active_axes:          Subset of axis names to include in the
                              character profile sent to the LLM.  An empty
                              list means "all axes that exist for this
                              character".
        deterministic:        When ``True`` and a non-``None`` ``ipc_hash``
                              is provided to ``translate()``, the renderer
                              will use ``temperature=0.0`` and a seed
                              derived from the IPC hash.  See module
                              docstring for IPC sourcing status.
    """

    enabled: bool
    model: str
    ollama_base_url: str
    timeout_seconds: float
    strict_mode: bool
    max_output_chars: int
    prompt_template_path: str
    active_axes: list[str]
    deterministic: bool

    @property
    def api_endpoint(self) -> str:
        """Full Ollama ``/api/chat`` URL constructed from ``ollama_base_url``."""
        return f"{self.ollama_base_url.rstrip('/')}/api/chat"

    @classmethod
    def from_dict(cls, data: dict, *, world_root: Path) -> TranslationLayerConfig:  # noqa: ARG002
        """Parse a ``translation_layer`` config block from ``world.json``.

        Missing optional fields fall back to safe defaults so that a minimal
        ``{"enabled": true}`` block is sufficient for basic operation.

        Args:
            data:       The ``translation_layer`` dict from ``world.json``.
            world_root: Passed for future use (e.g. resolving relative paths
                        at parse time).  Currently unused at construction but
                        kept in the signature to avoid a breaking change later.

        Returns:
            A fully-populated, frozen ``TranslationLayerConfig``.
        """
        return cls(
            enabled=bool(data.get("enabled", False)),
            model=str(data.get("model", "gemma2:2b")),
            ollama_base_url=str(data.get("ollama_base_url", "http://localhost:11434")),
            timeout_seconds=float(data.get("timeout_seconds", 10.0)),
            strict_mode=bool(data.get("strict_mode", True)),
            max_output_chars=int(data.get("max_output_chars", 280)),
            prompt_template_path=str(data.get("prompt_template_path", "policies/ic_prompt.txt")),
            active_axes=list(data.get("active_axes", [])),
            deterministic=bool(data.get("deterministic", False)),
        )

    @classmethod
    def disabled(cls) -> TranslationLayerConfig:
        """Return a config object that represents a disabled translation layer.

        Used as the default when a world has no ``translation_layer`` block,
        or when the server master switch is off.
        """
        return cls(
            enabled=False,
            model="gemma2:2b",
            ollama_base_url="http://localhost:11434",
            timeout_seconds=10.0,
            strict_mode=True,
            max_output_chars=280,
            prompt_template_path="policies/ic_prompt.txt",
            active_axes=[],
            deterministic=False,
        )
