Admin Axis Inspector
====================

Overview
--------

The Admin Axis Inspector is a purpose-built view in the Admin Web UI for
auditing character state. It exposes **authoritative axis scores** plus the
**immutable event ledger** and cached snapshot JSON. Use it to:

- verify state transitions after gameplay events,
- audit how a character arrived at a specific axis score,
- diagnose policy mismatches or missing thresholds.

Access
------

Open the Admin Web UI and navigate to ``Users``. Select a user and a character,
then open the **Axis State** tab inside the detail panel.

Behind the scenes, the UI calls:

- ``GET /admin/characters/{character_id}/axis-state``
- ``GET /admin/characters/{character_id}/axis-events?limit=50``

What You Are Looking At
-----------------------

The inspector merges three layers of data:

1. **World policy** (source of truth, from world package files)
2. **Normalized state** (axis registry + axis scores + event ledger)
3. **Snapshot JSON** (cached view for UI/debugging)

Only the **normalized tables + ledger** are authoritative. Snapshots are
derived, never authoritative.

Axis State Panel
----------------

The Axis State panel shows:

- **Axis scores**: numeric scores per axis (authoritative).
- **Axis labels**: threshold-mapped labels (derived from policy).
- **Snapshot metadata**: ``state_seed``, ``state_version``, ``state_updated_at``.
- **Snapshot JSON**: ``base_state_json`` and ``current_state_json``.

Interpretation notes:

- If the axis score changes but the label does not, the score is still within
  the same threshold range.
- ``state_version`` should match the policy hash reported at startup.
- ``state_seed`` increments when snapshots are refreshed.

Axis Events Panel
-----------------

The Axis Events panel shows immutable ledger entries with per-axis deltas and
metadata. Events are ordered by **monotonic ``event.id``** (not timestamp).

Each event includes:

- ``event_type`` and optional description
- ``timestamp`` (metadata only)
- ``metadata`` (key/value tags for debugging)
- ``deltas`` (axis changes with ``old_score``, ``new_score``, ``delta``)

Example (trimmed):

.. code-block:: json

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

How to read deltas:

- **Positive delta** increases the score.
- **Negative delta** decreases the score.
- The UI lists the **old score**, **new score**, and **delta** so you can spot
  unexpected jumps or repeated application.

Policy Validation Report
------------------------

On startup, the policy loader validates each world’s axis configuration and
emits a report. This provides an explicit “green light” that the world policy
is internally consistent.

Example report (illustrative):

.. code-block:: text

   [policy] world=pipeworks_web
   axes: wealth, reputation, fatigue
   ordering:
     wealth: ordinal (poor, modest, well-kept, wealthy)
     reputation: numeric (0.0 → 1.0)
     fatigue: ordinal (rested, tired, exhausted)
   thresholds:
     wealth: ok
     reputation: ok
     fatigue: ok
   missing components: none
   policy hash: 8f4c9a62

If any part is missing (for example, thresholds), the report will list those
components so you can fix the world policy before playing.

Debugging Workflow
------------------

Use this order for reliable diagnostics:

1. **Confirm policy**: check policy hash and thresholds in the report.
2. **Check axis score**: verify the normalized score matches expectation.
3. **Inspect events**: confirm correct deltas and ordering.
4. **Review snapshot**: ensure ``current_state_json`` matches the derived score.

Common Issues
-------------

- **Unexpected label**: thresholds may be missing or too coarse.
- **Axis score jumps**: event applied multiple times or large delta.
- **Snapshot mismatch**: snapshot cache out of date; re-derive it.
- **Missing events**: limit parameter too low or character ID mismatch.

Security Notes
--------------

The inspector is admin-only and served by the Admin Web UI. When deployed
publicly, ensure ``/admin`` is protected (for example, with mTLS) and blocked
on the public API domain. See :doc:`admin_web_ui_mtls`.
