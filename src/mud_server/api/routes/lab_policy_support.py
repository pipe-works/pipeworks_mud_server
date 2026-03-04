"""Policy bundle artifact helpers for the lab router."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException

from mud_server.api.models import (
    LabPolicyBundleDraftCreateRequest,
    LabPolicyBundleDraftCreateResponse,
    LabPolicyBundleDraftDocument,
    LabPolicyBundleDraftListResponse,
    LabPolicyBundleDraftPayload,
    LabPolicyBundleDraftPromoteRequest,
    LabPolicyBundleDraftPromoteResponse,
    LabPolicyBundleDraftSummary,
    LabPolicyBundleResponse,
)
from mud_server.api.routes.lab_support import load_world_json, require_world_root

if TYPE_CHECKING:
    from mud_server.core.world import World


def validate_policy_draft_name(name: str) -> str:
    """Validate and normalize a policy bundle draft name."""

    normalized = name.strip()
    if not re.fullmatch(r"^[a-z0-9][a-z0-9_-]*$", normalized):
        raise HTTPException(
            status_code=400,
            detail=(
                "Draft names must use lowercase letters, numbers, underscores, or "
                "hyphens and must not include a file extension."
            ),
        )
    return normalized


def policy_policies_dir(world: World, world_id: str) -> Path:
    """Return the canonical policies directory for one world."""

    world_root = require_world_root(
        world,
        unavailable_detail=f"Axis policy files unavailable for world {world_id!r}.",
    )
    policies_dir = world_root / "policies"
    if not policies_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Axis policy files unavailable for world {world_id!r}.",
        )
    return policies_dir


def create_world_policy_bundle_draft(
    world: World,
    world_id: str,
    req: LabPolicyBundleDraftCreateRequest,
    *,
    build_policy_bundle: Callable[[str, Path], LabPolicyBundleResponse],
) -> LabPolicyBundleDraftCreateResponse:
    """Create one normalized policy bundle draft under ``policies/drafts``."""

    draft_name = validate_policy_draft_name(req.draft_name)
    if req.content.world_id != world_id:
        raise HTTPException(
            status_code=400,
            detail="Draft content world_id must match the target world_id.",
        )

    world_root = require_world_root(
        world,
        unavailable_detail=f"Axis policy files unavailable for world {world_id!r}.",
    )
    build_policy_bundle(world_id, world_root)

    drafts_dir = world_root / "policies" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    target = drafts_dir / f"{draft_name}.json"
    if target.exists():
        raise HTTPException(
            status_code=409,
            detail=f"A policy bundle draft named {draft_name!r} already exists.",
        )

    target.write_text(
        json.dumps(req.content.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return LabPolicyBundleDraftCreateResponse(
        name=draft_name,
        origin_path=f"policies/drafts/{draft_name}.json",
        world_id=req.content.world_id,
        version=req.content.version,
        based_on_name=req.based_on_name,
    )


def list_world_policy_bundle_drafts(
    world: World,
    world_id: str,
    *,
    build_policy_bundle: Callable[[str, Path], LabPolicyBundleResponse],
) -> LabPolicyBundleDraftListResponse:
    """List saved normalized policy bundle drafts for one world."""

    world_root = require_world_root(
        world,
        unavailable_detail=f"Axis policy files unavailable for world {world_id!r}.",
    )
    build_policy_bundle(world_id, world_root)

    drafts_dir = world_root / "policies" / "drafts"
    if not drafts_dir.is_dir():
        return LabPolicyBundleDraftListResponse(world_id=world_id, drafts=[])

    drafts: list[LabPolicyBundleDraftSummary] = []
    for draft_file in sorted(drafts_dir.glob("*.json")):
        try:
            raw = json.loads(draft_file.read_text(encoding="utf-8"))
            payload = LabPolicyBundleDraftPayload.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if payload.world_id != world_id:
            continue
        drafts.append(
            LabPolicyBundleDraftSummary(
                name=draft_file.stem,
                origin_path=f"policies/drafts/{draft_file.name}",
                world_id=payload.world_id,
                version=payload.version,
            )
        )

    return LabPolicyBundleDraftListResponse(world_id=world_id, drafts=drafts)


def get_world_policy_bundle_draft(
    world: World,
    world_id: str,
    draft_name: str,
    *,
    build_policy_bundle: Callable[[str, Path], LabPolicyBundleResponse],
) -> LabPolicyBundleDraftDocument:
    """Load one normalized policy bundle draft from disk."""

    normalized_name = validate_policy_draft_name(draft_name)
    world_root = require_world_root(
        world,
        unavailable_detail=f"Axis policy files unavailable for world {world_id!r}.",
    )
    build_policy_bundle(world_id, world_root)

    target = world_root / "policies" / "drafts" / f"{normalized_name}.json"
    if not target.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Policy bundle draft {normalized_name!r} not found for world {world_id!r}.",
        )

    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        payload = LabPolicyBundleDraftPayload.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError) as err:
        raise HTTPException(
            status_code=500,
            detail=f"Policy bundle draft {normalized_name!r} is invalid on disk.",
        ) from err

    if payload.world_id != world_id:
        raise HTTPException(
            status_code=409,
            detail=f"Policy bundle draft {normalized_name!r} belongs to a different world.",
        )

    return LabPolicyBundleDraftDocument(
        name=normalized_name,
        origin_path=f"policies/drafts/{normalized_name}.json",
        world_id=payload.world_id,
        version=payload.version,
        content=payload,
    )


def promote_world_policy_bundle_draft(
    world: World,
    world_id: str,
    draft_name: str,
    req: LabPolicyBundleDraftPromoteRequest,
    *,
    build_policy_bundle: Callable[[str, Path], LabPolicyBundleResponse],
    build_axes_yaml_payload: Callable[[LabPolicyBundleDraftPayload], dict],
    build_thresholds_yaml_payload: Callable[[LabPolicyBundleDraftPayload], dict],
    build_resolution_yaml_payload: Callable[[LabPolicyBundleDraftPayload], dict],
    write_yaml: Callable[[Path, dict], None],
    reload_world_axis_engine: Callable[[World, dict], None],
    validate_policy_bundle_active_axes: Callable[[World, dict, LabPolicyBundleDraftPayload], None],
    canonical_policy_source_files: Callable[[], list[str]],
    hash_policy_payload: Callable[[dict, dict], str],
) -> LabPolicyBundleDraftPromoteResponse:
    """Promote one policy bundle draft into canonical files."""

    _ = req
    normalized_name = validate_policy_draft_name(draft_name)
    policies_dir = policy_policies_dir(world, world_id)

    draft_path = policies_dir / "drafts" / f"{normalized_name}.json"
    if not draft_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Policy bundle draft {normalized_name!r} not found for world {world_id!r}.",
        )

    try:
        raw = json.loads(draft_path.read_text(encoding="utf-8"))
        payload = LabPolicyBundleDraftPayload.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError) as err:
        raise HTTPException(
            status_code=500,
            detail=f"Policy bundle draft {normalized_name!r} is invalid on disk.",
        ) from err

    if payload.world_id != world_id:
        raise HTTPException(
            status_code=409,
            detail=f"Policy bundle draft {normalized_name!r} belongs to a different world.",
        )

    world_root = require_world_root(
        world,
        unavailable_detail=f"Axis policy files unavailable for world {world_id!r}.",
    )
    build_policy_bundle(world_id, world_root)

    _, world_data = load_world_json(
        world,
        unavailable_detail=f"Axis policy files unavailable for world {world_id!r}.",
    )
    validate_policy_bundle_active_axes(world, world_data, payload)

    axes_payload = build_axes_yaml_payload(payload)
    thresholds_payload = build_thresholds_yaml_payload(payload)
    resolution_payload = build_resolution_yaml_payload(payload)

    write_yaml(policies_dir / "axes.yaml", axes_payload)
    write_yaml(policies_dir / "thresholds.yaml", thresholds_payload)
    write_yaml(policies_dir / "resolution.yaml", resolution_payload)
    reload_world_axis_engine(world, world_data)

    return LabPolicyBundleDraftPromoteResponse(
        name=normalized_name,
        world_id=world_id,
        canonical_name=f"{world_id}_policy_bundle",
        source_files=canonical_policy_source_files(),
        version=payload.version,
        policy_hash=hash_policy_payload(axes_payload, thresholds_payload),
    )
