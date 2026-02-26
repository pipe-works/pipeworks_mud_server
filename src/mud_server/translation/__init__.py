"""OOC → IC translation layer for pipeworks_mud_server.

This package intercepts raw player/NPC chat input and renders it as
in-character dialogue using a locally-hosted LLM (via Ollama).

Architecture
------------
The translation layer is intentionally *non-authoritative*: it never
touches axis scores, ledger entries, or any game-mechanical state.  Its
sole responsibility is narrative rendering — taking a mechanical truth
and expressing it in the voice appropriate to a character's current axis
profile.

Package structure
-----------------
config.py           TranslationLayerConfig  — world-scoped settings loaded
                    from world.json.
profile_builder.py  CharacterProfileBuilder — fetches axis state from DB
                    and builds the template context dict.
renderer.py         OllamaRenderer          — synchronous HTTP client for
                    the Ollama /api/chat endpoint.
validator.py        OutputValidator         — validates/cleans raw LLM output
                    before it is stored.
service.py          OOCToICTranslationService — orchestrates the other four
                    classes; the single public entry-point used by the engine.

Typical call flow (inside GameEngine.chat)
------------------------------------------
1. engine obtains ``world.get_translation_service()``
2. ``service.translate(character_name, ooc_message, channel="say")``
3. ProfileBuilder fetches axis snapshot from DB
4. Renderer calls Ollama with the rendered system prompt
5. Validator checks the raw output
6. On success → IC text returned; on any failure → None (caller falls back)

Ledger integration (FUTURE — not yet implemented)
--------------------------------------------------
When the event ledger is built, each call to ``service.translate`` will
emit a ``chat.translation`` JSONL event containing the axis snapshot,
translation config, OOC input, IC output, and status.  The IPC hash will
be produced by the axis engine and threaded through the ``ipc_hash``
parameter of ``translate()``.  See ``_working/translation_layer/`` for
the full ledger event schema.
"""

from mud_server.translation.service import OOCToICTranslationService

__all__ = ["OOCToICTranslationService"]
