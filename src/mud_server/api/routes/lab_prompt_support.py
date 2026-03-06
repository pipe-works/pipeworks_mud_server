"""Prompt artifact helpers for the lab router."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from mud_server.api.models import (
    LabPromptDraftCreateRequest,
    LabPromptDraftCreateResponse,
    LabPromptDraftDocument,
    LabPromptDraftListResponse,
    LabPromptDraftPromoteRequest,
    LabPromptDraftPromoteResponse,
    LabPromptDraftSummary,
    LabPromptFile,
    LabWorldPromptsResponse,
)
from mud_server.api.routes.lab_support import (
    load_world_json,
    require_translation_world,
    require_world_root,
    write_world_json,
)
from mud_server.core.world import World
from mud_server.policies import PolicyManifestLoader


def validate_prompt_draft_name(name: str, *, detail_prefix: str = "Draft names") -> str:
    """Validate and normalize a prompt draft or target name."""

    normalized = name.strip()
    if not re.fullmatch(r"^[a-z0-9][a-z0-9_-]*$", normalized):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{detail_prefix} must use lowercase letters, numbers, underscores, or "
                "hyphens and must not include a file extension."
            ),
        )
    return normalized


def _prompt_policies_dir(world: World, world_id: str) -> Path:
    """Return the policies directory for prompt artifacts."""

    require_translation_world(world, world_id)
    world_root = require_world_root(
        world,
        unavailable_detail=f"Prompt files unavailable for world {world_id!r}.",
    )
    policies_dir = world_root / "policies"
    if not policies_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Prompt files unavailable for world {world_id!r}.",
        )
    return policies_dir


def list_world_prompts(world: World, world_id: str) -> LabWorldPromptsResponse:
    """List canonical prompt template files for one world."""

    service = require_translation_world(world, world_id)
    try:
        world_root = require_world_root(
            world,
            unavailable_detail=f"Prompt files unavailable for world {world_id!r}.",
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            return LabWorldPromptsResponse(world_id=world_id, prompts=[])
        raise

    policies_dir = world_root / "policies"
    if not policies_dir.is_dir():
        return LabWorldPromptsResponse(world_id=world_id, prompts=[])

    active_path = _resolve_active_prompt_template_path(
        world_root, world_id, service.config.prompt_template_path
    )
    prompts: list[LabPromptFile] = []
    for txt_file in sorted(policies_dir.rglob("*.txt")):
        # Draft artifacts are intentionally excluded from canonical prompt listing.
        if "drafts" in txt_file.parts:
            continue
        try:
            content = txt_file.read_text(encoding="utf-8")
        except OSError:
            continue
        rel_path = txt_file.relative_to(policies_dir).as_posix()
        rel = f"policies/{rel_path}"
        prompts.append(
            LabPromptFile(
                filename=rel_path,
                content=content,
                is_active=(rel == active_path),
            )
        )

    return LabWorldPromptsResponse(world_id=world_id, prompts=prompts)


def _resolve_active_prompt_template_path(
    world_root: Path, world_id: str, configured_active_path: str
) -> str:
    """Resolve active prompt path, preferring manifest path when available.

    During migration, worlds may have both:
    - legacy ``translation_layer.prompt_template_path`` in ``world.json``
    - manifest-defined ``translation.active_prompt.path``

    Manifest path is preferred when available so downstream tooling follows the
    new canonical policy source.
    """

    policy_root = world_root / "policies"
    manifest_path = policy_root / "manifest.yaml"
    if not manifest_path.exists():
        return configured_active_path

    loader = PolicyManifestLoader(worlds_root=world_root.parent)
    _payload, report = loader.load_from_world_root(world_id=world_id, world_root=world_root)
    manifest_prompt_path = report.referenced_paths.get("translation.active_prompt")
    if manifest_prompt_path:
        return manifest_prompt_path

    # TODO(refactor-cleanup): remove after manifest migration complete.
    # Fallback to world.json-configured prompt path while manifest adoption
    # is still in progress and some worlds may be partially migrated.
    return configured_active_path


def create_world_prompt_draft(
    world: World,
    world_id: str,
    req: LabPromptDraftCreateRequest,
) -> LabPromptDraftCreateResponse:
    """Create one prompt draft under ``policies/drafts``."""

    draft_name = validate_prompt_draft_name(req.draft_name)
    policies_dir = _prompt_policies_dir(world, world_id)

    canonical_target = policies_dir / f"{draft_name}.txt"
    drafts_dir = policies_dir / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    target = drafts_dir / f"{draft_name}.txt"
    if canonical_target.exists() or target.exists():
        raise HTTPException(
            status_code=409,
            detail=f"A prompt draft named {draft_name!r} already exists.",
        )

    target.write_text(req.content.rstrip() + "\n", encoding="utf-8")

    return LabPromptDraftCreateResponse(
        name=draft_name,
        origin_path=f"policies/drafts/{draft_name}.txt",
        world_id=world_id,
        based_on_name=req.based_on_name,
    )


def list_world_prompt_drafts(world: World, world_id: str) -> LabPromptDraftListResponse:
    """List prompt draft files for one world."""

    policies_dir = _prompt_policies_dir(world, world_id)
    drafts_dir = policies_dir / "drafts"
    if not drafts_dir.is_dir():
        return LabPromptDraftListResponse(world_id=world_id, drafts=[])

    drafts: list[LabPromptDraftSummary] = []
    for draft_file in sorted(drafts_dir.glob("*.txt")):
        try:
            draft_file.read_text(encoding="utf-8")
        except OSError:
            continue
        drafts.append(
            LabPromptDraftSummary(
                name=draft_file.stem,
                origin_path=f"policies/drafts/{draft_file.name}",
                world_id=world_id,
            )
        )

    return LabPromptDraftListResponse(world_id=world_id, drafts=drafts)


def get_world_prompt_draft(
    world: World,
    world_id: str,
    draft_name: str,
) -> LabPromptDraftDocument:
    """Load one prompt draft from disk."""

    normalized_name = validate_prompt_draft_name(draft_name)
    policies_dir = _prompt_policies_dir(world, world_id)
    target = policies_dir / "drafts" / f"{normalized_name}.txt"
    if not target.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Prompt draft {normalized_name!r} not found for world {world_id!r}.",
        )

    try:
        content = target.read_text(encoding="utf-8")
    except OSError as err:
        raise HTTPException(
            status_code=500,
            detail=f"Prompt draft {normalized_name!r} is unreadable on disk.",
        ) from err

    return LabPromptDraftDocument(
        name=normalized_name,
        origin_path=f"policies/drafts/{normalized_name}.txt",
        world_id=world_id,
        content=content,
    )


def _activate_prompt_template(world: World, *, prompt_template_path: str) -> None:
    """Update ``world.json`` and reload the translation service."""

    world_json_path, world_data = load_world_json(
        world,
        unavailable_detail=f"Prompt files unavailable for world {world.world_id!r}.",
    )
    translation_data = world_data.setdefault("translation_layer", {})
    translation_data["enabled"] = True
    translation_data["prompt_template_path"] = prompt_template_path
    write_world_json(world_json_path, world_data)
    world.reload_translation_service(world_data)


def promote_world_prompt_draft(
    world: World,
    world_id: str,
    draft_name: str,
    req: LabPromptDraftPromoteRequest,
) -> LabPromptDraftPromoteResponse:
    """Promote one prompt draft into a canonical active prompt."""

    normalized_name = validate_prompt_draft_name(draft_name)
    target_name = validate_prompt_draft_name(
        req.target_name,
        detail_prefix="Promotion target names",
    )
    policies_dir = _prompt_policies_dir(world, world_id)

    draft_path = policies_dir / "drafts" / f"{normalized_name}.txt"
    if not draft_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Prompt draft {normalized_name!r} not found for world {world_id!r}.",
        )

    canonical_path = policies_dir / f"{target_name}.txt"
    if canonical_path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"A canonical prompt named {target_name!r} already exists.",
        )

    try:
        content = draft_path.read_text(encoding="utf-8")
    except OSError as err:
        raise HTTPException(
            status_code=500,
            detail=f"Prompt draft {normalized_name!r} is unreadable on disk.",
        ) from err

    canonical_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    active_prompt_path = f"policies/{target_name}.txt"
    _activate_prompt_template(world, prompt_template_path=active_prompt_path)

    return LabPromptDraftPromoteResponse(
        name=normalized_name,
        world_id=world_id,
        canonical_name=target_name,
        canonical_path=active_prompt_path,
        active_prompt_path=active_prompt_path,
    )
