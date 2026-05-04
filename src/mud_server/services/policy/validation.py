"""Canonical policy validation and upsert workflows.

This module owns contract-level validation and validate-before-write behavior.
Storage repositories remain persistence-only; this layer enforces business
rules that define valid canonical policy objects.
"""

from __future__ import annotations

from typing import Any

from mud_server.db import policy_repo

from .constants import (
    _LAYER1_POLICY_TYPES,
    _LAYER2_POLICY_TYPES,
    _SPECIES_PILOT_NAMESPACE,
    _SPECIES_PILOT_POLICY_TYPE,
    _SUPPORTED_POLICY_TYPES,
    _SUPPORTED_STATUSES,
)
from .errors import PolicyServiceError
from .hashing import compute_content_hash
from .types import PolicyIdentity, PolicyValidationResult
from .utils import now_iso


def parse_policy_id(policy_id: str) -> PolicyIdentity:
    """Parse canonical ``policy_type:namespace:policy_key`` identity.

    Raises:
        PolicyServiceError: When the identity format is invalid or policy type
            is not supported by canonical policy APIs.
    """
    parts = [part.strip() for part in policy_id.split(":", 2)]
    if len(parts) != 3 or any(not part for part in parts):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_ID_INVALID",
            detail="policy_id must be formatted as 'policy_type:namespace:policy_key'.",
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


def list_policies(
    *,
    policy_type: str | None,
    namespace: str | None,
    status: str | None,
) -> list[dict[str, Any]]:
    """List canonical policy variants with optional filter constraints."""
    return policy_repo.list_policies(policy_type=policy_type, namespace=namespace, status=status)


def get_policy(*, policy_id: str, variant: str | None) -> dict[str, Any]:
    """Get a canonical policy row by id and optional variant selector."""
    parse_policy_id(policy_id)
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
    """Validate one policy payload and persist validation-run history."""
    identity = parse_policy_id(policy_id)
    validated_at = now_iso()

    errors = _validate_common_fields(
        identity=identity,
        variant=variant,
        schema_version=schema_version,
        policy_version=policy_version,
        status=status,
    )
    errors.extend(_validate_policy_type_content(identity=identity, content=content))

    content_hash = compute_content_hash(policy_id=policy_id, variant=variant, content=content)
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
    """Validate then upsert one canonical policy variant row.

    The write path enforces the invariant that invalid payloads never reach
    canonical variant storage.
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

    identity = parse_policy_id(policy_id)
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
        updated_at=now_iso(),
        updated_by=updated_by,
    )


def is_policy_variant_unchanged(
    *,
    existing_row: dict[str, Any] | None,
    schema_version: str | None = None,
    policy_version: int,
    status: str,
    content: dict[str, Any],
) -> bool:
    """Return whether the existing variant row already matches provided payload."""
    if existing_row is None:
        return False

    if schema_version is not None and str(existing_row.get("schema_version")) != schema_version:
        return False
    if int(existing_row.get("policy_version", 0)) != policy_version:
        return False
    if str(existing_row.get("status", "")) != status:
        return False
    existing_content = existing_row.get("content")
    if not isinstance(existing_content, dict):
        return False
    return existing_content == content


def _validate_common_fields(
    *,
    identity: PolicyIdentity,
    variant: str,
    schema_version: str,
    policy_version: int,
    status: str,
) -> list[str]:
    """Validate policy fields shared across all policy families."""
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


def _validate_slot_kinds_field(content: dict[str, Any]) -> list[str]:
    """Validate the optional ``content.slot_kinds`` snippet metadata field.

    The field is optional. When present it must be a non-empty list whose
    entries are non-empty strings after stripping. This metadata is consumed by
    the image-generator prompt composer to scope which snippets a given slot
    kind is allowed to pick. Snippets without the field default to the
    snippet's own namespace at API serialization time.
    """
    if "slot_kinds" not in content:
        return []
    raw = content.get("slot_kinds")
    if not isinstance(raw, list):
        return ["content.slot_kinds must be a list of strings when present"]
    if len(raw) == 0:
        return ["content.slot_kinds must not be empty when present"]
    cleaned: list[str] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, str) or not entry.strip():
            return [f"content.slot_kinds[{index}] must be a non-empty string"]
        cleaned.append(entry.strip())
    return []


def _validate_policy_type_content(
    *, identity: PolicyIdentity, content: dict[str, Any]
) -> list[str]:
    """Validate policy-type-specific content invariants.

    Canonical authoring currently supports Layer 1 and Layer 2 families used by
    runtime and publish flows.
    """
    errors: list[str] = list(_validate_slot_kinds_field(content))

    if identity.policy_type == _SPECIES_PILOT_POLICY_TYPE:
        if identity.namespace != _SPECIES_PILOT_NAMESPACE:
            errors.append("species_block namespace must be exactly 'image.blocks.species'.")
        text_value = content.get("text")
        if not isinstance(text_value, str) or not text_value.strip():
            errors.append("species_block content.text must be a non-empty string")
        return errors

    if identity.policy_type == "clothing_block":
        clothing_text = content.get("text")
        if not isinstance(clothing_text, str) or not clothing_text.strip():
            errors.append("clothing_block content.text must be a non-empty string")
        return errors

    if identity.policy_type == "image_block":
        image_text = content.get("text")
        if not isinstance(image_text, str) or not image_text.strip():
            errors.append("image_block content.text must be a non-empty string")
        return errors

    if identity.policy_type == "location":
        location_text = content.get("text")
        if not isinstance(location_text, str) or not location_text.strip():
            errors.append("location content.text must be a non-empty string")
        return errors

    if identity.policy_type == "prompt":
        prompt_text = content.get("text")
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            errors.append("prompt content.text must be a non-empty string")
        return errors

    if identity.policy_type == "tone_profile":
        prompt_block = content.get("prompt_block")
        if not isinstance(prompt_block, str) or not prompt_block.strip():
            errors.append("tone_profile content.prompt_block must be a non-empty string")
        return errors

    if identity.policy_type == "axis_bundle":
        for key in ("axes", "thresholds", "resolution"):
            if not isinstance(content.get(key), dict) or not content.get(key):
                errors.append(f"axis_bundle content.{key} must be a non-empty object")
        return errors

    if identity.policy_type == "manifest_bundle":
        manifest_payload = content.get("manifest")
        if not isinstance(manifest_payload, dict) or not manifest_payload:
            errors.append("manifest_bundle content.manifest must be a non-empty object")
        return errors

    if identity.policy_type in _LAYER2_POLICY_TYPES:
        errors.extend(_validate_layer2_references(content=content))
        if identity.policy_type == "descriptor_layer":
            descriptor_text = content.get("text")
            if not isinstance(descriptor_text, str) or not descriptor_text.strip():
                errors.append("descriptor_layer content.text must be a non-empty string")
        return errors

    errors.append(
        "Validation/writes currently support policy_type values: "
        "'image_block', 'species_block', 'clothing_block', 'location', "
        "'prompt', 'tone_profile', 'axis_bundle', 'manifest_bundle', "
        "'descriptor_layer', 'registry'."
    )
    return errors


def _validate_layer2_references(*, content: dict[str, Any]) -> list[str]:
    """Validate Layer 2 references as strict Layer 1 identity pointers."""
    errors: list[str] = []
    references = content.get("references")
    if not isinstance(references, list) or len(references) == 0:
        return ["Layer 2 content.references must be a non-empty list."]

    for index, reference in enumerate(references):
        prefix = f"content.references[{index}]"
        if not isinstance(reference, dict):
            errors.append(f"{prefix} must be an object with policy_id and variant.")
            continue

        referenced_policy_id = reference.get("policy_id")
        referenced_variant = reference.get("variant")
        if not isinstance(referenced_policy_id, str) or not referenced_policy_id.strip():
            errors.append(f"{prefix}.policy_id must be a non-empty string.")
            continue
        if not isinstance(referenced_variant, str) or not referenced_variant.strip():
            errors.append(f"{prefix}.variant must be a non-empty string.")
            continue

        try:
            referenced_identity = parse_policy_id(referenced_policy_id.strip())
        except PolicyServiceError as error:
            errors.append(f"{prefix}.policy_id is invalid: {error.detail}")
            continue

        if referenced_identity.policy_type not in _LAYER1_POLICY_TYPES:
            errors.append(
                f"{prefix}.policy_id must reference a Layer 1 policy type "
                f"{sorted(_LAYER1_POLICY_TYPES)}; got {referenced_identity.policy_type!r}."
            )
            continue

        referenced_row = policy_repo.get_policy(
            policy_id=referenced_identity.policy_id,
            variant=referenced_variant.strip(),
        )
        if referenced_row is None:
            errors.append(
                f"{prefix} references missing Layer 1 variant: "
                f"{referenced_identity.policy_id}:{referenced_variant.strip()}"
            )
    return errors
