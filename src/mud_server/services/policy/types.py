"""Data contracts for policy service modules.

The classes in this module are pure data containers used by multiple policy
subsystems. They intentionally avoid storage or API concerns so they can be
reused by service, CLI, and tests without cross-module coupling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AxisPolicyValidationReport:
    """Canonical axis-policy validation report used during engine bootstrap.

    This report shape is retained for bootstrap logging and diagnostics after
    legacy file-loader removal. Payloads are built from canonical DB policy
    objects (manifest/axis bundle activations), not from world policy files.
    """

    world_id: str
    axes: list[str]
    ordering_present: list[str]
    ordering_definitions: dict[str, Any]
    thresholds_present: list[str]
    thresholds_definitions: dict[str, Any]
    missing_components: list[str]
    policy_hash: str
    version: str | None


@dataclass(frozen=True, slots=True)
class PolicyIdentity:
    """Parsed canonical policy identity tuple.

    Attributes:
        policy_id: Canonical string form ``policy_type:namespace:policy_key``.
        policy_type: Parsed policy family token.
        namespace: Parsed namespace token.
        policy_key: Parsed logical policy key.
    """

    policy_id: str
    policy_type: str
    namespace: str
    policy_key: str


@dataclass(frozen=True, slots=True)
class ActivationScope:
    """Canonical activation scope for Layer 3 policy selection.

    Attributes:
        world_id: Required world identifier.
        client_profile: Optional client selector; empty string means world-level
            defaults.
    """

    world_id: str
    client_profile: str


@dataclass(frozen=True, slots=True)
class EffectiveAxisBundle:
    """Resolved canonical axis-bundle context for one scope.

    Runtime systems consume this object instead of reading policy YAML files.
    """

    manifest_policy_id: str
    manifest_variant: str
    axis_policy_id: str
    axis_variant: str
    bundle_id: str
    bundle_version: str
    manifest_payload: dict[str, Any]
    axes_payload: dict[str, Any]
    thresholds_payload: dict[str, Any]
    resolution_payload: dict[str, Any]
    required_runtime_inputs: set[str]
    policy_hash: str


@dataclass(frozen=True, slots=True)
class EffectiveImagePolicyBundle:
    """Resolved canonical image-policy bundle context for one scope.

    This contract powers the lab-facing image-bundle diagnostic endpoint while
    remaining DB-first. The ``*_path`` fields preserve route response shape
    compatibility for existing clients and are derived from manifest payload
    metadata rather than filesystem probes.
    """

    world_id: str
    policy_schema: str | None
    policy_bundle_id: str | None
    policy_bundle_version: int | str | None
    policy_hash: str
    composition_order: list[str]
    required_runtime_inputs: list[str]
    descriptor_layer_path: str | None
    tone_profile_path: str | None
    species_registry_path: str | None
    clothing_registry_path: str | None
    missing_components: list[str]


@dataclass(frozen=True, slots=True)
class PolicyValidationResult:
    """Validation-run result for one candidate policy variant payload."""

    policy_id: str
    variant: str
    is_valid: bool
    errors: list[str]
    content_hash: str
    validated_at: str
    validated_by: str
    validation_run_id: int


@dataclass(frozen=True, slots=True)
class ArtifactImportEntry:
    """One import outcome row for an artifact variant payload."""

    policy_id: str | None
    variant: str | None
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class ArtifactImportSummary:
    """Aggregate result for one artifact import run."""

    world_id: str
    client_profile: str
    activate: bool
    item_count: int
    imported_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    activated_count: int
    activation_skipped_count: int
    manifest_hash: str
    items_hash: str
    artifact_hash: str
    variants_hash: str
    entries: list[ArtifactImportEntry]
