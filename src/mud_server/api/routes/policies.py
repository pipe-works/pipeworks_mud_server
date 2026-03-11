"""Canonical policy-object API routes for the 3-layer architecture pilot.

These handlers intentionally stay thin:
- authenticate/authorize request session
- translate HTTP payloads to service-layer calls
- map structured service errors to stable API responses
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from mud_server.api.auth import validate_session
from mud_server.api.models_policy import (
    PolicyActivationEntryResponse,
    PolicyActivationListResponse,
    PolicyActivationRequest,
    PolicyListResponse,
    PolicyObjectResponse,
    PolicyPublishRequest,
    PolicyPublishResponse,
    PolicyPublishRunResponse,
    PolicyUpsertRequest,
    PolicyValidateRequest,
    PolicyValidateResponse,
)
from mud_server.core.engine import GameEngine
from mud_server.services.policy_service import (
    PolicyServiceError,
    parse_scope,
)
from mud_server.services.policy_service import (
    get_policy as service_get_policy,
)
from mud_server.services.policy_service import (
    get_publish_run as service_get_publish_run,
)
from mud_server.services.policy_service import (
    list_policies as service_list_policies,
)
from mud_server.services.policy_service import (
    list_policy_activations as service_list_policy_activations,
)
from mud_server.services.policy_service import (
    publish_scope as service_publish_scope,
)
from mud_server.services.policy_service import (
    resolve_effective_policy_activations as service_resolve_effective_policy_activations,
)
from mud_server.services.policy_service import (
    set_policy_activation as service_set_policy_activation,
)
from mud_server.services.policy_service import (
    upsert_policy_variant as service_upsert_policy_variant,
)
from mud_server.services.policy_service import (
    validate_policy_variant as service_validate_policy_variant,
)


def _error_response(error: PolicyServiceError) -> JSONResponse:
    """Map service-layer policy errors to canonical API payloads."""
    return JSONResponse(status_code=error.status_code, content=error.to_response_payload())


def _normalize_activation_response(row: dict[str, Any]) -> PolicyActivationEntryResponse:
    """Normalize service-layer activation rows to API response shape."""
    return PolicyActivationEntryResponse(
        world_id=row["world_id"],
        client_profile=row["client_profile"] or None,
        policy_id=row["policy_id"],
        variant=row["variant"],
        activated_at=row["activated_at"],
        activated_by=row["activated_by"],
        rollback_of_activation_id=row["rollback_of_activation_id"],
        audit_event_id=row.get("audit_event_id"),
    )


def router(_engine: GameEngine) -> APIRouter:
    """Build API router for canonical policy-object endpoints.

    Args:
        _engine: Reserved for future runtime-aware policy endpoints. The
            current pilot endpoints do not require direct engine access.
    """
    api = APIRouter(tags=["policy"])

    @api.get("/api/policies", response_model=PolicyListResponse)
    async def list_policies(
        session_id: str,
        policy_type: str | None = Query(default=None),
        namespace: str | None = Query(default=None),
        status: str | None = Query(default=None),
    ) -> Any:
        """List policy variants filtered by optional policy-type predicates."""
        validate_session(session_id)
        try:
            rows = service_list_policies(
                policy_type=policy_type, namespace=namespace, status=status
            )
            return PolicyListResponse(
                items=[PolicyObjectResponse.model_validate(row) for row in rows]
            )
        except PolicyServiceError as error:
            return _error_response(error)

    @api.get("/api/policies/{policy_id}", response_model=PolicyObjectResponse)
    async def get_policy(
        policy_id: str,
        session_id: str,
        variant: str | None = Query(default=None),
    ) -> Any:
        """Get one policy variant by id with optional variant selector."""
        validate_session(session_id)
        try:
            row = service_get_policy(policy_id=policy_id, variant=variant)
            return PolicyObjectResponse.model_validate(row)
        except PolicyServiceError as error:
            return _error_response(error)

    @api.post("/api/policies/{policy_id}/validate", response_model=PolicyValidateResponse)
    async def validate_policy_variant(
        policy_id: str,
        payload: PolicyValidateRequest,
        session_id: str,
        variant: str = Query(min_length=1),
    ) -> Any:
        """Validate one policy variant payload and persist validation history."""
        _user_id, username, _role = validate_session(session_id)
        validated_by = payload.validated_by or username
        try:
            result = service_validate_policy_variant(
                policy_id=policy_id,
                variant=variant,
                schema_version=payload.schema_version,
                policy_version=payload.policy_version,
                status=payload.status,
                content=payload.content,
                validated_by=validated_by,
            )
            return PolicyValidateResponse(
                policy_id=result.policy_id,
                variant=result.variant,
                is_valid=result.is_valid,
                errors=result.errors,
                content_hash=result.content_hash,
                validated_at=result.validated_at,
                validated_by=result.validated_by,
                validation_run_id=result.validation_run_id,
            )
        except PolicyServiceError as error:
            return _error_response(error)

    @api.put("/api/policies/{policy_id}/variants/{variant}", response_model=PolicyObjectResponse)
    async def upsert_policy_variant(
        policy_id: str,
        variant: str,
        payload: PolicyUpsertRequest,
        session_id: str,
    ) -> Any:
        """Validate and write one canonical policy variant.

        The service enforces validate-before-write so this endpoint is safe as
        the primary Phase 2 save path for API-only authoring.
        """
        _user_id, username, _role = validate_session(session_id)
        updated_by = payload.updated_by or username
        try:
            row = service_upsert_policy_variant(
                policy_id=policy_id,
                variant=variant,
                schema_version=payload.schema_version,
                policy_version=payload.policy_version,
                status=payload.status,
                content=payload.content,
                updated_by=updated_by,
            )
            return PolicyObjectResponse.model_validate(row)
        except PolicyServiceError as error:
            return _error_response(error)

    @api.post("/api/policy-activations", response_model=PolicyActivationEntryResponse)
    async def set_policy_activation(payload: PolicyActivationRequest, session_id: str):
        """Create or switch one activation pointer for a scope."""
        _user_id, username, _role = validate_session(session_id)
        activated_by = payload.activated_by or username
        scope_text = (
            payload.world_id
            if payload.client_profile is None
            else f"{payload.world_id}:{payload.client_profile}"
        )
        try:
            scope = parse_scope(scope_text)
            row = service_set_policy_activation(
                scope=scope,
                policy_id=payload.policy_id,
                variant=payload.variant,
                activated_by=activated_by,
                rollback_of_activation_id=payload.rollback_of_activation_id,
            )
            return _normalize_activation_response(row)
        except PolicyServiceError as error:
            return _error_response(error)

    @api.get("/api/policy-activations", response_model=PolicyActivationListResponse)
    async def list_policy_activations(
        scope: str = Query(min_length=1),
        session_id: str = Query(),
        effective: bool = Query(default=True),
    ):
        """List active pointers for one scope, optionally with world-default overlay.

        ``effective=true`` applies Layer 3 scope resolution:
        - world scope returns world pointers
        - world+client scope overlays client pointers on world defaults
        """
        validate_session(session_id)
        try:
            parsed_scope = parse_scope(scope)
            rows = (
                service_resolve_effective_policy_activations(scope=parsed_scope)
                if effective
                else service_list_policy_activations(scope=parsed_scope)
            )
            return PolicyActivationListResponse(
                world_id=parsed_scope.world_id,
                client_profile=parsed_scope.client_profile or None,
                items=[_normalize_activation_response(row) for row in rows],
            )
        except PolicyServiceError as error:
            return _error_response(error)

    @api.post("/api/policy-publish", response_model=PolicyPublishResponse)
    async def publish_policies(payload: PolicyPublishRequest, session_id: str):
        """Generate and persist one deterministic policy publish manifest."""
        _user_id, username, _role = validate_session(session_id)
        actor = payload.actor or username
        scope_text = (
            payload.world_id
            if payload.client_profile is None
            else f"{payload.world_id}:{payload.client_profile}"
        )
        try:
            scope = parse_scope(scope_text)
            result = service_publish_scope(scope=scope, actor=actor)
            return PolicyPublishResponse.model_validate(result)
        except PolicyServiceError as error:
            return _error_response(error)

    @api.get("/api/policy-publish/{publish_run_id}", response_model=PolicyPublishRunResponse)
    async def get_publish_run(publish_run_id: int, session_id: str):
        """Fetch one publish run with deterministic export artifact metadata."""
        validate_session(session_id)
        try:
            result = service_get_publish_run(publish_run_id=publish_run_id)
            return PolicyPublishRunResponse.model_validate(result)
        except PolicyServiceError as error:
            return _error_response(error)

    return api
