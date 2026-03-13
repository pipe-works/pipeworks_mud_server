Axis Descriptor Lab Integration
===============================

Overview
--------

The mud server exposes a lab-facing API under ``/api/lab`` so the
Axis Descriptor Lab can treat the server as the canonical source of
truth for prompt templates and policy packages. The lab remains a
text-box driven experimentation tool, but canonical artifacts live in
world packages owned by the mud server.

The integration is intentionally conservative:

* canonical files remain server-owned
* drafts are created under ``policies/drafts/``
* prompt promotion is create-only for canonical prompt files
* policy-bundle promotion rewrites the canonical YAML package explicitly
* promotion reloads the relevant runtime service immediately

Canonical, Draft, and Active
----------------------------

Prompt artifacts use three related states:

``canonical``
   A prompt file under ``data/worlds/<world_id>/policies/*.txt`` that is
   owned by the mud server world package.

``draft``
   A lab-created prompt or policy file under
   ``data/worlds/<world_id>/policies/drafts/``. Drafts are safe working
   copies and are never used automatically by gameplay.

``active``
   For prompts only, the canonical file currently referenced by
   ``world.json -> translation_layer.prompt_template_path``. This is the
   default prompt used by the running translation service for future chat
   translation requests.

Prompt Workflow
---------------

The prompt endpoints let the lab:

* list canonical prompt templates for a world
* load existing server drafts
* create a new draft without overwriting any file
* promote a draft into a new canonical prompt file

Prompt promotion performs all of the following in one explicit action:

1. reads the saved draft from ``policies/drafts/<name>.txt``
2. writes a new canonical ``policies/<target>.txt`` file
3. updates ``world.json -> translation_layer.prompt_template_path``
4. reloads the running world's translation service

No full server restart is required. In-flight requests may still finish
with the previous prompt, but subsequent translation requests use the new
active prompt immediately.

Policy Bundle Workflow
----------------------

The policy bundle endpoints normalize the canonical policy package into a
single JSON document for the lab, then allow the lab to round-trip edits
as server-side drafts.

The canonical files are still:

* ``policies/axis/axes.yaml``
* ``policies/axis/thresholds.yaml``
* ``policies/axis/resolution.yaml``

Promotion of a policy bundle draft:

1. validates the normalized draft payload
2. checks that the bundle still belongs to the selected world
3. rewrites the canonical YAML files in deterministic machine format
4. reloads the world's axis engine

This means comments or hand-formatting in the canonical YAML files are not
preserved across promotion. The draft JSON remains on disk after promotion.

API Surface
-----------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Endpoint
     - Purpose
   * - ``GET /api/lab/worlds``
     - List worlds visible to the lab.
   * - ``GET /api/lab/world-prompts/{world_id}``
     - List canonical prompt templates and mark the active prompt.
   * - ``GET /api/lab/world-prompts/{world_id}/drafts``
     - List saved prompt drafts.
   * - ``GET /api/lab/world-prompts/{world_id}/drafts/{name}``
     - Load one saved prompt draft.
   * - ``POST /api/lab/world-prompts/{world_id}/drafts``
     - Create a new prompt draft under ``policies/drafts``.
   * - ``POST /api/lab/world-prompts/{world_id}/drafts/{name}/promote``
     - Promote one prompt draft into a new canonical active prompt.
   * - ``GET /api/lab/world-policy-bundle/{world_id}``
     - Return the canonical policy package as a normalized JSON bundle.
   * - ``GET /api/lab/world-policy-bundle/{world_id}/drafts``
     - List saved policy bundle drafts.
   * - ``GET /api/lab/world-policy-bundle/{world_id}/drafts/{name}``
     - Load one saved policy bundle draft.
   * - ``POST /api/lab/world-policy-bundle/{world_id}/drafts``
     - Create a new policy bundle draft under ``policies/drafts``.
   * - ``POST /api/lab/world-policy-bundle/{world_id}/drafts/{name}/promote``
     - Promote one policy bundle draft back into canonical YAML files.

Operational Notes
-----------------

* These endpoints are intended for the Axis Descriptor Lab, not a general
  multi-user editing surface.
* Draft creation is create-only; filename collisions are rejected.
* Prompt promotion never overwrites an existing canonical prompt file.
* Policy promotion rewrites the canonical YAML package on purpose.
* Clients may need to refresh their prompt or artifact lists after a
  promotion even though the server runtime is already updated.
