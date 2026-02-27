Axis State System
=================

Overview
--------

PipeWorks tracks character state using **axis scores** and two complementary
ledger systems:

1. **SQLite event ledger** — normalized, queryable, per-event DB rows.
   Used for admin inspection and axis score history.
2. **JSONL ledger** — append-only files at ``data/ledger/<world_id>.jsonl``.
   Authoritative source of truth.  Written *before* DB materialisation.

Key properties:

- **Deterministic ordering**: events are ordered by monotonic ``event.id``
  in the DB ledger, and by append order + timestamp in the JSONL ledger.
- **Atomic mutations**: event insert + delta insert + score update happen in
  a single DB transaction.
- **World-defined policy**: axes, ordering, thresholds, and resolution
  grammar all come from world policy files — nothing is hard-coded.
- **Snapshots are caches**: JSON snapshots exist for UI/debugging only and
  are never used to resolve mechanics.
- **Ledger first**: the JSONL ``chat.mechanical_resolution`` event is
  written before the DB is updated.  The DB is always a materialisation
  of what the ledger already committed.

.. note::

   See :doc:`ledger` for the full JSONL ledger specification and event
   envelope format.

World Policy Files
------------------

Policy files live in each world package::

   data/worlds/<world_id>/policies/
     axes.yaml           ← axis registry (names, labels, ordinal ordering)
     thresholds.yaml     ← float score → label mappings
     resolution.yaml     ← chat resolver grammar  ← NEW
     ic_prompt.txt       ← translation system prompt template  ← NEW

Example ``axes.yaml``:

.. code-block:: yaml

   version: 0.1.0
   axes:
     demeanor:
       values: [resentful, guarded, neutral, proud, commanding]
       ordering:
         type: ordinal
         values: [resentful, guarded, neutral, proud, commanding]
     health:
       values: [incapacitated, wounded, scarred, hale, vigorous]
       ordering:
         type: ordinal
         values: [incapacitated, wounded, scarred, hale, vigorous]

Example ``thresholds.yaml``:

.. code-block:: yaml

   version: 0.1.0
   axes:
     demeanor:
       values:
         resentful:  { min: 0.0,  max: 0.19 }
         guarded:    { min: 0.20, max: 0.39 }
         neutral:    { min: 0.40, max: 0.59 }
         proud:      { min: 0.60, max: 0.79 }
         commanding: { min: 0.80, max: 1.0  }

Resolution Grammar
------------------

The resolution grammar is the machine-readable ruleset that controls
what happens to each axis when two characters interact via chat.  It
lives at ``data/worlds/<world_id>/policies/resolution.yaml`` and is
loaded once at world startup by
:func:`~mud_server.axis.grammar.load_resolution_grammar`.

Full example:

.. code-block:: yaml

   version: "1.0"

   interactions:
     chat:
       channel_multipliers:
         say:     1.0
         yell:    1.5
         whisper: 0.5

       min_gap_threshold: 0.05

       axes:
         demeanor:
           resolver: dominance_shift
           base_magnitude: 0.03

         health:
           resolver: shared_drain
           base_magnitude: 0.01

         wealth:
           resolver: no_effect
         physique:
           resolver: no_effect
         # ... all other axes must be listed explicitly

**Design rules:**

* Every axis defined in ``axes.yaml`` must have an entry in the
  grammar.  ``no_effect`` is the explicit no-op for axes not involved
  in a given interaction type.
* New stimulus types (environmental, physical, economic) add new
  top-level keys under ``interactions`` without modifying existing
  grammar blocks.
* New resolver algorithms add entries to the resolver registry in
  ``axis/engine.py`` without modifying the YAML schema.

Grammar Dataclasses
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @dataclass(frozen=True)
   class AxisRuleConfig:
       resolver: str           # "dominance_shift" | "shared_drain" | "no_effect"
       base_magnitude: float   # scaling factor for this axis

   @dataclass(frozen=True)
   class ChatGrammar:
       channel_multipliers: dict[str, float]   # {"say": 1.0, "yell": 1.5, ...}
       min_gap_threshold: float                # below which dominance_shift → (0, 0)
       axes: dict[str, AxisRuleConfig]

   @dataclass(frozen=True)
   class ResolutionGrammar:
       version: str
       chat: ChatGrammar

Resolver Functions
------------------

Resolvers are pure stateless functions in
:mod:`mud_server.axis.resolvers`.  Each returns
``(speaker_delta, listener_delta)`` as a ``tuple[float, float]``.
They never clamp; the engine applies ``[0.0, 1.0]`` clamping after
all resolvers have run.

``dominance_shift``
~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   gap       = abs(speaker_score - listener_score)
   magnitude = base_magnitude × channel_multiplier × gap

   if gap < min_gap_threshold:
       return (0.0, 0.0)            # too evenly matched → no shift

   winner (higher score) gets +magnitude
   loser  (lower  score) gets −magnitude

Two similarly-matched characters interact without either gaining social
ground.  Health still drains regardless (see ``shared_drain``).

Note: the gap threshold uses a **strict ``<``** comparison.  A gap
exactly equal to ``min_gap_threshold`` is *not* below threshold and
produces a real delta.

``shared_drain``
~~~~~~~~~~~~~~~~

.. code-block:: text

   drain = −(base_magnitude × channel_multiplier)
   return (drain, drain)    # same negative delta for both parties

Social interaction has a universal physical cost.  The drain applies
whether or not the demeanor gap triggers a dominance shift.

``no_effect``
~~~~~~~~~~~~~

.. code-block:: text

   return (0.0, 0.0)

Explicit no-op.  Listed in the grammar rather than silently omitted so
the engine can assert complete axis coverage.

Axis Engine
-----------

:class:`~mud_server.axis.engine.AxisEngine` is instantiated once per
world at startup (via ``World._init_axis_engine``).  It is retrieved
by game engine code via ``world.get_axis_engine()``.

Resolution Sequence
~~~~~~~~~~~~~~~~~~~

``resolve_chat_interaction(speaker_name, listener_name, channel, world_id)``
executes the following ten steps under per-character locks:

.. code-block:: text

   1.  Resolve character IDs from names (world-scoped DB lookup)
   2.  Acquire per-character locks (both speaker and listener)
       └── Locks are always acquired in ascending character_id order
           to prevent deadlocks in concurrent interactions
   3.  Read current axis scores from DB
   4.  Build axis_snapshot_before (active axes only — non-no_effect)
   5.  Run resolvers for all grammar axes; collect raw deltas
   6.  Compute ipc_hash = compute_payload_hash({world_id, speaker_id,
       listener_id, channel, axis_snapshot_before, grammar_version})
   7.  Write chat.mechanical_resolution to JSONL ledger  ← authoritative
   8.  Compute clamped new scores: clamp(old + raw, 0.0, 1.0)
   9.  Apply clamped deltas via apply_axis_event() to DB  ← materialisation
   10. Release locks; return AxisResolutionResult

Steps 7 and 9 are individually non-fatal.  A ledger write failure
logs ERROR and continues.  A DB write failure logs WARNING and
continues.  The result (including the ``ipc_hash``) is always returned
to the caller.

Result Dataclasses
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @dataclass(frozen=True)
   class AxisDelta:
       axis_name: str
       old_score: float
       new_score: float    # clamped to [0.0, 1.0]
       delta: float        # new_score - old_score (may differ from raw after clamping)

   @dataclass(frozen=True)
   class EntityResolution:
       character_id: int
       character_name: str
       deltas: tuple[AxisDelta, ...]

   @dataclass(frozen=True)
   class AxisResolutionResult:
       ipc_hash: str
       world_id: str
       channel: str
       speaker: EntityResolution
       listener: EntityResolution
       axis_snapshot_before: dict   # {axis_name: {score: float}} for active axes

.. note::

   ``ipc_hash`` is computed using ``compute_payload_hash`` from
   ``pipeworks_ipc`` directly (not ``compute_ipc_id``), because
   mechanical resolution involves no LLM call and therefore has no
   ``system_prompt_hash``.  The hash fingerprints the mechanical state
   of the interaction rather than an LLM invocation.

IPC Hash and Ledger Linkage
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every ``chat.mechanical_resolution`` event in the JSONL ledger carries
an ``ipc_hash`` that fingerprints the exact mechanical state at the
moment of resolution.  The same hash is forwarded to the translation
service and embedded in the ``chat.translation`` ledger event.

This creates a traceable link between the two ledger events:

::

   JSONL ledger (data/ledger/daily_undertaking.jsonl)

   {"event_type": "chat.mechanical_resolution", "ipc_hash": "a3f91c9e...", ...}
   {"event_type": "chat.translation",           "ipc_hash": "a3f91c9e...", ...}
                                                              ^^^^^^^^^^^^
                                                              same hash → same turn

Locking Model
~~~~~~~~~~~~~

``AxisEngine`` maintains a per-character ``threading.Lock`` pool.  For
any two-party interaction the engine acquires **both** locks before
reading scores, and releases both after DB materialisation.  Locks are
always acquired in ascending ``character_id`` order to prevent
deadlocks when two concurrent interactions share one participant.

World Integration
-----------------

``World._init_axis_engine`` is called during ``_load_from_zones`` at
startup.  It:

1. Checks ``world_data["axis_engine"]["enabled"]`` (default: ``False``)
2. Calls ``verify_world_ledger(world_id)`` for a startup integrity check
3. Loads ``policies/resolution.yaml`` via ``load_resolution_grammar``
4. Instantiates ``AxisEngine(world_id=..., grammar=...)``

If any step fails, ``_axis_engine`` is set to ``None`` and an ERROR is
logged.  The world starts normally; chat interactions degrade gracefully
(no axis resolution, ``ipc_hash = None``).

``world.get_axis_engine()`` returns the live engine or ``None``.
``world.axis_resolution_enabled()`` returns ``True`` only when the
engine was successfully initialised.

Policy Validation Report
------------------------

The policy loader produces a validation report containing:

- **axes list**
- **ordering definitions**
- **thresholds present**
- **missing components**
- **policy hash/version string**

This is emitted at startup to confirm world readiness.

Registry Seeding
----------------

On startup, the engine mirrors world policy files into the axis registry
tables (``axis`` and ``axis_value``). This makes the database a queryable
reflection of the policy while keeping policy files as the source of truth.

Event Application
-----------------

DB axis mutations are recorded via a single transaction inside
``events_repo.apply_axis_event``:

1. Insert ``event`` row
2. Insert ``event_entity_axis_delta`` rows
3. Update ``character_axis_score``
4. Refresh ``current_state_json``

If any step fails (for example, an unknown axis), the transaction is
rolled back and no changes are written to the DB.  The JSONL ledger
entry is unaffected — it was written before this DB call.

Admin Inspection
----------------

The admin Web UI exposes both the current axis state and recent event
history for a selected character. The same data is available via API:

* ``GET /admin/characters/{character_id}/axis-state``
* ``GET /admin/characters/{character_id}/axis-events?limit=50``

Axis state returns normalised scores plus cached snapshots. Axis events
return the immutable DB ledger entries with per-axis deltas and any
metadata tags. This is intended for debugging, tuning, and auditing
progression.

See also: :doc:`admin_axis_inspector` for a full walkthrough of the Admin
Axis Inspector UI and how to interpret event deltas.

Example ``chat.mechanical_resolution`` ledger event:

.. code-block:: json

   {
     "event_id":       "a3f91c9e2d4b5e6f...",
     "timestamp":      "2026-02-27T14:23:01.452Z",
     "world_id":       "daily_undertaking",
     "event_type":     "chat.mechanical_resolution",
     "schema_version": "1.0",
     "ipc_hash":       "a3f91c9e...",
     "data": {
       "channel": "say",
       "speaker": {
         "character_id": 7,
         "character_name": "Mira Voss",
         "axis_deltas": {"demeanor": 0.011, "health": -0.01}
       },
       "listener": {
         "character_id": 12,
         "character_name": "Kael Rhys",
         "axis_deltas": {"demeanor": -0.011, "health": -0.01}
       },
       "axis_snapshot_before": {
         "7":  {"demeanor": 0.87, "health": 0.72},
         "12": {"demeanor": 0.51, "health": 0.44}
       },
       "grammar_version": "1.0"
     },
     "_checksum": "sha256:b94f3e..."
   }

``axis_snapshot_before`` includes only axes with non-``no_effect``
resolvers in order to bound storage cost.  The full snapshot is in the
DB ``current_state_json`` column if needed.

Database Tables (Authoritative)
-------------------------------

Axis registry and score tables::

   axis
     id (PK)
     world_id
     name
     ordering_json

   axis_value
     id (PK)
     axis_id (FK → axis.id)
     value
     min_score / max_score
     ordinal

   character_axis_score
     character_id (FK → characters.id)
     world_id
     axis_id (FK → axis.id)
     axis_score
     updated_at

Event ledger tables (DB)::

   event
     id (PK)
     world_id
     event_type_id (FK → event_type.id)
     timestamp

   event_entity_axis_delta
     id (PK)
     event_id (FK → event.id)
     character_id (FK → characters.id)
     axis_id (FK → axis.id)
     old_score
     new_score
     delta

   event_metadata
     id (PK)
     event_id (FK → event.id)
     key
     value

Snapshots (Derived)
-------------------

The ``characters`` table stores cached JSON snapshots:

- ``base_state_json`` (seed snapshot at creation)
- ``current_state_json`` (derived from axis scores + thresholds)

**Rule**: never read ``current_state_json`` to resolve mechanics; rebuild
it from axis scores + policy.

Multi-World Isolation
---------------------

All axis tables include ``world_id`` so multiple worlds can coexist safely
in the same database.

Why Normalised + JSON?
----------------------

The normalised DB ledger is authoritative, queryable, and deterministic.
JSON snapshots are cheap to render and convenient for UI.  The JSONL
flat-file ledger is the write-ahead record that backs both.  This gives
the best of all three worlds without compromising integrity.
