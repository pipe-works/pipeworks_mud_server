Translation Layer
=================

Overview
--------

The translation layer converts a player's **out-of-character (OOC)**
message into **in-character (IC)** dialogue before it is stored in the
chat log.  It is rendered by a locally-hosted language model (Ollama)
using a character-specific system prompt built from the character's
current axis scores.

Design principles:

* **Non-authoritative** — the layer cannot change axis scores or any
  other game state.  It is flavour text, not mechanics.
* **Gracefully degrading** — any failure (Ollama unavailable,
  validation error, missing character profile) returns ``None`` and
  the engine stores the original OOC message unmodified.
* **Ledger-linked** — every call emits a ``chat.translation`` event to
  the JSONL ledger (success and failure alike), carrying the same
  ``ipc_hash`` produced by the axis engine for the same turn.

See :doc:`ledger` for the full ledger event format and :doc:`axis_state`
for the axis engine that produces the ``ipc_hash``.

Configuration
-------------

Translation is configured per-world in ``world.json``:

.. code-block:: json

   {
     "translation_layer": {
       "enabled":               true,
       "model":                 "gemma2:2b",
       "ollama_base_url":       "http://localhost:11434",
       "timeout_seconds":       10.0,
       "strict_mode":           true,
       "max_output_chars":      280,
       "prompt_template_path":  "policies/ic_prompt.txt",
       "active_axes":           ["demeanor", "health", "physique",
                                 "wealth", "facial_signal"],
       "deterministic":         false
     }
   }

Field reference:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Description
   * - ``enabled``
     - Must be ``true`` to activate the layer.  Default ``false``.
   * - ``model``
     - Ollama model tag (e.g. ``"gemma2:2b"``).
   * - ``ollama_base_url``
     - Ollama API base URL.  Default ``"http://localhost:11434"``.
   * - ``timeout_seconds``
     - Request timeout for Ollama API calls.  Default 10.0.
   * - ``strict_mode``
     - If ``true``, the PASSTHROUGH sentinel causes the call to return
       ``None``.  If ``false``, PASSTHROUGH is passed through as-is.
   * - ``max_output_chars``
     - Maximum length of the validated IC output.  Longer strings are
       rejected.  Default 280.
   * - ``prompt_template_path``
     - Path to the system prompt template, relative to the world root.
       Default ``"policies/ic_prompt.txt"``.
   * - ``active_axes``
     - List of axis names included in the character profile dict.
       Other axes are excluded from the system prompt context.
   * - ``deterministic``
     - If ``true`` and an ``ipc_hash`` is available, the renderer is
       seeded with ``int(ipc_hash[:16], 16)`` for reproducible output.

There is also a server-level master switch in ``config/server.ini``:

.. code-block:: ini

   [ollama_translation]
   enabled = true

Setting this to ``false`` disables translation for all worlds
regardless of their individual ``world.json`` settings.

Translation Pipeline
--------------------

``OOCToICTranslationService.translate(character_name, ooc_message, *, channel, ipc_hash)``
executes the following pipeline:

.. code-block:: text

   1. Build character axis profile (DB lookup via CharacterProfileBuilder)
      └── Returns None → no ledger event, return None (no profile data)

   2. Arm deterministic mode if ipc_hash is set and config.deterministic
      └── seed = int(ipc_hash[:16], 16) → OllamaRenderer.set_deterministic(seed)

   3. Inject channel into profile dict ("say" | "yell" | "whisper")

   4. Render system prompt from ic_prompt.txt template
      └── {{key}} substitution from profile dict
      └── {{ooc_message}} substituted last

   5. Call Ollama /api/chat (synchronous HTTP via requests)
      └── Failure → emit "fallback.api_error" ledger event → return None

   6. Validate raw output (OutputValidator)
      ├── PASSTHROUGH sentinel → emit "fallback.validation_failed" → return None
      ├── Empty string → emit "fallback.validation_failed" → return None
      └── Exceeds max_output_chars → emit "fallback.validation_failed" → return None

   7. Emit "success" chat.translation ledger event
      └── Carries ipc_hash (may be None in pre-axis-engine era)

   Return: IC text string (or None on any failure)

The caller (``GameEngine.chat/yell/whisper``) uses the returned text as
the stored message; if ``None``, the OOC message is stored unchanged.

System Prompt Template
----------------------

The template lives at ``data/worlds/<world_id>/policies/ic_prompt.txt``
(path configurable in ``world.json``).  It uses ``{{key}}`` placeholders
that are substituted from the character profile dict.

Available placeholders include all fields produced by
``CharacterProfileBuilder``, plus ``{{channel}}`` injected by the
service and ``{{ooc_message}}`` substituted last.

Built-in placeholders:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Placeholder
     - Source
   * - ``{{character_name}}``
     - Character's name from DB
   * - ``{{demeanor_score}}``
     - Axis float score (0.0–1.0)
   * - ``{{demeanor_label}}``
     - Axis label (e.g. ``"proud"``, ``"guarded"``)
   * - ``{{health_score}}``
     - Same pattern for each axis in ``active_axes``
   * - ``{{health_label}}``
     - Same pattern for each axis in ``active_axes``
   * - ``{{channel}}``
     - ``"say"``, ``"yell"``, or ``"whisper"``
   * - ``{{ooc_message}}``
     - The raw OOC input from the player
   * - ``{{profile_summary}}``
     - Pre-formatted axis summary block (if the template uses it)

If the template file is absent at startup, the service falls back to a
built-in minimal template and logs a WARNING.

Example template (``pipeworks_web/policies/ic_prompt.txt``):

.. code-block:: text

   You are a narrative rendering engine for a text-based role-playing game
   set in the Undertaking — a ledger-driven, procedural city where every
   transaction is recorded and failure is carved in stone.  Your sole
   function is to translate the user's out-of-character (OOC) message into
   a single line of in-character (IC) dialogue.

   CHARACTER PROFILE (current state):
   {{profile_summary}}
     Delivery Mode: {{channel}}

   TRANSLATION RULES (non-negotiable):
     1. Output exactly one line of spoken dialogue.  No stage directions.
     2. The dialogue must reflect the character's profile.
     3. The city register matters: gritty, transactional, exhausted.
     4. Adjust for delivery mode: "say" is direct; "yell" is raw and
        urgent; "whisper" is conspiratorial and clipped.
     5. If the message cannot be rendered as IC dialogue, output only
        the word: PASSTHROUGH

PASSTHROUGH Sentinel
--------------------

If the model outputs only the word ``PASSTHROUGH`` (case-insensitive
by default), the validator treats it as a signal that the OOC message
cannot be rendered as IC dialogue (e.g. a game command, meta-question,
or pure punctuation).

In ``strict_mode`` (the default):

* ``PASSTHROUGH`` → ``validate()`` returns ``None``
* A ``"fallback.validation_failed"`` ledger event is emitted
* The engine falls back to the original OOC message

In lenient mode (``strict_mode: false``):

* ``PASSTHROUGH`` is returned as-is to the caller

Character Profile Builder
-------------------------

:class:`~mud_server.translation.profile_builder.CharacterProfileBuilder`
builds the flat dict injected into the system prompt.

It performs a world-scoped DB lookup for the character's current axis
scores, resolves labels using the world's threshold policy, and returns
a dict of the form:

.. code-block:: python

   {
       "character_name": "Mira Voss",
       "demeanor_score": 0.87,
       "demeanor_label": "proud",
       "health_score":   0.72,
       "health_label":   "hale",
       ...
   }

Only axes listed in ``active_axes`` (from ``world.json``) are included.

Axis Snapshot in Ledger Events
-------------------------------

The ``chat.translation`` ledger event includes an ``axis_snapshot``
field derived from the character profile at translation time.  This
captures the character's mechanical state *before* any axis mutations
applied during the same turn:

.. code-block:: json

   "axis_snapshot": {
     "demeanor": {"score": 0.87, "label": "proud"},
     "health":   {"score": 0.72, "label": "hale"}
   }

Because the axis engine runs *before* translation, the snapshot
reflects scores that are already post-mutation for this turn.  For the
pre-mutation snapshot, see ``axis_snapshot_before`` in the
``chat.mechanical_resolution`` event.

IPC Hash and Deterministic Mode
---------------------------------

When the axis engine is active, ``GameEngine.chat/yell/whisper`` calls
the axis engine first and retrieves an ``ipc_hash``:

.. code-block:: python

   result = axis_engine.resolve_chat_interaction(
       speaker_name=username,
       listener_name=co_present[0],
       channel="say",
       world_id=world_id,
   )
   ipc_hash = result.ipc_hash   # e.g. "a3f91c9e..."

This hash is passed to ``translate()``:

.. code-block:: python

   ic_text = translation_service.translate(
       character_name=username,
       ooc_message=message,
       channel="say",
       ipc_hash=ipc_hash,
   )

Inside ``translate()``:

* The hash is embedded in the ``chat.translation`` ledger event.
* If ``config.deterministic = True``, the first 16 hex characters are
  converted to an integer seed for Ollama's ``options.seed`` parameter,
  making the model output reproducible given the same mechanical state.

If the axis engine is disabled or fails, ``ipc_hash`` is ``None`` and
deterministic mode is silently skipped.

Per-World Enable/Disable
------------------------

.. code-block:: json

   {"translation_layer": {"enabled": true}}    ← pipeworks_web (test world)
   {"translation_layer": {"enabled": false}}   ← daily_undertaking (production)

The service is instantiated lazily at world load time.
``world.get_translation_service()`` returns ``None`` when disabled.

Hardening Notes
---------------

Current PoC trade-offs:

* Translation is **synchronous** — the Ollama HTTP call blocks the
  request thread.  An async upgrade path is documented in
  ``translation/renderer.py``.
* Ledger write failure is non-fatal (same as the axis engine).
* No retry logic for transient Ollama errors.
