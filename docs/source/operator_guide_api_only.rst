Operator Guide: API-Only Canonical Policy Operations
=====================================================

Canonical Source of Truth
-------------------------

1. Canonical policy authority is SQLite (``policy_item``, ``policy_variant``,
   ``policy_activation``, and related audit tables).
2. Runtime reads effective policy state via Layer 3 activation mapping only.
3. World policy files under ``data/worlds/<world_id>/policies/**`` are not runtime authority.

Artifact Import Workflow
------------------------

Use deterministic publish artifacts as the only supported import/bootstrap path:

.. code-block:: bash

   mud-server import-policy-artifact --artifact-path /abs/path/publish_<manifest_hash>.json

Optional (import without activation):

.. code-block:: bash

   mud-server import-policy-artifact --artifact-path /abs/path/publish_<manifest_hash>.json --no-activate

init-db Bootstrap Behavior
--------------------------

``mud-server init-db`` bootstraps policies by importing ``latest.json`` pointer artifacts from:

``<policy-exports-root>/worlds/<world_id>/world/latest.json``

Policy exports root resolution order:

1. ``MUD_POLICY_EXPORTS_ROOT`` environment variable.
2. Sibling repository next to the active CLI repo root (derived from current working directory).
3. Sibling repository next to ``PROJECT_ROOT`` (historical default).

If ``latest.json`` is missing for a world, bootstrap logs a warning and continues.
If ``latest.json`` exists but points to a missing artifact file, that world import fails and is reported.
If one or more world imports fail, ``init-db`` exits non-zero.

Use ``mud-server init-db --skip-policy-import`` when you need schema/init only.

Breaking Change Summary
-----------------------

The following legacy file-import commands were removed:

1. ``import-species-policies``
2. ``import-layer2-policies``
3. ``import-tone-prompt-policies``
4. ``import-world-policies``

Command Replacement Table
-------------------------

.. list-table::
   :header-rows: 1

   * - Removed Command
     - Replacement
   * - ``mud-server import-species-policies --world-id <world>``
     - ``mud-server import-policy-artifact --artifact-path <publish_*.json>``
   * - ``mud-server import-layer2-policies --world-id <world>``
     - ``mud-server import-policy-artifact --artifact-path <publish_*.json>``
   * - ``mud-server import-tone-prompt-policies --world-id <world>``
     - ``mud-server import-policy-artifact --artifact-path <publish_*.json>``
   * - ``mud-server import-world-policies --world-id <world>``
     - ``mud-server import-policy-artifact --artifact-path <publish_*.json>``
