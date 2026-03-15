Axis Descriptor Lab Integration
===============================

Overview
--------

The mud server exposes a lab-facing API under ``/api/lab`` for
runtime diagnostics and deterministic prompt compilation.

Canonical authority is DB-first:

* ``policy_item`` + ``policy_variant`` store policy identities and content
* ``policy_activation`` selects effective runtime variants by scope
* runtime/lab endpoints read effective activated variants from DB
* world ``policies/*`` files are migration/import inputs or exchange outputs,
  not runtime authority

Active Lab API Surface
----------------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Endpoint
     - Purpose
   * - ``GET /api/lab/worlds``
     - List worlds visible to the lab and whether translation is enabled.
   * - ``GET /api/lab/world-config/{world_id}``
     - Return translation runtime settings for one world.
   * - ``GET /api/lab/world-image-policy-bundle/{world_id}``
     - Return DB-resolved image policy bundle metadata for active scope.
   * - ``POST /api/lab/compile-image-prompt``
     - Compile deterministic image prompt text from active canonical policy variants.
   * - ``POST /api/lab/translate``
     - Translate one OOC message using active canonical runtime prompt config.

Removed Legacy Routes (Breaking)
--------------------------------

The following file-authoring routes were intentionally removed:

* ``/api/lab/world-prompts/*``
* ``/api/lab/world-policy-bundle/*``

This removal prevents file-path editing flows from being misread as canonical
runtime authoring behavior.

Operational Flow (DB-Only)
--------------------------

1. Initialize schema and world catalog:

   .. code-block:: bash

      mud-server init-db

2. Import canonical artifact into DB (activation is enabled by default):

   .. code-block:: bash

      mud-server import-policy-artifact --artifact-path /path/to/artifact.json

   To import without applying activation pointers:

   .. code-block:: bash

      mud-server import-policy-artifact --artifact-path /path/to/artifact.json --no-activate

3. Verify effective activation pointers:

   .. code-block:: bash

      curl -s "http://127.0.0.1:8000/api/policy-activations?scope=pipeworks_web&effective=true&session_id=<sid>"

4. Inspect image policy contract from DB:

   .. code-block:: bash

      curl -s "http://127.0.0.1:8000/api/lab/world-image-policy-bundle/pipeworks_web?session_id=<sid>"

5. Compile deterministic prompt from active DB policy state:

   .. code-block:: bash

      curl -s -X POST "http://127.0.0.1:8000/api/lab/compile-image-prompt" \
        -H "Content-Type: application/json" \
        -d '{
              "session_id": "<sid>",
              "world_id": "pipeworks_web",
              "species": "goblin",
              "gender": "male",
              "axes": {"demeanor": {"label": "timid", "score": 0.07}}
            }'

6. Publish deterministic artifact for sharing/mirroring:

   .. code-block:: bash

      curl -s -X POST "http://127.0.0.1:8000/api/policy-publish?session_id=<sid>" \
        -H "Content-Type: application/json" \
        -d '{"world_id":"pipeworks_web"}'

Artifacts are exchange outputs and should be committed in
``pipe-works-world-policies``. They are not runtime authority.
