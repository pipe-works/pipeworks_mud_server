# Policy Service Package Design

This document defines the architecture boundaries for the policy service package at
`src/mud_server/services/policy/`.

## Goals

1. Keep canonical policy operations DB/artifact-first.
2. Keep `mud_server.services.policy_service` as a stable facade for canonical callers.
3. Remove legacy world-file import/read pathways from runtime and service surfaces.

## Canonical Invariants

1. Canonical policy identity is represented by policy object fields and stored in SQLite.
2. Activation (`policy_activation`) and variant status (`policy_variant.status`) are distinct concerns.
3. Runtime effective policy resolution is computed from activation mappings, not file paths.
4. Publish artifacts are deterministic exchange outputs, not runtime authority.
5. Artifact import is idempotent at policy identity + variant granularity.

## Package Modules

### `types.py`

Defines shared typed structures used across policy modules, including:

- `ActivationScope`
- `EffectiveAxisBundle`

### `errors.py`

Defines canonical policy service exceptions consumed by facade and route layers.

### `constants.py`

Defines canonical constants used by policy validation and import/publish paths.

### `utils.py`

Implements normalization and shared utility helpers used across modules.

### `hashing.py`

Owns deterministic content hashing helpers used by upsert and publish flows.

### `validation.py`

Owns policy content validation and policy-type specific rules.

### `activation.py`

Owns activation writes, activation listing, and effective activation overlays.

### `runtime_resolution.py`

Owns runtime effective resolution for policy variants, prompt templates, and axis bundle payloads.

### `publish.py`

Owns deterministic publish runs and manifest generation.

### `artifact_import.py`

Owns canonical artifact ingestion into policy tables.

## Facade Contract

`src/mud_server/services/policy_service.py` provides compatibility wrappers for canonical APIs only.

Supported canonical facade exports:

- `list_policies`
- `get_policy`
- `validate_policy_variant`
- `upsert_policy_variant`
- `set_policy_activation`
- `list_policy_activations`
- `resolve_effective_policy_activations`
- `get_effective_policy_variant`
- `resolve_effective_prompt_template`
- `resolve_effective_axis_bundle`
- `publish_scope`
- `get_publish_run`
- `import_published_artifact`
- `parse_scope`

Removed legacy exports are intentionally absent.

## Legacy Removal Scope

Removed from service/CLI surface:

1. Legacy world-policy file import entry points.
2. Legacy path-to-policy mapping helpers.
3. Legacy runtime fallback assumptions that imply file-path canonicality.

## Testing Expectations

1. Unit coverage for validation, activation overlays, runtime resolution, publish, and artifact import.
2. Integration coverage for policy API routes and CLI retained commands.
3. Regression coverage proving DB/runtime behavior does not depend on legacy world policy files.
