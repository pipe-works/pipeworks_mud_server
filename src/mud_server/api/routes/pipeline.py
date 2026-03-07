"""Pipeline API endpoints.

This module owns API routes under ``/api/pipeline/*`` that expose
stateless generation primitives for downstream clients.

Current scope:
- ``POST /api/pipeline/condition-axis/generate``.

Design constraints:
- Session-authenticated endpoint (any valid role).
- Route-level validation returns structured ``detail/code/stage`` payloads.
- Business logic is delegated to service-layer adapters to avoid route drift.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from mud_server.api.auth import validate_session
from mud_server.api.models import (
    ConditionAxisGenerateRequest,
    ConditionAxisGenerateResponse,
    ConditionAxisProvenanceResponse,
)
from mud_server.core.engine import GameEngine
from mud_server.services.condition_axis_service import (
    ConditionAxisServiceError,
)
from mud_server.services.condition_axis_service import (
    generate_condition_axis as service_generate_condition_axis,
)


def _error_response(*, status_code: int, code: str, detail: str) -> JSONResponse:
    """Return canonical structured error payload for pipeline clients.

    Args:
        status_code: HTTP status code to emit.
        code: Stable machine-readable pipeline error code.
        detail: Human-readable error message.

    Returns:
        JSONResponse using the canonical ``axis_input`` error stage.
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "code": code,
            "stage": "axis_input",
        },
    )


def router(engine: GameEngine) -> APIRouter:
    """Build pipeline router endpoints.

    Args:
        engine: Shared game engine instance used for world resolution.

    Returns:
        Configured router with pipeline endpoints registered.
    """
    api = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

    @api.post("/condition-axis/generate", response_model=ConditionAxisGenerateResponse)
    async def generate_condition_axis(payload: dict[str, Any], session_id: str):
        """Generate canonical condition-axis values without side effects.

        Request:
            - ``session_id`` query parameter for session auth.
            - JSON body validated against ``ConditionAxisGenerateRequest``.

        Response:
            - ``200`` with canonical condition-axis payload.
            - Structured error payloads for validation/world/service failures.
        """
        # Keep auth explicit at route edge: nginx/CORS are not auth controls.
        validate_session(session_id)

        try:
            request = ConditionAxisGenerateRequest.model_validate(payload)
        except ValidationError:
            return _error_response(
                status_code=422,
                code="CONDITION_AXIS_VALIDATION_ERROR",
                detail="Invalid request payload for condition-axis generation.",
            )

        # Resolve world via canonical in-memory registry so world status checks
        # stay aligned with gameplay/runtime loading behavior.
        try:
            world = engine.world_registry.get_world(request.world_id)
        except ValueError:
            return _error_response(
                status_code=404,
                code="CONDITION_AXIS_WORLD_NOT_FOUND",
                detail=f"World {request.world_id!r} not found or inactive.",
            )

        world_root = world.get_world_root()
        if world_root is None:
            return _error_response(
                status_code=501,
                code="CONDITION_AXIS_UPSTREAM_UNSUPPORTED",
                detail=(
                    "Condition-axis generation is not available in the current upstream "
                    "configuration."
                ),
            )

        try:
            # Route delegates all generation behavior (policy/seed/upstream/error
            # mapping) to the service layer to avoid duplicate logic paths.
            result = service_generate_condition_axis(
                world_id=request.world_id,
                world_root=world_root,
                seed=request.seed,
                bundle_id=request.bundle_id,
                inputs=request.inputs.model_dump(mode="python"),
                strict_inputs=True,
            )
        except ConditionAxisServiceError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_response_payload(),
            )

        # Serialize result into stable API response model for OpenAPI/docs
        # consistency and predictable client parsing.
        return ConditionAxisGenerateResponse(
            world_id=result.world_id,
            bundle_id=result.bundle_id,
            bundle_version=result.bundle_version,
            policy_hash=result.policy_hash,
            seed=result.seed,
            axes=result.axes,
            provenance=ConditionAxisProvenanceResponse(
                source=result.provenance.source,
                served_via=result.provenance.served_via,
                generator=result.provenance.generator,
                generator_version=result.provenance.generator_version,
                generated_at=result.provenance.generated_at,
            ),
        )

    return api
