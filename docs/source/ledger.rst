JSONL Ledger
============

Overview
--------

The JSONL ledger is the **authoritative audit trail** for all mechanical
and translation events in PipeWorks.  Every chat interaction that
involves the axis engine or translation layer produces at least one
ledger event, written *before* any database update.

Key properties:

* **Append-only** — events are never modified or deleted.
* **Self-verifying** — each line carries a SHA-256 checksum over all
  other fields.
* **Per-world files** — ``data/ledger/<world_id>.jsonl``.
* **Not committed to git** — ledger files are runtime data, git-ignored
  alongside ``data/*.db``.
* **Non-fatal writes** — a ledger write failure logs a WARNING and
  allows the interaction to continue; only the audit record is lost.

File Location
-------------

::

    data/ledger/
    ├── daily_undertaking.jsonl
    └── pipeworks_web.jsonl

One file per world.  The directory is created automatically by the
first ``append_event`` call for that world.

Startup Integrity Check
-----------------------

``World._init_axis_engine`` calls
:func:`~mud_server.ledger.verify_world_ledger` at startup.

.. code-block:: python

   result: LedgerVerifyResult = verify_world_ledger(world_id)

``LedgerVerifyResult`` has three possible statuses:

.. list-table::
   :header-rows: 1
   :widths: 15 20 65

   * - ``status``
     - ``last_event_id``
     - Meaning
   * - ``"ok"``
     - hex string
     - Last line is valid JSON with a matching checksum.
   * - ``"empty"``
     - ``None``
     - File does not exist or is empty.  Normal for a fresh world.
   * - ``"corrupt"``
     - ``None``
     - Last line fails checksum verification or is not valid JSON.
       A CRITICAL log is emitted.  The server continues; full replay
       from ledger is future scope.

Envelope Format
---------------

Every JSONL line is a self-contained JSON object:

.. code-block:: json

   {
     "event_id":       "a3f91c9e2d4b5e6f...",
     "timestamp":      "2026-02-27T14:23:01.452Z",
     "world_id":       "daily_undertaking",
     "event_type":     "chat.mechanical_resolution",
     "schema_version": "1.0",
     "ipc_hash":       "a3f91c9e...",
     "meta":           {},
     "data":           { ... event-specific payload ... },
     "_checksum":      "sha256:b94f3e..."
   }

Field reference:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Field
     - Description
   * - ``event_id``
     - 32-character hex string.  Globally unique identifier for this event.
   * - ``timestamp``
     - ISO 8601 UTC timestamp.
   * - ``world_id``
     - World this event belongs to.
   * - ``event_type``
     - Dotted string identifying the event category.
       See *Event Types* below.
   * - ``schema_version``
     - Envelope schema version.  Currently ``"1.0"``.
   * - ``ipc_hash``
     - Deterministic fingerprint of the mechanical state at the time of
       this event.  Computed by ``compute_payload_hash`` from
       ``pipeworks_ipc``.  ``null`` for pre-axis-engine-era events
       (see *Pre-Axis-Engine Era* below).
   * - ``meta``
     - Optional context dict.  Empty ``{}`` for live events;
       ``{"phase": "pre_axis_engine"}`` for events written before the
       axis engine was integrated.
   * - ``data``
     - Event-specific payload.  Schema varies by ``event_type``.
   * - ``_checksum``
     - ``"sha256:<hex>"`` where the hash is computed over
       ``json.dumps({all fields except _checksum}, sort_keys=True)``.
       Allows verification without the checksum being part of its own
       hash input.

Checksum Verification
---------------------

The checksum covers all fields **except** ``_checksum`` itself:

.. code-block:: python

   import hashlib, json

   def verify_line(line: str) -> bool:
       event = json.loads(line)
       stored = event.pop("_checksum")          # remove before hashing
       payload = json.dumps(event, sort_keys=True)
       expected = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
       return stored == expected

File Locking
------------

``append_event`` acquires an exclusive POSIX ``fcntl.flock(LOCK_EX)``
before writing and releases it after.  This serialises concurrent writes
from multiple threads within the same process and from separate processes
sharing the filesystem.

.. note::

   ``fcntl`` is a POSIX API.  Ledger writes are supported on Linux and
   macOS; Windows is not a supported deployment target.

Event Types
-----------

``chat.mechanical_resolution``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Written by :meth:`~mud_server.axis.engine.AxisEngine.resolve_chat_interaction`
after computing axis deltas, **before** DB materialisation.

.. code-block:: json

   {
     "event_type": "chat.mechanical_resolution",
     "ipc_hash":   "a3f91c9e...",
     "data": {
       "channel": "say",
       "speaker": {
         "character_id":   7,
         "character_name": "Mira Voss",
         "axis_deltas":    {"demeanor": 0.011, "health": -0.01}
       },
       "listener": {
         "character_id":   12,
         "character_name": "Kael Rhys",
         "axis_deltas":    {"demeanor": -0.011, "health": -0.01}
       },
       "axis_snapshot_before": {
         "7":  {"demeanor": 0.87, "health": 0.72},
         "12": {"demeanor": 0.51, "health": 0.44}
       },
       "grammar_version": "1.0"
     }
   }

``axis_snapshot_before`` includes only axes with non-``no_effect``
resolvers to bound storage cost.

``chat.translation``
~~~~~~~~~~~~~~~~~~~~~

Written by
:meth:`~mud_server.translation.service.OOCToICTranslationService.translate`
on every translate call — success *and* failure.

.. code-block:: json

   {
     "event_type": "chat.translation",
     "ipc_hash":   "a3f91c9e...",
     "meta":       {},
     "data": {
       "status":         "success",
       "character_name": "Mira Voss",
       "channel":        "say",
       "ooc_input":      "give me the ledger",
       "ic_output":      "Hand it over — now.",
       "axis_snapshot":  {
         "demeanor": {"score": 0.87, "label": "proud"},
         "health":   {"score": 0.72, "label": "hale"}
       }
     }
   }

``status`` values:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - ``status``
     - Meaning
   * - ``"success"``
     - Ollama returned output and validation passed.
   * - ``"fallback.api_error"``
     - Ollama was unavailable or returned an error.
   * - ``"fallback.validation_failed"``
     - Ollama returned output but validation rejected it (PASSTHROUGH
       sentinel, empty string, or exceeded ``max_output_chars``).

``ic_output`` is ``null`` on fallback paths.  The raw (unvalidated)
Ollama output is intentionally not stored.

``ipc_hash`` Linkage
~~~~~~~~~~~~~~~~~~~~~

Both event types carry the same ``ipc_hash`` for a given turn.  This
links the mechanical resolution event to the translation event that
consumed it:

::

   {"event_type": "chat.mechanical_resolution", "ipc_hash": "a3f91c9e...", ...}
   {"event_type": "chat.translation",           "ipc_hash": "a3f91c9e...", ...}

This allows replay tooling to reconstruct the full decision context for
any translation: which axis scores were in play, what the grammar said,
and what the model produced.

Pre-Axis-Engine Era
-------------------

Before the axis engine was wired to the chat pipeline (Phase 4 of the
implementation plan), ``chat.translation`` events were emitted with
``ipc_hash: null`` and ``meta: {"phase": "pre_axis_engine"}``.  These
events are valid and verifiable; they simply lack a mechanical resolution
counterpart.

Replay tooling can distinguish the eras by inspecting ``ipc_hash`` and
``meta.phase``:

.. code-block:: python

   is_pre_axis = event["ipc_hash"] is None
   # or equivalently:
   is_pre_axis = event.get("meta", {}).get("phase") == "pre_axis_engine"

Python API
----------

:func:`~mud_server.ledger.append_event`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from mud_server.ledger import append_event

   event_id: str = append_event(
       world_id="daily_undertaking",
       event_type="chat.translation",
       data={"status": "success", ...},
       ipc_hash="a3f91c9e...",    # optional, default None
       meta={"phase": "..."},     # optional, default None
   )

Returns the ``event_id`` hex string.  Raises
:class:`~mud_server.ledger.writer.LedgerWriteError` on filesystem
failure.  Callers should catch and log; do not let ledger failures
propagate to the user.

:func:`~mud_server.ledger.verify_world_ledger`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from mud_server.ledger import verify_world_ledger

   result = verify_world_ledger("daily_undertaking")
   print(result.status)         # "ok" | "empty" | "corrupt"
   print(result.last_event_id)  # hex string or None
   print(result.error_detail)   # None if ok

Hardening Notes
---------------

The current implementation follows PoC trade-offs:

* Ledger write failure is non-fatal.  An audit record may be lost.
* No write-ahead buffer or retry queue.
* No automatic replay-from-ledger on DB/ledger mismatch.
* File-based locking only (no distributed lock).

Each of these is marked ``TODO(ledger-hardening)`` in the source code.
