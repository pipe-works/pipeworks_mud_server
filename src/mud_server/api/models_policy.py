"""Pydantic API models for policy hash and canonical policy-object endpoints.

This module now carries two model groups:
- hash snapshot models used by Step 1 drift checks
- policy-object CRUD/validate/activate/publish models used by the 3-layer API
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PolicyHashDirectoryResponse(BaseModel):
    """One deterministic directory hash summary under the canonical policy root."""

    path: str
    file_count: int
    hash: str


class PolicyHashSnapshotResponse(BaseModel):
    """Top-level canonical policy hash snapshot payload."""

    hash_version: str
    canonical_root: str
    generated_at: str
    file_count: int
    root_hash: str
    directories: list[PolicyHashDirectoryResponse]


class PolicyObjectResponse(BaseModel):
    """Canonical policy-object payload returned by policy CRUD endpoints.

    This shape mirrors the contract in
    ``3_layer_policy_architecture.md`` section 24.1.
    """

    policy_id: str
    policy_type: str
    namespace: str
    policy_key: str
    variant: str
    schema_version: str
    policy_version: int
    status: str
    content: dict[str, Any]
    content_hash: str
    updated_at: str
    updated_by: str


class PolicyListResponse(BaseModel):
    """List payload for filtered policy-object queries."""

    items: list[PolicyObjectResponse]


class PolicyValidateRequest(BaseModel):
    """Request body for policy variant validation.

    ``validated_by`` is optional; route handlers default it from authenticated
    username when omitted.
    """

    schema_version: str = Field(min_length=1)
    policy_version: int = Field(ge=1)
    status: str = Field(min_length=1)
    content: dict[str, Any]
    validated_by: str | None = None


class PolicyValidateResponse(BaseModel):
    """Validation response payload for one policy variant."""

    policy_id: str
    variant: str
    is_valid: bool
    errors: list[str]
    content_hash: str
    validated_at: str
    validated_by: str
    validation_run_id: int


class PolicyUpsertRequest(BaseModel):
    """Request body for policy variant upsert.

    ``updated_by`` is optional; route handlers default it from authenticated
    username when omitted.
    """

    schema_version: str = Field(min_length=1)
    policy_version: int = Field(ge=1)
    status: str = Field(min_length=1)
    content: dict[str, Any]
    updated_by: str | None = None


class PolicyActivationRequest(BaseModel):
    """Request body for activation pointer updates.

    ``rollback_of_activation_id`` points to a prior activation audit event and
    requests pointer reassignment to that event's variant.
    """

    world_id: str = Field(min_length=1)
    client_profile: str | None = None
    policy_id: str = Field(min_length=1)
    variant: str = Field(min_length=1)
    activated_by: str | None = None
    rollback_of_activation_id: int | None = Field(default=None, ge=1)


class PolicyActivationEntryResponse(BaseModel):
    """One activation pointer row in API responses."""

    world_id: str
    client_profile: str | None
    policy_id: str
    variant: str
    activated_at: str
    activated_by: str
    rollback_of_activation_id: int | None
    audit_event_id: int | None = None


class PolicyActivationListResponse(BaseModel):
    """Scope activation listing payload."""

    world_id: str
    client_profile: str | None
    items: list[PolicyActivationEntryResponse]


class PolicyPublishRequest(BaseModel):
    """Request payload for deterministic policy publish generation.

    ``actor`` is optional; route handlers default it from authenticated
    username when omitted.
    """

    world_id: str = Field(min_length=1)
    client_profile: str | None = None
    actor: str | None = None


class PolicyPublishManifestItemResponse(BaseModel):
    """One policy variant row in publish manifest payload."""

    policy_id: str
    policy_type: str
    namespace: str
    policy_key: str
    variant: str
    schema_version: str
    policy_version: int
    status: str
    content_hash: str
    updated_at: str


class PolicyPublishManifestResponse(BaseModel):
    """Deterministic publish manifest for one activation scope."""

    world_id: str
    client_profile: str | None
    generated_at: str
    item_count: int
    items_hash: str
    manifest_hash: str
    items: list[PolicyPublishManifestItemResponse]


class PolicyPublishArtifactResponse(BaseModel):
    """Deterministic export artifact metadata for downstream mirrors."""

    artifact_hash: str
    artifact_path: str


class PolicyPublishResponse(BaseModel):
    """API response for publish-run creation."""

    publish_run_id: int
    manifest: PolicyPublishManifestResponse
    artifact: PolicyPublishArtifactResponse


class PolicyPublishRunResponse(BaseModel):
    """API response for one persisted publish run."""

    publish_run_id: int
    world_id: str
    client_profile: str | None
    actor: str
    created_at: str
    manifest: PolicyPublishManifestResponse
    artifact: PolicyPublishArtifactResponse
