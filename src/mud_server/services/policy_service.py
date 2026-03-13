"""Canonical policy service facade.

This module is intentionally thin. It preserves the historical import path
(``mud_server.services.policy_service``) while delegating behavior to
specialized modules under ``mud_server.services.policy``.

Breaking changes in this refactor:
1. Legacy file-import APIs were removed from this facade.
2. Legacy path-mapping API (`policy_reference_from_legacy_path`) was removed.
3. Canonical DB/artifact APIs remain stable and are re-exported here.
"""

from __future__ import annotations

from typing import Any

from mud_server.config import config as _config
from mud_server.db import policy_repo as _policy_repo
from mud_server.services.policy.activation import (
    get_effective_policy_variant as _get_effective_policy_variant,
)
from mud_server.services.policy.activation import (
    list_policy_activations as _list_policy_activations,
)
from mud_server.services.policy.activation import (
    resolve_effective_policy_activations as _resolve_effective_policy_activations,
)
from mud_server.services.policy.activation import set_policy_activation as _set_policy_activation
from mud_server.services.policy.artifact_import import (
    import_published_artifact as _import_published_artifact,
)
from mud_server.services.policy.errors import PolicyServiceError as _PolicyServiceError
from mud_server.services.policy.publish import get_publish_run as _get_publish_run
from mud_server.services.policy.publish import publish_scope as _publish_scope
from mud_server.services.policy.runtime_resolution import (
    resolve_effective_axis_bundle as _resolve_effective_axis_bundle,
)
from mud_server.services.policy.runtime_resolution import (
    resolve_effective_image_policy_bundle as _resolve_effective_image_policy_bundle,
)
from mud_server.services.policy.runtime_resolution import (
    resolve_effective_prompt_template as _resolve_effective_prompt_template,
)
from mud_server.services.policy.types import (
    ActivationScope,
    ArtifactImportSummary,
    EffectiveAxisBundle,
    EffectiveImagePolicyBundle,
    PolicyValidationResult,
)
from mud_server.services.policy.utils import parse_scope as _parse_scope
from mud_server.services.policy.validation import get_policy as _get_policy
from mud_server.services.policy.validation import list_policies as _list_policies
from mud_server.services.policy.validation import (
    upsert_policy_variant as _upsert_policy_variant,
)
from mud_server.services.policy.validation import (
    validate_policy_variant as _validate_policy_variant,
)

# Re-exported compatibility aliases for existing API routes/tests that import
# `config`, `policy_repo`, and `PolicyServiceError` directly from this module.
config = _config
policy_repo = _policy_repo
PolicyServiceError = _PolicyServiceError


def list_policies(
    *,
    policy_type: str | None,
    namespace: str | None,
    status: str | None,
) -> list[dict[str, Any]]:
    """List canonical policy variants with optional filter constraints."""
    return _list_policies(policy_type=policy_type, namespace=namespace, status=status)


def get_policy(*, policy_id: str, variant: str | None) -> dict[str, Any]:
    """Get one canonical policy variant row by id and optional variant."""
    return _get_policy(policy_id=policy_id, variant=variant)


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
    """Validate one policy variant payload and persist validation-run history."""
    return _validate_policy_variant(
        policy_id=policy_id,
        variant=variant,
        schema_version=schema_version,
        policy_version=policy_version,
        status=status,
        content=content,
        validated_by=validated_by,
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
    """Validate then upsert one canonical policy variant row."""
    return _upsert_policy_variant(
        policy_id=policy_id,
        variant=variant,
        schema_version=schema_version,
        policy_version=policy_version,
        status=status,
        content=content,
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
    """Set one Layer 3 activation pointer for a scope."""
    return _set_policy_activation(
        scope=scope,
        policy_id=policy_id,
        variant=variant,
        activated_by=activated_by,
        rollback_of_activation_id=rollback_of_activation_id,
    )


def list_policy_activations(*, scope: ActivationScope) -> list[dict[str, Any]]:
    """List active policy pointers for exactly one scope."""
    return _list_policy_activations(scope=scope)


def resolve_effective_policy_activations(*, scope: ActivationScope) -> list[dict[str, Any]]:
    """Resolve effective active pointers for a scope overlay."""
    return _resolve_effective_policy_activations(scope=scope)


def get_effective_policy_variant(
    *,
    scope: ActivationScope,
    policy_id: str,
) -> dict[str, Any] | None:
    """Return effective active policy variant for scope + policy id."""
    return _get_effective_policy_variant(scope=scope, policy_id=policy_id)


def resolve_effective_prompt_template(
    *,
    scope: ActivationScope,
    preferred_policy_id: str | None = None,
    preferred_template_path: str | None,
) -> dict[str, str]:
    """Resolve effective canonical prompt template from DB activation state."""
    return _resolve_effective_prompt_template(
        scope=scope,
        preferred_policy_id=preferred_policy_id,
        preferred_template_path=preferred_template_path,
    )


def resolve_effective_axis_bundle(*, scope: ActivationScope) -> EffectiveAxisBundle:
    """Resolve effective canonical manifest+axis-bundle payloads."""
    return _resolve_effective_axis_bundle(scope=scope)


def resolve_effective_image_policy_bundle(*, scope: ActivationScope) -> EffectiveImagePolicyBundle:
    """Resolve effective canonical image-policy diagnostic bundle for one scope."""
    return _resolve_effective_image_policy_bundle(scope=scope)


def publish_scope(*, scope: ActivationScope, actor: str) -> dict[str, Any]:
    """Publish deterministic manifest/artifact for one scope."""
    return _publish_scope(scope=scope, actor=actor)


def get_publish_run(*, publish_run_id: int) -> dict[str, Any]:
    """Get one publish run plus deterministic artifact metadata."""
    return _get_publish_run(publish_run_id=publish_run_id)


def import_published_artifact(
    *,
    artifact: dict[str, Any],
    actor: str,
    activate: bool,
) -> ArtifactImportSummary:
    """Import one publish artifact into canonical DB policy state."""
    return _import_published_artifact(
        artifact=artifact,
        actor=actor,
        activate=activate,
    )


def parse_scope(scope_text: str) -> ActivationScope:
    """Parse ``world_id[:client_profile]`` string into ``ActivationScope``."""
    return _parse_scope(scope_text)
