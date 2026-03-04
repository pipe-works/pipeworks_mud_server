"""Shared helpers for lab route preconditions and response assembly.

This module keeps the ``lab`` router focused on HTTP registration while
centralising repeated session, world, and translation-layer checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from fastapi import HTTPException

from mud_server.api.auth import validate_session
from mud_server.api.models import LabWorldConfig
from mud_server.api.permissions import get_role_hierarchy_level
from mud_server.core.engine import GameEngine
from mud_server.db import facade as database

if TYPE_CHECKING:
    from mud_server.core.world import World
    from mud_server.translation.service import OOCToICTranslationService

_LAB_MIN_ROLE_LEVEL: int = get_role_hierarchy_level("admin")


def require_lab_role(role: str) -> None:
    """Raise 403 if the role's hierarchy level is below admin."""

    if get_role_hierarchy_level(role) < _LAB_MIN_ROLE_LEVEL:
        raise HTTPException(
            status_code=403,
            detail="Lab endpoints require admin or superuser role.",
        )


def require_lab_session(session_id: str) -> str:
    """Validate one session id and enforce the minimum lab role.

    Returns:
        The validated role string for the current session.
    """

    _, _, role = validate_session(session_id)
    require_lab_role(role)
    return role


def get_lab_world(engine: GameEngine, world_id: str) -> World:
    """Return an active world or raise a 404 lab-style error."""

    try:
        return engine.world_registry.get_world(world_id)
    except ValueError as err:
        raise HTTPException(
            status_code=404,
            detail=f"World {world_id!r} not found or inactive.",
        ) from err


def require_translation_world(
    world: World,
    world_id: str,
    *,
    status_code: int = 404,
) -> OOCToICTranslationService:
    """Return one world's translation service or raise an HTTP error."""

    service = world.get_translation_service()
    if service is None:
        raise HTTPException(
            status_code=status_code,
            detail=f"Translation layer not enabled for world {world_id!r}.",
        )
    return cast(OOCToICTranslationService, service)


def require_world_root(world: World, *, unavailable_detail: str) -> Path:
    """Return the world root directory or raise a 404 with route-specific detail."""

    world_root = world.get_world_root()
    if world_root is None:
        raise HTTPException(status_code=404, detail=unavailable_detail)
    return world_root


def build_lab_world_config(
    world_id: str,
    service: OOCToICTranslationService,
) -> LabWorldConfig:
    """Construct the stable lab-facing world config payload."""

    cfg = service.config
    world_row = database.get_world_by_id(world_id) or {}
    return LabWorldConfig(
        world_id=world_id,
        name=world_row.get("name", world_id),
        model=cfg.model,
        active_axes=list(cfg.active_axes),
        strict_mode=cfg.strict_mode,
        max_output_chars=cfg.max_output_chars,
        timeout_seconds=cfg.timeout_seconds,
        translation_enabled=True,
    )


def load_world_json(world: World, *, unavailable_detail: str) -> tuple[Path, dict]:
    """Return the resolved ``world.json`` path and parsed payload for one world."""

    require_world_root(world, unavailable_detail=unavailable_detail)
    world_json_path = world.get_world_json_path()
    if not world_json_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"World config unavailable for world {world.world_id!r}.",
        )

    try:
        world_data = json.loads(world_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise HTTPException(
            status_code=500,
            detail=f"World config for world {world.world_id!r} is unreadable on disk.",
        ) from err

    return world_json_path, world_data


def write_world_json(path: Path, payload: dict) -> None:
    """Persist one ``world.json`` payload using repo-standard formatting."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
