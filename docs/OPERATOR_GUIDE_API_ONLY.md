# Operator Guide: API-Only Canonical Policy Operations

## Canonical Source of Truth

1. Canonical policy authority is SQLite (`policy_item`, `policy_variant`, `policy_activation`, related audit tables).
2. Runtime reads effective policy state via Layer 3 activation mapping only.
3. World policy files under `data/worlds/<world_id>/policies/**` are not runtime authority.

## Artifact Import Workflow

Use deterministic publish artifacts as the only supported import/bootstrap path:

```bash
mud-server import-policy-artifact --artifact-path /abs/path/publish_<manifest_hash>.json
```

Optional:

```bash
mud-server import-policy-artifact --artifact-path /abs/path/publish_<manifest_hash>.json --no-activate
```

## init-db Bootstrap Behavior

`mud-server init-db` now bootstraps policies by importing `latest.json` pointer artifacts from
`pipe-works-world-policies/worlds/<world_id>/world/latest.json` (or from `MUD_POLICY_EXPORTS_ROOT`).

If the pointer is missing, bootstrap logs a warning and continues.

## Breaking Change Summary

The following legacy file-import commands were removed:

1. `import-species-policies`
2. `import-layer2-policies`
3. `import-tone-prompt-policies`
4. `import-world-policies`

## Command Replacement Table

| Removed Command | Replacement |
|---|---|
| `mud-server import-species-policies --world-id <world>` | `mud-server import-policy-artifact --artifact-path <publish_*.json>` |
| `mud-server import-layer2-policies --world-id <world>` | `mud-server import-policy-artifact --artifact-path <publish_*.json>` |
| `mud-server import-tone-prompt-policies --world-id <world>` | `mud-server import-policy-artifact --artifact-path <publish_*.json>` |
| `mud-server import-world-policies --world-id <world>` | `mud-server import-policy-artifact --artifact-path <publish_*.json>` |
