"""Lab endpoints for the Axis Descriptor Lab research tool.

These endpoints expose the world's OOC→IC translation pipeline directly via
a JSON API, bypassing the game engine's character DB lookup.  They are
intended exclusively for use by the Axis Descriptor Lab — a single-user
research tool for testing IC prompt behaviour against deterministic axis
payloads.

Auth
----
Session-based — same mechanism as all other server endpoints.  Admin or
superuser role is required.  The lab logs in interactively via its UI; no
credentials are stored anywhere on disk.

Endpoints
---------
GET  /api/lab/worlds
    List all active worlds with a flag indicating whether the translation
    layer is enabled.  Used to populate the lab's world-selector dropdown.

GET  /api/lab/world-config/{world_id}
    Return the translation layer configuration for a specific world (model,
    active_axes, strict_mode, etc.).  Used by the lab UI to reflect what the
    server will actually apply to a translation request.

POST /api/lab/translate
    Translate an OOC message to IC dialogue using the world's canonical
    pipeline.  Accepts raw axis values — no character DB lookup is
    performed.  Returns the IC text, outcome status, the server-formatted
    profile_summary, and the fully-rendered system prompt sent to Ollama.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from mud_server.api.auth import validate_session
from mud_server.api.models import (
    LabTranslateRequest,
    LabTranslateResponse,
    LabWorldConfig,
    LabWorldsResponse,
    LabWorldSummary,
)
from mud_server.api.permissions import get_role_hierarchy_level
from mud_server.core.engine import GameEngine
from mud_server.db import facade as database

logger = logging.getLogger(__name__)

# Minimum role level required for all lab endpoints.
# Admin (level 2) and Superuser (level 3) are permitted; Player (0) and
# Worldbuilder (1) are not.
_LAB_MIN_ROLE_LEVEL: int = get_role_hierarchy_level("admin")


def _require_lab_role(role: str) -> None:
    """Raise 403 if the session role is below admin.

    Args:
        role: Role string from the validated session.

    Raises:
        HTTPException(403): If the role's hierarchy level is below admin.
    """
    if get_role_hierarchy_level(role) < _LAB_MIN_ROLE_LEVEL:
        raise HTTPException(
            status_code=403,
            detail="Lab endpoints require admin or superuser role.",
        )


def router(engine: GameEngine) -> APIRouter:
    """Build and return the lab API router.

    Args:
        engine: The live ``GameEngine`` instance, used to access the world
                registry and translation services.

    Returns:
        Configured ``APIRouter`` with all lab endpoints registered.
    """
    api = APIRouter(prefix="/api/lab", tags=["lab"])

    @api.get("/worlds", response_model=LabWorldsResponse)
    async def list_lab_worlds(session_id: str) -> LabWorldsResponse:
        """List all active worlds with translation-layer availability.

        Returns every active world known to the server, flagged with whether
        its translation layer is enabled.  Used to populate the lab UI's
        world-selector dropdown.

        Requires admin or superuser role.
        """
        _, _, role = validate_session(session_id)
        _require_lab_role(role)

        worlds_data = engine.world_registry.list_worlds()
        result: list[LabWorldSummary] = []
        for row in worlds_data:
            wid = row.get("world_id", "")
            translation_enabled = False
            try:
                world = engine.world_registry.get_world(wid)
                translation_enabled = world.translation_layer_enabled()
            except Exception:
                # World failed to load or is inactive — surface it with
                # translation_enabled=False so the lab can still show it.
                pass
            result.append(
                LabWorldSummary(
                    world_id=wid,
                    name=row.get("name", wid),
                    translation_enabled=translation_enabled,
                )
            )

        return LabWorldsResponse(worlds=result)

    @api.get("/world-config/{world_id}", response_model=LabWorldConfig)
    async def get_world_config(world_id: str, session_id: str) -> LabWorldConfig:
        """Return the translation layer configuration for a world.

        Used by the lab UI to reflect the server's canonical active_axes,
        model, and validation settings without hardcoding them in the lab.

        Returns 404 if the world does not exist, is inactive, or has its
        translation layer disabled.

        Requires admin or superuser role.
        """
        _, _, role = validate_session(session_id)
        _require_lab_role(role)

        try:
            world = engine.world_registry.get_world(world_id)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"World {world_id!r} not found or inactive.",
            )

        service = world.get_translation_service()
        if service is None:
            raise HTTPException(
                status_code=404,
                detail=f"Translation layer not enabled for world {world_id!r}.",
            )

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

    @api.post("/translate", response_model=LabTranslateResponse)
    async def lab_translate(req: LabTranslateRequest) -> LabTranslateResponse:
        """Translate an OOC message using the world's canonical pipeline.

        Accepts raw axis values from the lab — no character DB lookup is
        performed.  The server filters the supplied axes to the world's
        ``active_axes``, builds the ``profile_summary`` in the server's
        canonical format, renders the system prompt, calls Ollama, and runs
        the validator.

        The response includes ``rendered_prompt`` so the lab can display
        exactly what was sent to Ollama, and ``world_config`` so the lab
        knows which axes and settings were applied.

        Returns 404 if the world is not found or inactive.
        Returns 503 if the world's translation layer is disabled.

        Requires admin or superuser role.
        """
        _, _, role = validate_session(req.session_id)
        _require_lab_role(role)

        try:
            world = engine.world_registry.get_world(req.world_id)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"World {req.world_id!r} not found or inactive.",
            )

        service = world.get_translation_service()
        if service is None:
            raise HTTPException(
                status_code=503,
                detail=f"Translation layer not enabled for world {req.world_id!r}.",
            )

        axes_raw = {name: ax.model_dump() for name, ax in req.axes.items()}
        seed = req.seed if req.seed != -1 else None

        result = service.translate_with_axes(
            axes_raw,
            req.ooc_message,
            character_name=req.character_name,
            channel=req.channel,
            seed=seed,
            temperature=req.temperature,
        )

        cfg = service.config
        world_row = database.get_world_by_id(req.world_id) or {}
        world_config = LabWorldConfig(
            world_id=req.world_id,
            name=world_row.get("name", req.world_id),
            model=cfg.model,
            active_axes=list(cfg.active_axes),
            strict_mode=cfg.strict_mode,
            max_output_chars=cfg.max_output_chars,
            timeout_seconds=cfg.timeout_seconds,
            translation_enabled=True,
        )

        return LabTranslateResponse(
            ic_text=result.ic_text,
            status=result.status,
            profile_summary=result.profile_summary,
            rendered_prompt=result.rendered_prompt,
            model=cfg.model,
            world_config=world_config,
        )

    return api
