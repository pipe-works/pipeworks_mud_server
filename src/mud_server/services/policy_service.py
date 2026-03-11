"""Service-layer orchestration for canonical policy APIs.

This layer owns contract and workflow semantics for policy authoring:
- identity parsing and guard rails
- schema/content validation
- validate-before-write upsert behavior
- activation pointer mutation and rollback checks
- deterministic publish manifest assembly

The repository layer remains storage-only; this layer enforces policy rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pipeworks_ipc import compute_payload_hash

from mud_server.db import facade as db_facade
from mud_server.db import policy_repo

_SUPPORTED_POLICY_TYPES = {
    "image_block",
    "species_block",
    "registry",
    "prompt",
    "descriptor_layer",
    "tone_profile",
}
_SPECIES_PILOT_POLICY_TYPE = "species_block"
_SPECIES_PILOT_NAMESPACE = "image.blocks.species"
_SUPPORTED_STATUSES = {"draft", "candidate", "active", "archived"}


class PolicyServiceError(RuntimeError):
    """Typed service error carrying stable HTTP and contract metadata.

    Attributes:
        status_code: HTTP status code returned by API adapters.
        code: Stable machine-readable contract code.
        detail: Human-readable explanation for logs and UI surfaces.
    """

    def __init__(self, *, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail

    def to_response_payload(self) -> dict[str, str]:
        """Return canonical error payload for API responses."""
        return {"detail": self.detail, "code": self.code, "stage": "policy"}


@dataclass(frozen=True, slots=True)
class PolicyIdentity:
    """Parsed canonical policy-object identity tuple."""

    policy_id: str
    policy_type: str
    namespace: str
    policy_key: str


@dataclass(frozen=True, slots=True)
class ActivationScope:
    """Canonical activation scope parsed from API payload/query string."""

    world_id: str
    client_profile: str


@dataclass(frozen=True, slots=True)
class PolicyValidationResult:
    """Validation result payload for one candidate policy variant."""

    policy_id: str
    variant: str
    is_valid: bool
    errors: list[str]
    content_hash: str
    validated_at: str
    validated_by: str
    validation_run_id: int


def list_policies(
    *,
    policy_type: str | None,
    namespace: str | None,
    status: str | None,
) -> list[dict[str, Any]]:
    """List policy variants with optional filter constraints.

    This function is intentionally thin and delegates filtering to the repo.
    """
    return policy_repo.list_policies(policy_type=policy_type, namespace=namespace, status=status)


def get_policy(*, policy_id: str, variant: str | None) -> dict[str, Any]:
    """Get one policy variant by id and optional variant selector.

    Args:
        policy_id: Canonical ``policy_type:namespace:policy_key`` identity.
        variant: Optional variant selector. When omitted, latest policy_version
            is returned.

    Raises:
        PolicyServiceError: If identity is invalid or no row exists.
    """
    _parse_policy_id(policy_id)
    row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
    if row is None:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_NOT_FOUND",
            detail=f"Policy not found for id={policy_id!r} variant={variant!r}.",
        )
    return row


def validate_policy_variant(
    *,
    policy_id: str,
    variant: str,
    schema_version: str,
    policy_version: int,
    status: str,
    content: dict[str, Any],
    validated_by: str,
) -> PolicyValidationResult:
    """Validate one policy payload and persist validation-run history.

    Validation always records a run, even when invalid, so callers can inspect
    validation trends and failures over time.
    """
    identity = _parse_policy_id(policy_id)
    validated_at = _now_iso()
    # First run common contract checks, then policy-type-specific checks.
    errors = _validate_common_fields(
        identity=identity,
        variant=variant,
        schema_version=schema_version,
        policy_version=policy_version,
        status=status,
        content=content,
    )
    errors.extend(_validate_policy_type_content(identity=identity, content=content))

    content_hash = _compute_content_hash(
        policy_id=policy_id,
        variant=variant,
        content=content,
    )
    is_valid = len(errors) == 0
    validation_run_id = policy_repo.insert_validation_run(
        policy_id=policy_id,
        variant=variant,
        is_valid=is_valid,
        errors=errors,
        validated_at=validated_at,
        validated_by=validated_by,
    )
    return PolicyValidationResult(
        policy_id=policy_id,
        variant=variant,
        is_valid=is_valid,
        errors=errors,
        content_hash=content_hash,
        validated_at=validated_at,
        validated_by=validated_by,
        validation_run_id=validation_run_id,
    )


def upsert_policy_variant(
    *,
    policy_id: str,
    variant: str,
    schema_version: str,
    policy_version: int,
    status: str,
    content: dict[str, Any],
    updated_by: str,
) -> dict[str, Any]:
    """Validate and upsert one policy variant row.

    This function enforces the Phase 2 save flow invariant:
    1. validate
    2. write variant only when valid
    """
    validation = validate_policy_variant(
        policy_id=policy_id,
        variant=variant,
        schema_version=schema_version,
        policy_version=policy_version,
        status=status,
        content=content,
        validated_by=updated_by,
    )
    if not validation.is_valid:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_VALIDATION_ERROR",
            detail="; ".join(validation.errors),
        )

    identity = _parse_policy_id(policy_id)
    policy_repo.upsert_policy_item(
        policy_id=identity.policy_id,
        policy_type=identity.policy_type,
        namespace=identity.namespace,
        policy_key=identity.policy_key,
    )
    return policy_repo.upsert_policy_variant(
        policy_id=policy_id,
        variant=variant,
        schema_version=schema_version,
        policy_version=policy_version,
        status=status,
        content=content,
        content_hash=validation.content_hash,
        updated_at=_now_iso(),
        updated_by=updated_by,
    )


def set_policy_activation(
    *,
    scope: ActivationScope,
    policy_id: str,
    variant: str,
    activated_by: str,
    rollback_of_activation_id: int | None = None,
) -> dict[str, Any]:
    """Set one activation pointer for a scope and emit audit history.

    When ``rollback_of_activation_id`` is supplied, the target variant is taken
    from that prior activation event after scope and policy-id checks.
    """
    _ensure_world_exists(scope.world_id)
    _parse_policy_id(policy_id)

    resolved_variant = variant
    if rollback_of_activation_id is not None:
        rollback_event = policy_repo.get_activation_event(rollback_of_activation_id)
        if rollback_event is None:
            raise PolicyServiceError(
                status_code=404,
                code="POLICY_ROLLBACK_EVENT_NOT_FOUND",
                detail=f"Rollback activation event not found: {rollback_of_activation_id}",
            )
        if rollback_event["policy_id"] != policy_id:
            raise PolicyServiceError(
                status_code=409,
                code="POLICY_ROLLBACK_POLICY_MISMATCH",
                detail="Rollback activation event does not match requested policy_id.",
            )
        if rollback_event["world_id"] != scope.world_id or rollback_event["client_profile"] != (
            scope.client_profile
        ):
            raise PolicyServiceError(
                status_code=409,
                code="POLICY_ROLLBACK_SCOPE_MISMATCH",
                detail="Rollback activation event belongs to a different activation scope.",
            )
        resolved_variant = str(rollback_event["variant"])

    try:
        # Repository call performs atomic pointer update + audit event insert.
        return policy_repo.set_policy_activation(
            world_id=scope.world_id,
            client_profile=scope.client_profile,
            policy_id=policy_id,
            variant=resolved_variant,
            activated_by=activated_by,
            activated_at=_now_iso(),
            rollback_of_activation_id=rollback_of_activation_id,
        )
    except Exception as exc:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_ACTIVATION_ERROR",
            detail=str(exc),
        ) from exc


def list_policy_activations(*, scope: ActivationScope) -> list[dict[str, Any]]:
    """List all active policy pointers for one scope."""
    _ensure_world_exists(scope.world_id)
    return policy_repo.list_policy_activations(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
    )


def publish_scope(*, scope: ActivationScope, actor: str) -> dict[str, Any]:
    """Build and persist one deterministic publish manifest for a scope.

    The manifest includes only active variants for the requested scope and is
    sorted deterministically before hashing to guarantee stable output for
    equivalent activation sets.
    """
    _ensure_world_exists(scope.world_id)
    activations = list_policy_activations(scope=scope)
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
    generated_at = _now_iso()
    manifest = {
        "world_id": scope.world_id,
        "client_profile": scope.client_profile or None,
        "generated_at": generated_at,
        "item_count": len(manifest_items),
        "items": manifest_items,
    }
    manifest_hash = str(compute_payload_hash(manifest))
    manifest["manifest_hash"] = manifest_hash
    publish_run_id = policy_repo.insert_publish_run(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
        actor=actor,
        manifest=manifest,
        created_at=generated_at,
    )
    return {
        "publish_run_id": publish_run_id,
        "manifest": manifest,
    }


def parse_scope(scope_text: str) -> ActivationScope:
    """Parse one scope string in ``world_id[:client_profile]`` format.

    ``client_profile`` is optional; an empty string represents world-level
    activation scope.
    """
    normalized = scope_text.strip()
    if not normalized:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_SCOPE_INVALID",
            detail="Activation scope must not be empty.",
        )
    if ":" in normalized:
        world_id, client_profile = normalized.split(":", 1)
    else:
        world_id, client_profile = normalized, ""
    world_id = world_id.strip()
    client_profile = client_profile.strip()
    if not world_id:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_SCOPE_INVALID",
            detail="Scope world_id must not be empty.",
        )
    return ActivationScope(world_id=world_id, client_profile=client_profile)


def _parse_policy_id(policy_id: str) -> PolicyIdentity:
    """Parse canonical policy id string ``policy_type:namespace:policy_key``.

    Raises:
        PolicyServiceError: If formatting is invalid or policy type is unknown.
    """
    parts = [part.strip() for part in policy_id.split(":", 2)]
    if len(parts) != 3 or any(not part for part in parts):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_ID_INVALID",
            detail=("policy_id must be formatted as " "'policy_type:namespace:policy_key'."),
        )
    policy_type, namespace, policy_key = parts
    if policy_type not in _SUPPORTED_POLICY_TYPES:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_TYPE_UNSUPPORTED",
            detail=f"Unsupported policy_type: {policy_type!r}",
        )
    return PolicyIdentity(
        policy_id=policy_id,
        policy_type=policy_type,
        namespace=namespace,
        policy_key=policy_key,
    )


def _validate_common_fields(
    *,
    identity: PolicyIdentity,
    variant: str,
    schema_version: str,
    policy_version: int,
    status: str,
    content: dict[str, Any],
) -> list[str]:
    """Validate common policy-object fields shared by all policy types."""
    errors: list[str] = []
    if not identity.namespace:
        errors.append("namespace must not be empty")
    if not identity.policy_key:
        errors.append("policy_key must not be empty")
    if not variant.strip():
        errors.append("variant must not be empty")
    if not schema_version.strip():
        errors.append("schema_version must not be empty")
    if policy_version < 1:
        errors.append("policy_version must be >= 1")
    if status not in _SUPPORTED_STATUSES:
        errors.append("status must be one of: draft, candidate, active, archived")
    return errors


def _validate_policy_type_content(
    *,
    identity: PolicyIdentity,
    content: dict[str, Any],
) -> list[str]:
    """Validate policy-type-specific content payload rules.

    Phase 1/2 intentionally limits write support to ``species_block`` in the
    ``image.blocks.species`` namespace.
    """
    errors: list[str] = []
    if identity.policy_type != _SPECIES_PILOT_POLICY_TYPE:
        errors.append("Phase 1 only supports writes/validation for policy_type='species_block'.")
        return errors
    if identity.namespace != _SPECIES_PILOT_NAMESPACE:
        errors.append("species_block namespace must be exactly 'image.blocks.species' in Phase 1.")
    text_value = content.get("text")
    if not isinstance(text_value, str) or not text_value.strip():
        errors.append("species_block content.text must be a non-empty string")
    return errors


def _compute_content_hash(*, policy_id: str, variant: str, content: dict[str, Any]) -> str:
    """Return deterministic content hash for policy variant payload.

    The hash input explicitly includes identity and variant so equal content in
    different policy objects does not collide at contract level.
    """
    return str(
        compute_payload_hash(
            {
                "policy_id": policy_id,
                "variant": variant,
                "content": content,
            }
        )
    )


def _ensure_world_exists(world_id: str) -> None:
    """Raise 404 when activation/publish target world does not exist."""
    if db_facade.get_world_by_id(world_id) is None:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_WORLD_NOT_FOUND",
            detail=f"World {world_id!r} not found.",
        )


def _now_iso() -> str:
    """Return UTC timestamp string in canonical ISO-8601 format."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
