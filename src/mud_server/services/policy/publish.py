"""Deterministic publish and mirror artifact services.

This module materializes non-authoritative exchange artifacts from canonical
DB state selected by Layer 3 activation pointers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pipeworks_ipc import compute_payload_hash

from mud_server.db import policy_repo

from .activation import resolve_effective_policy_activations
from .constants import (
    _POLICY_EXPORT_LATEST_FILENAME,
    _POLICY_EXPORT_SCHEMA_VERSION,
    _POLICY_EXPORT_WORLD_DIRNAME,
    _POLICY_SCHEMA_VERSION_V1,
)
from .errors import PolicyServiceError
from .hashing import compute_artifact_hash
from .paths import resolve_policy_export_root
from .types import ActivationScope
from .utils import ensure_world_exists, now_iso


def publish_scope(*, scope: ActivationScope, actor: str) -> dict[str, Any]:
    """Build and persist one deterministic publish manifest for a scope."""
    ensure_world_exists(scope.world_id)
    activations = resolve_effective_policy_activations(scope=scope)

    manifest_items: list[dict[str, Any]] = []
    for activation in activations:
        policy = policy_repo.get_policy(
            policy_id=str(activation["policy_id"]),
            variant=str(activation["variant"]),
        )
        if policy is None:
            raise PolicyServiceError(
                status_code=409,
                code="POLICY_PUBLISH_REFERENCE_MISSING",
                detail=(
                    "Activation references a missing policy variant: "
                    f"{activation['policy_id']}:{activation['variant']}"
                ),
            )

        manifest_items.append(
            {
                "policy_id": policy["policy_id"],
                "policy_type": policy["policy_type"],
                "namespace": policy["namespace"],
                "policy_key": policy["policy_key"],
                "variant": policy["variant"],
                "schema_version": policy["schema_version"],
                "policy_version": policy["policy_version"],
                "status": policy["status"],
                "content_hash": policy["content_hash"],
                "updated_at": policy["updated_at"],
            }
        )

    manifest_items.sort(
        key=lambda item: (item["policy_type"], item["namespace"], item["policy_key"])
    )
    items_hash = str(compute_payload_hash({"items": manifest_items}))
    manifest_hash = str(
        compute_payload_hash(
            {
                "world_id": scope.world_id,
                "client_profile": scope.client_profile or None,
                "items_hash": items_hash,
                "item_count": len(manifest_items),
            }
        )
    )

    generated_at = now_iso()
    manifest = {
        "world_id": scope.world_id,
        "client_profile": scope.client_profile or None,
        "generated_at": generated_at,
        "item_count": len(manifest_items),
        "items_hash": items_hash,
        "manifest_hash": manifest_hash,
        "items": manifest_items,
    }
    publish_run_id = policy_repo.insert_publish_run(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
        actor=actor,
        manifest=manifest,
        created_at=generated_at,
    )
    artifact = _materialize_publish_artifact(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
        manifest=manifest,
    )
    return {
        "publish_run_id": publish_run_id,
        "manifest": manifest,
        "artifact": artifact,
    }


def get_publish_run(*, publish_run_id: int) -> dict[str, Any]:
    """Get one publish run plus deterministic artifact metadata."""
    run_row = policy_repo.get_publish_run(publish_run_id=publish_run_id)
    if run_row is None:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_PUBLISH_RUN_NOT_FOUND",
            detail=f"Publish run not found: {publish_run_id}",
        )

    world_id = str(run_row["world_id"])
    client_profile = str(run_row["client_profile"] or "")
    manifest = _normalize_manifest_for_export(
        world_id=world_id,
        client_profile=client_profile,
        manifest=run_row["manifest"],
    )
    artifact = _materialize_publish_artifact(
        world_id=world_id,
        client_profile=client_profile,
        manifest=manifest,
    )
    return {
        "publish_run_id": int(run_row["publish_run_id"]),
        "world_id": world_id,
        "client_profile": client_profile or None,
        "actor": str(run_row["actor"]),
        "created_at": str(run_row["created_at"]),
        "manifest": manifest,
        "artifact": artifact,
    }


def _normalize_manifest_for_export(
    *,
    world_id: str,
    client_profile: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Return normalized manifest with deterministic hash fields populated."""
    normalized = dict(manifest)
    items_raw = normalized.get("items")
    if not isinstance(items_raw, list):
        items_raw = []
    items: list[dict[str, Any]] = [dict(item) for item in items_raw if isinstance(item, dict)]
    items.sort(
        key=lambda item: (
            str(item.get("policy_type", "")),
            str(item.get("namespace", "")),
            str(item.get("policy_key", "")),
        )
    )
    normalized["items"] = items
    normalized["item_count"] = int(normalized.get("item_count", len(items)))
    normalized["world_id"] = world_id
    normalized["client_profile"] = client_profile or None

    items_hash = str(normalized.get("items_hash") or compute_payload_hash({"items": items}))
    normalized["items_hash"] = items_hash
    manifest_hash = str(
        normalized.get("manifest_hash")
        or compute_payload_hash(
            {
                "world_id": world_id,
                "client_profile": client_profile or None,
                "items_hash": items_hash,
                "item_count": normalized["item_count"],
            }
        )
    )
    normalized["manifest_hash"] = manifest_hash
    return normalized


def _materialize_publish_artifact(
    *,
    world_id: str,
    client_profile: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Write deterministic exchange artifact and return artifact metadata."""
    normalized_manifest = _normalize_manifest_for_export(
        world_id=world_id,
        client_profile=client_profile,
        manifest=manifest,
    )
    variants = _build_export_variants(items=normalized_manifest["items"])
    variants_hash = str(compute_payload_hash({"variants": variants}))

    artifact_payload: dict[str, Any] = {
        "export_schema_version": _POLICY_EXPORT_SCHEMA_VERSION,
        "policy_authority": "mud_server",
        "mirror_mode": "non_authoritative",
        "world_id": world_id,
        "client_profile": client_profile or None,
        "manifest_hash": normalized_manifest["manifest_hash"],
        "items_hash": normalized_manifest["items_hash"],
        "item_count": normalized_manifest["item_count"],
        "items": normalized_manifest["items"],
        "variants_hash": variants_hash,
        "variants": variants,
    }
    artifact_hash = compute_artifact_hash(artifact=artifact_payload)
    artifact_payload["artifact_hash"] = artifact_hash

    artifact_path = _publish_artifact_path(
        world_id=world_id,
        client_profile=client_profile,
        manifest_hash=str(normalized_manifest["manifest_hash"]),
    )
    export_root = resolve_policy_export_root()
    latest_path = artifact_path.parent / _POLICY_EXPORT_LATEST_FILENAME
    artifact_path_for_latest = str(artifact_path)
    try:
        artifact_path_for_latest = str(artifact_path.relative_to(export_root))
    except ValueError:
        # Keep absolute fallback if artifact path is not under export root.
        artifact_path_for_latest = str(artifact_path)

    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(artifact_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        latest_payload = {
            "policy_authority": "mud_server",
            "mirror_mode": "non_authoritative",
            "world_id": world_id,
            "scope": _scope_segment(client_profile),
            "client_profile": client_profile or None,
            "manifest_hash": normalized_manifest["manifest_hash"],
            "items_hash": normalized_manifest["items_hash"],
            "variants_hash": variants_hash,
            "item_count": normalized_manifest["item_count"],
            "artifact_hash": artifact_hash,
            "artifact_file": artifact_path.name,
            "artifact_path": artifact_path_for_latest,
        }
        latest_path.write_text(
            json.dumps(latest_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        raise PolicyServiceError(
            status_code=500,
            code="POLICY_PUBLISH_ARTIFACT_WRITE_ERROR",
            detail=str(exc),
        ) from exc

    return {
        "artifact_hash": artifact_hash,
        "artifact_path": str(artifact_path),
        "latest_path": str(latest_path),
    }


def _publish_artifact_path(*, world_id: str, client_profile: str, manifest_hash: str) -> Path:
    """Return deterministic artifact path under exchange-repo layout."""
    export_root = _resolve_policy_export_root()
    scope_segment = _scope_segment(client_profile)
    filename = f"publish_{manifest_hash}.json"
    return export_root / _POLICY_EXPORT_WORLD_DIRNAME / world_id / scope_segment / filename


def _build_export_variants(*, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build canonical variant payloads used by import/export round-trips."""
    variants: list[dict[str, Any]] = []
    for item in items:
        policy_id = str(item.get("policy_id", ""))
        variant = str(item.get("variant", ""))
        policy_row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
        if policy_row is None:
            # Historical publish runs may reference variants deleted later.
            # We preserve inspectability by emitting a non-materialized row.
            variants.append(
                {
                    "policy_id": policy_id,
                    "policy_type": str(item.get("policy_type", "")),
                    "namespace": str(item.get("namespace", "")),
                    "policy_key": str(item.get("policy_key", "")),
                    "variant": variant,
                    "schema_version": str(item.get("schema_version", _POLICY_SCHEMA_VERSION_V1)),
                    "policy_version": int(item.get("policy_version", 1) or 1),
                    "status": str(item.get("status", "candidate")),
                    "content": {},
                    "content_hash": str(item.get("content_hash", "")),
                    "updated_at": str(item.get("updated_at", "")),
                    "updated_by": "unknown",
                    "materialized": False,
                }
            )
            continue

        variants.append(
            {
                "policy_id": str(policy_row["policy_id"]),
                "policy_type": str(policy_row["policy_type"]),
                "namespace": str(policy_row["namespace"]),
                "policy_key": str(policy_row["policy_key"]),
                "variant": str(policy_row["variant"]),
                "schema_version": str(policy_row["schema_version"]),
                "policy_version": int(policy_row["policy_version"]),
                "status": str(policy_row["status"]),
                "content": dict(policy_row["content"]),
                "content_hash": str(policy_row["content_hash"]),
                "updated_at": str(policy_row["updated_at"]),
                "updated_by": str(policy_row["updated_by"]),
                "materialized": True,
            }
        )

    variants.sort(
        key=lambda row: (
            str(row.get("policy_type", "")),
            str(row.get("namespace", "")),
            str(row.get("policy_key", "")),
            str(row.get("variant", "")),
        )
    )
    return variants


def _resolve_policy_export_root() -> Path:
    """Resolve root directory for publish mirror artifacts.

    Resolution order:
    1. ``MUD_POLICY_EXPORTS_ROOT`` environment variable
    2. sibling repo near active working repo
    3. sibling repo near ``PROJECT_ROOT`` default
    """
    return resolve_policy_export_root()


def _scope_segment(client_profile: str) -> str:
    """Return stable filesystem path segment for a client-profile scope."""
    if not client_profile:
        return "world"
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", client_profile).strip("._")
    if not sanitized:
        sanitized = "client"
    return f"client_{sanitized}"
