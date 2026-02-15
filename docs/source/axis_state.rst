Axis State System
=================

Overview
--------

PipeWorks tracks character state using **axis scores** and an **event ledger**.
The ledger is authoritative: every drift or event writes immutable deltas, and
current state is derived from those numeric scores.

Key properties:

- **Deterministic ordering**: events are ordered by monotonic ``event.id``.
- **Atomic mutations**: event insert + delta insert + score update happen in
  a single transaction.
- **World-defined policy**: axes, ordering, and thresholds come from world
  policy files (not hard-coded in DB).
- **Snapshots are caches**: JSON snapshots exist for UI/debugging only and are
  never used to resolve mechanics.

World Policy Files
------------------

Policy files live in each world package:

::

   data/worlds/<world_id>/policies/
     axes.yaml
     thresholds.yaml

Example ``axes.yaml``:

.. code-block:: yaml

   version: 0.1.0
   axes:
     wealth:
       values: [poor, modest, well-kept, wealthy, decadent]
       ordering:
         type: ordinal
         values: [poor, modest, well-kept, wealthy, decadent]

Example ``thresholds.yaml``:

.. code-block:: yaml

   version: 0.1.0
   axes:
     wealth:
       values:
         poor: { min: 0.0, max: 0.19 }
         modest: { min: 0.20, max: 0.39 }
         well-kept: { min: 0.40, max: 0.59 }
         wealthy: { min: 0.60, max: 0.79 }
         decadent: { min: 0.80, max: 1.0 }

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

Axis mutations are recorded via a single transaction:

1. Insert ``event`` row
2. Insert ``event_entity_axis_delta`` rows
3. Update ``character_axis_score``
4. Refresh ``current_state_json``

If any step fails (for example, an unknown axis), the transaction is rolled
back and no changes are written.

Admin Inspection
----------------

The admin Web UI exposes both the current axis state and recent event history
for a selected character. The same data is available via API:

* ``GET /admin/characters/{character_id}/axis-state``
* ``GET /admin/characters/{character_id}/axis-events?limit=50``

Axis state returns normalized scores plus cached snapshots. Axis events return
the immutable ledger entries with per-axis deltas and any metadata tags. This
is intended for debugging, tuning, and auditing progression.

See also: :doc:`admin_axis_inspector` for a full walkthrough of the Admin Axis
Inspector UI and how to interpret event deltas.

Example ``axis-events`` response (trimmed):

.. code-block:: json

   {
     "character_id": 42,
     "events": [
       {
         "event_id": 1201,
         "world_id": "pipeworks_web",
         "event_type": "loot_found",
         "timestamp": "2026-02-15 10:12:44",
         "metadata": {"source": "treasure_chest"},
         "deltas": [
           {"axis_name": "wealth", "old_score": 0.3, "new_score": 0.5, "delta": 0.2}
         ]
       }
     ]
   }

Database Tables (Authoritative)
-------------------------------

Axis registry and score tables:

::

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

Event ledger tables:

::

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

**Rule**: never read ``current_state_json`` to resolve mechanics; rebuild it
from axis scores + policy.

Snapshot Payload (Example)
--------------------------

Snapshots store world + axis values in a compact JSON payload:

.. code-block:: json

   {
     "world_id": "pipeworks_web",
     "seed": 0,
     "policy_hash": "abc123...",
     "axes": {
       "wealth": { "score": 0.5, "label": "wealthy" },
       "health": { "score": 0.5, "label": "hale" }
     }
   }

Multi-World Isolation
---------------------

All axis tables include ``world_id`` so multiple worlds can coexist safely
in the same database.

Why Normalized + JSON?
----------------------

The normalized ledger is authoritative, queryable, and deterministic. JSON
snapshots are cheap to render and convenient for UI. This gives the best of
both worlds without compromising integrity.
