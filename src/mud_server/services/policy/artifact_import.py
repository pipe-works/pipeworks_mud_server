"""Canonical publish-artifact import workflows.

This module ingests deterministic export artifacts back into canonical DB
policy state. It is idempotent and never reads world policy files.
"""

from __future__ import annotations

from typing import Any

from pipeworks_ipc import compute_payload_hash

from mud_server.db import policy_repo

from .activation import set_policy_activation
from .errors import PolicyServiceError
from .hashing import compute_artifact_hash
from .types import ActivationScope, ArtifactImportEntry, ArtifactImportSummary, PolicyIdentity
from .utils import ensure_world_exists
from .validation import is_policy_variant_unchanged, parse_policy_id, upsert_policy_variant


def import_published_artifact(
    *,
    artifact: dict[str, Any],
    actor: str,
    activate: bool,
) -> ArtifactImportSummary:
    """Import one publish artifact into canonical policy DB rows.

    Workflow:
    1. Validate artifact envelope + integrity hashes.
    2. Upsert canonical variants from ``artifact.variants``.
    3. Optionally apply activation pointers for artifact scope.
    """
    normalized_actor = actor.strip() or "policy-importer"
    if not isinstance(artifact, dict):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_ARTIFACT_INVALID",
            detail="Artifact payload must be a JSON object.",
        )

    provided_artifact_hash = str(artifact.get("artifact_hash", "")).strip()
    calculated_artifact_hash = compute_artifact_hash(artifact=artifact)
    if provided_artifact_hash and provided_artifact_hash != calculated_artifact_hash:
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_IMPORT_ARTIFACT_HASH_MISMATCH",
            detail=(
                "Artifact integrity check failed: artifact_hash mismatch "
                f"(provided={provided_artifact_hash!r}, calculated={calculated_artifact_hash!r})."
            ),
        )

    world_id = str(artifact.get("world_id", "")).strip()
    if not world_id:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_ARTIFACT_INVALID",
            detail="Artifact field world_id must be a non-empty string.",
        )
    ensure_world_exists(world_id)

    client_profile_raw = artifact.get("client_profile")
    client_profile = str(client_profile_raw or "").strip()
    scope = ActivationScope(world_id=world_id, client_profile=client_profile)

    variants_raw = artifact.get("variants")
    if not isinstance(variants_raw, list):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_ARTIFACT_INVALID",
            detail="Artifact field variants must be a list.",
        )
    variants_payload = [row for row in variants_raw if isinstance(row, dict)]
    if len(variants_payload) != len(variants_raw):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_ARTIFACT_INVALID",
            detail="Artifact field variants must contain only object entries.",
        )

    variants_hash = str(
        artifact.get("variants_hash") or compute_payload_hash({"variants": variants_payload})
    )
    provided_variants_hash = str(artifact.get("variants_hash", "")).strip()
    if provided_variants_hash and provided_variants_hash != variants_hash:
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_IMPORT_ARTIFACT_HASH_MISMATCH",
            detail=(
                "Artifact integrity check failed: variants_hash mismatch "
                f"(provided={provided_variants_hash!r}, calculated={variants_hash!r})."
            ),
        )

    entries: list[ArtifactImportEntry] = []
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    activation_targets: dict[str, str] = {}

    for index, row in _ordered_variants_for_import(variants_payload):
        prefix = f"variants[{index}]"
        policy_id: str | None = None
        variant: str | None = None
        try:
            policy_id_raw = row.get("policy_id")
            variant_raw = row.get("variant")
            if not isinstance(policy_id_raw, str) or not policy_id_raw.strip():
                raise ValueError(f"{prefix}.policy_id must be a non-empty string.")
            if not isinstance(variant_raw, str) or not variant_raw.strip():
                raise ValueError(f"{prefix}.variant must be a non-empty string.")
            policy_id = policy_id_raw.strip()
            variant = variant_raw.strip()
            identity = parse_policy_id(policy_id)

            _validate_artifact_identity_fields(prefix=prefix, row=row, identity=identity)
            schema_version = _required_non_empty_string(
                prefix=prefix,
                row=row,
                field_name="schema_version",
            )
            policy_version = _required_positive_int(
                prefix=prefix,
                row=row,
                field_name="policy_version",
            )
            status = _required_non_empty_string(prefix=prefix, row=row, field_name="status")
            content = row.get("content")
            if not isinstance(content, dict):
                raise ValueError(f"{prefix}.content must be an object.")

            existing_row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
            if is_policy_variant_unchanged(
                existing_row=existing_row,
                schema_version=schema_version,
                policy_version=policy_version,
                status=status,
                content=content,
            ):
                skipped_count += 1
                entries.append(
                    ArtifactImportEntry(
                        policy_id=policy_id,
                        variant=variant,
                        action="skipped",
                        detail=f"unchanged {policy_id}:{variant}",
                    )
                )
                activation_targets[policy_id] = variant
                continue

            upsert_policy_variant(
                policy_id=policy_id,
                variant=variant,
                schema_version=schema_version,
                policy_version=policy_version,
                status=status,
                content=content,
                updated_by=normalized_actor,
            )
            action = "imported" if existing_row is None else "updated"
            if action == "imported":
                imported_count += 1
            else:
                updated_count += 1
            entries.append(
                ArtifactImportEntry(
                    policy_id=policy_id,
                    variant=variant,
                    action=action,
                    detail=f"{action} {policy_id}:{variant}",
                )
            )
            activation_targets[policy_id] = variant
        except (PolicyServiceError, ValueError, TypeError) as exc:
            error_count += 1
            entries.append(
                ArtifactImportEntry(
                    policy_id=policy_id,
                    variant=variant,
                    action="error",
                    detail=str(exc),
                )
            )

    activated_count = 0
    activation_skipped_count = 0
    if activate and activation_targets:
        current_activations = {
            str(row["policy_id"]): str(row["variant"])
            for row in policy_repo.list_policy_activations(
                world_id=scope.world_id,
                client_profile=scope.client_profile,
            )
        }
        for policy_id in sorted(activation_targets):
            target_variant = activation_targets[policy_id]
            if current_activations.get(policy_id) == target_variant:
                activation_skipped_count += 1
                continue
            try:
                set_policy_activation(
                    scope=scope,
                    policy_id=policy_id,
                    variant=target_variant,
                    activated_by=normalized_actor,
                )
                current_activations[policy_id] = target_variant
                activated_count += 1
            except PolicyServiceError as exc:
                error_count += 1
                entries.append(
                    ArtifactImportEntry(
                        policy_id=policy_id,
                        variant=target_variant,
                        action="error",
                        detail=f"activation failed: {exc.detail}",
                    )
                )

    return ArtifactImportSummary(
        world_id=world_id,
        client_profile=client_profile,
        activate=activate,
        item_count=len(variants_payload),
        imported_count=imported_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        activated_count=activated_count,
        activation_skipped_count=activation_skipped_count,
        manifest_hash=str(artifact.get("manifest_hash", "")).strip(),
        items_hash=str(artifact.get("items_hash", "")).strip(),
        artifact_hash=provided_artifact_hash or calculated_artifact_hash,
        variants_hash=variants_hash,
        entries=entries,
    )


def _ordered_variants_for_import(
    variants_payload: list[dict[str, Any]],
) -> list[tuple[int, dict[str, Any]]]:
    """Return variants ordered for deterministic, dependency-safe import.

    Artifact payloads may contain variants in any order. Layer 2 policy types
    (`descriptor_layer`, `registry`) validate references to Layer 1 rows, so we
    import Layer 1 rows first to prevent false reference-missing errors during
    clean bootstrap imports.

    The original index is preserved for error labeling (`variants[i]`), making
    diagnostics refer back to the source artifact order.
    """
    indexed_rows = list(enumerate(variants_payload))
    indexed_rows.sort(
        key=lambda pair: (_import_priority_for_policy_row(pair[1]), int(pair[0])),
    )
    return indexed_rows


def _import_priority_for_policy_row(row: dict[str, Any]) -> int:
    """Return dependency priority for one artifact variant row.

    Lower numbers import earlier. Unknown/malformed rows are placed last so the
    normal per-row validation path can report clear errors.
    """
    policy_id = row.get("policy_id")
    if not isinstance(policy_id, str) or ":" not in policy_id:
        return 99
    policy_type = policy_id.split(":", 1)[0].strip()
    priority_by_type = {
        "image_block": 10,
        "species_block": 20,
        "clothing_block": 30,
        "prompt": 40,
        "tone_profile": 50,
        "axis_bundle": 60,
        "manifest_bundle": 70,
        "descriptor_layer": 80,
        "registry": 90,
    }
    return int(priority_by_type.get(policy_type, 99))


def _required_non_empty_string(*, prefix: str, row: dict[str, Any], field_name: str) -> str:
    """Extract required non-empty string field from one artifact variant row."""
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{prefix}.{field_name} must be a non-empty string.")
    return value.strip()


def _required_positive_int(*, prefix: str, row: dict[str, Any], field_name: str) -> int:
    """Extract required integer >= 1 field from one artifact variant row."""
    value = row.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{prefix}.{field_name} must be an integer >= 1.")
    return int(value)


def _validate_artifact_identity_fields(
    *,
    prefix: str,
    row: dict[str, Any],
    identity: PolicyIdentity,
) -> None:
    """Validate optional expanded identity fields against policy_id-derived identity."""
    checks = (
        ("policy_type", identity.policy_type),
        ("namespace", identity.namespace),
        ("policy_key", identity.policy_key),
    )
    for field_name, expected_value in checks:
        if field_name not in row:
            continue
        actual_value = row.get(field_name)
        if not isinstance(actual_value, str) or actual_value.strip() != expected_value:
            raise ValueError(
                f"{prefix}.{field_name} must match policy_id-derived value {expected_value!r}."
            )
