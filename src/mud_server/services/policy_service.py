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

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pipeworks_ipc import compute_payload_hash

from mud_server.config import PROJECT_ROOT, config
from mud_server.db import facade as db_facade
from mud_server.db import policy_repo

_SUPPORTED_POLICY_TYPES = {
    "species_block",
    "clothing_block",
    "registry",
    "prompt",
    "descriptor_layer",
    "tone_profile",
    "axis_bundle",
    "manifest_bundle",
}
_LAYER1_POLICY_TYPES = {
    "species_block",
    "clothing_block",
    "prompt",
    "tone_profile",
}
_LAYER2_POLICY_TYPES = {
    "descriptor_layer",
    "registry",
}
_SPECIES_PILOT_POLICY_TYPE = "species_block"
_SPECIES_PILOT_NAMESPACE = "image.blocks.species"
_SUPPORTED_STATUSES = {"draft", "candidate", "active", "archived"}
_POLICY_EXPORT_SCHEMA_VERSION = "1.0"
_POLICY_EXPORT_DIRNAME = "policy_exports"
_POLICY_SCHEMA_VERSION_V1 = "1.0"
_SPECIES_SOURCE_RELATIVE_DIR = Path("policies") / "image" / "blocks" / "species"
_SPECIES_FILENAME_PATTERN = re.compile(
    r"^(?P<policy_key>[A-Za-z0-9_.-]+)_v(?P<version>[1-9][0-9]*)$"
)
_TONE_PROFILE_SOURCE_RELATIVE_DIR = Path("policies") / "image" / "tone_profiles"
_PROMPT_TRANSLATION_SOURCE_RELATIVE_DIR = Path("policies") / "translation" / "prompts"
_PROMPT_IMAGE_SOURCE_RELATIVE_DIR = Path("policies") / "image" / "prompts"
_TONE_PROFILE_FILENAME_PATTERN = re.compile(
    r"^(?P<policy_key>[A-Za-z0-9_.-]+)_v(?P<version>[1-9][0-9]*)\.json$"
)
_PROMPT_FILENAME_PATTERN = re.compile(
    r"^(?P<policy_key>[A-Za-z0-9_.-]+)_v(?P<version>[1-9][0-9]*)\.txt$"
)
_CLOTHING_BLOCK_FILENAME_PATTERN = _PROMPT_FILENAME_PATTERN
_DESCRIPTOR_SOURCE_RELATIVE_DIR = Path("policies") / "image" / "descriptor_layers"
_REGISTRY_SOURCE_RELATIVE_DIR = Path("policies") / "image" / "registries"
_CLOTHING_BLOCK_SOURCE_RELATIVE_DIR = Path("policies") / "image" / "blocks" / "clothing"
_MANIFEST_SOURCE_RELATIVE_PATH = Path("policies") / "manifest.yaml"
_DESCRIPTOR_FILENAME_PATTERN = re.compile(
    r"^(?P<policy_key>[A-Za-z0-9_.-]+)_v(?P<version>[1-9][0-9]*)\.(?P<ext>txt|json|ya?ml)$"
)
_REGISTRY_VERSIONED_FILENAME_PATTERN = re.compile(
    r"^(?P<policy_key>[A-Za-z0-9_.-]+)_v(?P<version>[1-9][0-9]*)$"
)
_LEGACY_SPECIES_BLOCK_PATH_PATTERN = re.compile(
    r"^(?:policies/)?image/blocks/species/(?P<policy_key>.+)_"
    r"(?P<variant>v[0-9][A-Za-z0-9_-]*)\.ya?ml$"
)
_LEGACY_CLOTHING_BLOCK_PATH_PATTERN = re.compile(
    r"^(?:policies/)?image/blocks/clothing/"
    r"(?P<namespace_path>(?:[A-Za-z0-9._-]+/)*)"
    r"(?P<policy_key>.+)_(?P<variant>v[0-9][A-Za-z0-9_-]*)\.txt$"
)
_LEGACY_PROMPT_PATH_PATTERN = re.compile(
    r"^(?:policies/)?(?P<namespace_path>(?:image|translation)/prompts(?:/[A-Za-z0-9._-]+)*)/"
    r"(?P<policy_key>.+)_(?P<variant>v[0-9][A-Za-z0-9_-]*)\.txt$"
)
_LEGACY_TONE_PROFILE_PATH_PATTERN = re.compile(
    r"^(?:policies/)?image/tone_profiles/(?P<policy_key>.+)_"
    r"(?P<variant>v[0-9][A-Za-z0-9_-]*)\.json$"
)


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
class EffectiveAxisBundle:
    """Resolved canonical axis bundle context for one activation scope.

    Attributes:
        manifest_policy_id: Canonical Layer 1 manifest policy id.
        manifest_variant: Activated manifest variant token.
        axis_policy_id: Canonical Layer 1 axis-bundle policy id.
        axis_variant: Activated axis-bundle variant token.
        bundle_id: Logical axis bundle id referenced by the manifest payload.
        bundle_version: Logical axis bundle version referenced by manifest.
        manifest_payload: Parsed manifest payload from canonical policy content.
        axes_payload: Parsed ``axes`` payload from canonical axis bundle.
        thresholds_payload: Parsed ``thresholds`` payload from canonical axis bundle.
        resolution_payload: Parsed ``resolution`` payload from canonical axis bundle.
        required_runtime_inputs: Runtime input keys from manifest composition.
        policy_hash: Deterministic hash of the resolved manifest+axis payloads.
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


@dataclass(frozen=True, slots=True)
class SpeciesImportEntry:
    """One legacy species import outcome row."""

    source_path: str
    policy_id: str | None
    variant: str | None
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class SpeciesImportSummary:
    """Aggregate result for one species backfill/import run."""

    world_id: str
    activate: bool
    scanned_files: int
    imported_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    activated_count: int
    activation_skipped_count: int
    entries: list[SpeciesImportEntry]


@dataclass(frozen=True, slots=True)
class Layer2ImportEntry:
    """One legacy Layer 2 import outcome row."""

    source_path: str
    policy_id: str | None
    variant: str | None
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class Layer2ImportSummary:
    """Aggregate result for one Layer 2 backfill/import run."""

    world_id: str
    activate: bool
    scanned_descriptor_files: int
    scanned_registry_files: int
    imported_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    activated_count: int
    activation_skipped_count: int
    entries: list[Layer2ImportEntry]


@dataclass(frozen=True, slots=True)
class TonePromptImportEntry:
    """One legacy tone-profile/prompt import outcome row."""

    source_path: str
    policy_id: str | None
    variant: str | None
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class TonePromptImportSummary:
    """Aggregate result for one tone-profile/prompt backfill/import run."""

    world_id: str
    activate: bool
    scanned_tone_profile_files: int
    scanned_prompt_files: int
    imported_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    activated_count: int
    activation_skipped_count: int
    entries: list[TonePromptImportEntry]


@dataclass(frozen=True, slots=True)
class ClothingImportEntry:
    """One legacy clothing-block import outcome row."""

    source_path: str
    policy_id: str | None
    variant: str | None
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class ClothingImportSummary:
    """Aggregate result for one clothing-block backfill/import run."""

    world_id: str
    activate: bool
    scanned_clothing_files: int
    imported_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    activated_count: int
    activation_skipped_count: int
    entries: list[ClothingImportEntry]


@dataclass(frozen=True, slots=True)
class AxisManifestImportEntry:
    """One axis/manifest bundle import outcome row."""

    source_path: str
    policy_id: str | None
    variant: str | None
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class AxisManifestImportSummary:
    """Aggregate result for axis-bundle + manifest-bundle backfill/import run."""

    world_id: str
    activate: bool
    scanned_files: int
    imported_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    activated_count: int
    activation_skipped_count: int
    entries: list[AxisManifestImportEntry]


@dataclass(frozen=True, slots=True)
class WorldPolicyImportSummary:
    """Aggregate result for one world-scoped import-all migration run."""

    world_id: str
    activate: bool
    imported_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    activated_count: int
    activation_skipped_count: int
    entries: list[str]


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


def import_species_blocks_from_legacy_yaml(
    *,
    world_id: str,
    actor: str,
    activate: bool,
    status: str = "active",
) -> SpeciesImportSummary:
    """Backfill legacy ``species/*.yaml`` files into canonical policy DB rows.

    The importer is idempotent:
    - unchanged variants are skipped
    - existing variants with changed payload/status/version are updated
    - new variants are imported
    - optional world-scope activation only mutates pointers when needed
    """
    _ensure_world_exists(world_id)
    normalized_status = status.strip()
    if normalized_status not in _SUPPORTED_STATUSES:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_STATUS_INVALID",
            detail=(
                "Import status must be one of: draft, candidate, active, archived; "
                f"got {status!r}."
            ),
        )

    normalized_actor = actor.strip() or "policy-importer"
    species_root = _resolve_world_root_path(world_id) / _SPECIES_SOURCE_RELATIVE_DIR
    if not species_root.exists() or not species_root.is_dir():
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_SPECIES_SOURCE_NOT_FOUND",
            detail=f"Species source directory not found: {species_root}",
        )

    species_files = sorted(
        [*species_root.glob("*.yaml"), *species_root.glob("*.yml")],
        key=lambda path: path.name,
    )

    entries: list[SpeciesImportEntry] = []
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    activation_targets: dict[str, str] = {}

    for species_path in species_files:
        source_path = str(species_path)
        try:
            policy_key, variant, file_policy_version = _parse_species_filename(species_path)
            payload = _read_species_yaml_payload(species_path)
            policy_version = _resolve_species_policy_version(
                payload=payload,
                file_policy_version=file_policy_version,
                species_path=species_path,
            )
            content = _extract_species_text_content(payload=payload, species_path=species_path)
            policy_id = f"{_SPECIES_PILOT_POLICY_TYPE}:{_SPECIES_PILOT_NAMESPACE}:{policy_key}"
            existing_row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
            if _is_species_variant_unchanged(
                existing_row=existing_row,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
            ):
                skipped_count += 1
                entries.append(
                    SpeciesImportEntry(
                        source_path=source_path,
                        policy_id=policy_id,
                        variant=variant,
                        action="skipped",
                        detail="unchanged",
                    )
                )
                activation_targets[policy_id] = variant
                continue

            upsert_policy_variant(
                policy_id=policy_id,
                variant=variant,
                schema_version=_POLICY_SCHEMA_VERSION_V1,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
                updated_by=normalized_actor,
            )
            action = "imported" if existing_row is None else "updated"
            if action == "imported":
                imported_count += 1
            else:
                updated_count += 1
            entries.append(
                SpeciesImportEntry(
                    source_path=source_path,
                    policy_id=policy_id,
                    variant=variant,
                    action=action,
                    detail=f"{action} {policy_id}:{variant}",
                )
            )
            activation_targets[policy_id] = variant
        except (PolicyServiceError, ValueError, OSError, yaml.YAMLError) as exc:
            error_count += 1
            entries.append(
                SpeciesImportEntry(
                    source_path=source_path,
                    policy_id=None,
                    variant=None,
                    action="error",
                    detail=str(exc),
                )
            )

    activated_count = 0
    activation_skipped_count = 0
    if activate and activation_targets:
        current_activations = {
            str(row["policy_id"]): str(row["variant"])
            for row in policy_repo.list_policy_activations(world_id=world_id, client_profile="")
        }
        world_scope = ActivationScope(world_id=world_id, client_profile="")
        for policy_id in sorted(activation_targets):
            target_variant = activation_targets[policy_id]
            if current_activations.get(policy_id) == target_variant:
                activation_skipped_count += 1
                continue
            try:
                set_policy_activation(
                    scope=world_scope,
                    policy_id=policy_id,
                    variant=target_variant,
                    activated_by=normalized_actor,
                )
                current_activations[policy_id] = target_variant
                activated_count += 1
            except PolicyServiceError as exc:
                error_count += 1
                entries.append(
                    SpeciesImportEntry(
                        source_path="<activation>",
                        policy_id=policy_id,
                        variant=target_variant,
                        action="error",
                        detail=f"activation failed: {exc.detail}",
                    )
                )

    return SpeciesImportSummary(
        world_id=world_id,
        activate=activate,
        scanned_files=len(species_files),
        imported_count=imported_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        activated_count=activated_count,
        activation_skipped_count=activation_skipped_count,
        entries=entries,
    )


def import_layer2_policies_from_legacy_files(
    *,
    world_id: str,
    actor: str,
    activate: bool,
    status: str = "active",
) -> Layer2ImportSummary:
    """Backfill legacy descriptor-layer and registry files into canonical Layer 2 rows.

    Current migration behavior:
    - registry files are read from ``policies/image/registries/*.yaml|*.yml``
    - descriptor files are read from ``policies/image/descriptor_layers/*``
    - registry references are inferred from legacy path fields
    - descriptor references are inferred from successfully parsed registry refs
    - unchanged variants are skipped, changed variants are updated, new variants are imported
    """
    _ensure_world_exists(world_id)
    normalized_status = status.strip()
    if normalized_status not in _SUPPORTED_STATUSES:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_STATUS_INVALID",
            detail=(
                "Import status must be one of: draft, candidate, active, archived; "
                f"got {status!r}."
            ),
        )

    normalized_actor = actor.strip() or "policy-importer"
    world_root = _resolve_world_root_path(world_id)
    descriptor_root = world_root / _DESCRIPTOR_SOURCE_RELATIVE_DIR
    registry_root = world_root / _REGISTRY_SOURCE_RELATIVE_DIR

    descriptor_files = (
        sorted(
            [
                *descriptor_root.glob("*.txt"),
                *descriptor_root.glob("*.json"),
                *descriptor_root.glob("*.yaml"),
                *descriptor_root.glob("*.yml"),
            ],
            key=lambda path: path.name,
        )
        if descriptor_root.exists() and descriptor_root.is_dir()
        else []
    )
    registry_files = (
        sorted(
            [*registry_root.glob("*.yaml"), *registry_root.glob("*.yml")],
            key=lambda path: path.name,
        )
        if registry_root.exists() and registry_root.is_dir()
        else []
    )
    if not descriptor_files and not registry_files:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_LAYER2_SOURCE_NOT_FOUND",
            detail=(
                "Layer 2 source directories not found under world root: "
                f"{descriptor_root} and {registry_root}"
            ),
        )

    entries: list[Layer2ImportEntry] = []
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    activation_targets: dict[str, str] = {}
    descriptor_reference_pool: set[tuple[str, str]] = set()

    for registry_path in registry_files:
        source_path = str(registry_path)
        try:
            payload = _read_registry_yaml_payload(registry_path)
            policy_key, variant, policy_version = _resolve_registry_identity(
                registry_path=registry_path,
                payload=payload,
            )
            references = _extract_registry_references(payload=payload, registry_path=registry_path)
            content = {"references": references}
            policy_id = f"registry:image.registries:{policy_key}"
            existing_row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
            if _is_policy_variant_unchanged(
                existing_row=existing_row,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
            ):
                skipped_count += 1
                entries.append(
                    Layer2ImportEntry(
                        source_path=source_path,
                        policy_id=policy_id,
                        variant=variant,
                        action="skipped",
                        detail="unchanged",
                    )
                )
                for reference in references:
                    descriptor_reference_pool.add((reference["policy_id"], reference["variant"]))
                activation_targets[policy_id] = variant
                continue

            upsert_policy_variant(
                policy_id=policy_id,
                variant=variant,
                schema_version=_POLICY_SCHEMA_VERSION_V1,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
                updated_by=normalized_actor,
            )
            action = "imported" if existing_row is None else "updated"
            if action == "imported":
                imported_count += 1
            else:
                updated_count += 1
            entries.append(
                Layer2ImportEntry(
                    source_path=source_path,
                    policy_id=policy_id,
                    variant=variant,
                    action=action,
                    detail=f"{action} {policy_id}:{variant}",
                )
            )
            for reference in references:
                descriptor_reference_pool.add((reference["policy_id"], reference["variant"]))
            activation_targets[policy_id] = variant
        except (PolicyServiceError, ValueError, OSError) as exc:
            error_count += 1
            entries.append(
                Layer2ImportEntry(
                    source_path=source_path,
                    policy_id=None,
                    variant=None,
                    action="error",
                    detail=str(exc),
                )
            )

    descriptor_references = [
        {"policy_id": policy_id, "variant": variant}
        for policy_id, variant in sorted(descriptor_reference_pool)
    ]
    for descriptor_path in descriptor_files:
        source_path = str(descriptor_path)
        try:
            policy_key, variant, policy_version = _parse_descriptor_filename(descriptor_path)
            # Ensure descriptor source files are still readable for audit and diagnostics.
            descriptor_path.read_text(encoding="utf-8")
            if not descriptor_references:
                raise ValueError(
                    "Descriptor import could not infer Layer 1 references from registry files. "
                    "Import valid registries first."
                )

            content = {"references": descriptor_references}
            policy_id = f"descriptor_layer:image.descriptors:{policy_key}"
            existing_row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
            if _is_policy_variant_unchanged(
                existing_row=existing_row,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
            ):
                skipped_count += 1
                entries.append(
                    Layer2ImportEntry(
                        source_path=source_path,
                        policy_id=policy_id,
                        variant=variant,
                        action="skipped",
                        detail="unchanged",
                    )
                )
                activation_targets[policy_id] = variant
                continue

            upsert_policy_variant(
                policy_id=policy_id,
                variant=variant,
                schema_version=_POLICY_SCHEMA_VERSION_V1,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
                updated_by=normalized_actor,
            )
            action = "imported" if existing_row is None else "updated"
            if action == "imported":
                imported_count += 1
            else:
                updated_count += 1
            entries.append(
                Layer2ImportEntry(
                    source_path=source_path,
                    policy_id=policy_id,
                    variant=variant,
                    action=action,
                    detail=f"{action} {policy_id}:{variant}",
                )
            )
            activation_targets[policy_id] = variant
        except (PolicyServiceError, ValueError, OSError) as exc:
            error_count += 1
            entries.append(
                Layer2ImportEntry(
                    source_path=source_path,
                    policy_id=None,
                    variant=None,
                    action="error",
                    detail=str(exc),
                )
            )

    activated_count = 0
    activation_skipped_count = 0
    if activate and activation_targets:
        current_activations = {
            str(row["policy_id"]): str(row["variant"])
            for row in policy_repo.list_policy_activations(world_id=world_id, client_profile="")
        }
        world_scope = ActivationScope(world_id=world_id, client_profile="")
        for policy_id in sorted(activation_targets):
            target_variant = activation_targets[policy_id]
            if current_activations.get(policy_id) == target_variant:
                activation_skipped_count += 1
                continue
            try:
                set_policy_activation(
                    scope=world_scope,
                    policy_id=policy_id,
                    variant=target_variant,
                    activated_by=normalized_actor,
                )
                current_activations[policy_id] = target_variant
                activated_count += 1
            except PolicyServiceError as exc:
                error_count += 1
                entries.append(
                    Layer2ImportEntry(
                        source_path="<activation>",
                        policy_id=policy_id,
                        variant=target_variant,
                        action="error",
                        detail=f"activation failed: {exc.detail}",
                    )
                )

    return Layer2ImportSummary(
        world_id=world_id,
        activate=activate,
        scanned_descriptor_files=len(descriptor_files),
        scanned_registry_files=len(registry_files),
        imported_count=imported_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        activated_count=activated_count,
        activation_skipped_count=activation_skipped_count,
        entries=entries,
    )


def import_tone_prompt_policies_from_legacy_files(
    *,
    world_id: str,
    actor: str,
    activate: bool,
    status: str = "active",
) -> TonePromptImportSummary:
    """Backfill legacy tone-profile/prompt files into canonical Layer 1 policy rows.

    Current migration behavior:
    - tone profiles are read from ``policies/image/tone_profiles/*.json``
    - prompts are read from ``policies/translation/prompts/**/*.txt`` and
      ``policies/image/prompts/**/*.txt``
    - unchanged variants are skipped, changed variants are updated, and new variants
      are imported
    - optional world-scope activation only mutates pointers when needed
    """
    _ensure_world_exists(world_id)
    normalized_status = status.strip()
    if normalized_status not in _SUPPORTED_STATUSES:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_STATUS_INVALID",
            detail=(
                "Import status must be one of: draft, candidate, active, archived; "
                f"got {status!r}."
            ),
        )

    normalized_actor = actor.strip() or "policy-importer"
    world_root = _resolve_world_root_path(world_id)
    tone_profile_root = world_root / _TONE_PROFILE_SOURCE_RELATIVE_DIR
    translation_prompt_root = world_root / _PROMPT_TRANSLATION_SOURCE_RELATIVE_DIR
    image_prompt_root = world_root / _PROMPT_IMAGE_SOURCE_RELATIVE_DIR

    tone_profile_files = (
        sorted(tone_profile_root.glob("*.json"), key=lambda path: path.name)
        if tone_profile_root.exists() and tone_profile_root.is_dir()
        else []
    )
    prompt_files: list[Path] = []
    for prompt_root in (translation_prompt_root, image_prompt_root):
        if prompt_root.exists() and prompt_root.is_dir():
            prompt_files.extend(path for path in prompt_root.rglob("*.txt") if path.is_file())
    prompt_files = sorted(
        prompt_files,
        key=lambda path: str(path.relative_to(world_root)).replace("\\", "/"),
    )

    if not tone_profile_files and not prompt_files:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_TONE_PROMPT_SOURCE_NOT_FOUND",
            detail=(
                "Tone profile/prompt source directories not found under world root: "
                f"{tone_profile_root}, {translation_prompt_root}, and {image_prompt_root}"
            ),
        )

    entries: list[TonePromptImportEntry] = []
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    activation_targets: dict[str, str] = {}

    for tone_profile_path in tone_profile_files:
        source_path = str(tone_profile_path)
        try:
            policy_key, variant, policy_version = _parse_tone_profile_filename(tone_profile_path)
            content = _read_tone_profile_json_content(tone_profile_path)
            policy_id = f"tone_profile:image.tone_profiles:{policy_key}"
            existing_row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
            if _is_policy_variant_unchanged(
                existing_row=existing_row,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
            ):
                skipped_count += 1
                entries.append(
                    TonePromptImportEntry(
                        source_path=source_path,
                        policy_id=policy_id,
                        variant=variant,
                        action="skipped",
                        detail="unchanged",
                    )
                )
                activation_targets[policy_id] = variant
                continue

            upsert_policy_variant(
                policy_id=policy_id,
                variant=variant,
                schema_version=_POLICY_SCHEMA_VERSION_V1,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
                updated_by=normalized_actor,
            )
            action = "imported" if existing_row is None else "updated"
            if action == "imported":
                imported_count += 1
            else:
                updated_count += 1
            entries.append(
                TonePromptImportEntry(
                    source_path=source_path,
                    policy_id=policy_id,
                    variant=variant,
                    action=action,
                    detail=f"{action} {policy_id}:{variant}",
                )
            )
            activation_targets[policy_id] = variant
        except (PolicyServiceError, ValueError, OSError) as exc:
            error_count += 1
            entries.append(
                TonePromptImportEntry(
                    source_path=source_path,
                    policy_id=None,
                    variant=None,
                    action="error",
                    detail=str(exc),
                )
            )

    for prompt_path in prompt_files:
        source_path = str(prompt_path)
        try:
            namespace, policy_key, variant, policy_version = _parse_prompt_file_identity(
                prompt_path=prompt_path,
                world_root=world_root,
            )
            prompt_text = _read_prompt_text_content(prompt_path)
            policy_id = f"prompt:{namespace}:{policy_key}"
            content = {"text": prompt_text}
            existing_row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
            if _is_policy_variant_unchanged(
                existing_row=existing_row,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
            ):
                skipped_count += 1
                entries.append(
                    TonePromptImportEntry(
                        source_path=source_path,
                        policy_id=policy_id,
                        variant=variant,
                        action="skipped",
                        detail="unchanged",
                    )
                )
                activation_targets[policy_id] = variant
                continue

            upsert_policy_variant(
                policy_id=policy_id,
                variant=variant,
                schema_version=_POLICY_SCHEMA_VERSION_V1,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
                updated_by=normalized_actor,
            )
            action = "imported" if existing_row is None else "updated"
            if action == "imported":
                imported_count += 1
            else:
                updated_count += 1
            entries.append(
                TonePromptImportEntry(
                    source_path=source_path,
                    policy_id=policy_id,
                    variant=variant,
                    action=action,
                    detail=f"{action} {policy_id}:{variant}",
                )
            )
            activation_targets[policy_id] = variant
        except (PolicyServiceError, ValueError, OSError) as exc:
            error_count += 1
            entries.append(
                TonePromptImportEntry(
                    source_path=source_path,
                    policy_id=None,
                    variant=None,
                    action="error",
                    detail=str(exc),
                )
            )

    activated_count = 0
    activation_skipped_count = 0
    if activate and activation_targets:
        current_activations = {
            str(row["policy_id"]): str(row["variant"])
            for row in policy_repo.list_policy_activations(world_id=world_id, client_profile="")
        }
        world_scope = ActivationScope(world_id=world_id, client_profile="")
        for policy_id in sorted(activation_targets):
            target_variant = activation_targets[policy_id]
            if current_activations.get(policy_id) == target_variant:
                activation_skipped_count += 1
                continue
            try:
                set_policy_activation(
                    scope=world_scope,
                    policy_id=policy_id,
                    variant=target_variant,
                    activated_by=normalized_actor,
                )
                current_activations[policy_id] = target_variant
                activated_count += 1
            except PolicyServiceError as exc:
                error_count += 1
                entries.append(
                    TonePromptImportEntry(
                        source_path="<activation>",
                        policy_id=policy_id,
                        variant=target_variant,
                        action="error",
                        detail=f"activation failed: {exc.detail}",
                    )
                )

    return TonePromptImportSummary(
        world_id=world_id,
        activate=activate,
        scanned_tone_profile_files=len(tone_profile_files),
        scanned_prompt_files=len(prompt_files),
        imported_count=imported_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        activated_count=activated_count,
        activation_skipped_count=activation_skipped_count,
        entries=entries,
    )


def import_clothing_block_policies_from_legacy_files(
    *,
    world_id: str,
    actor: str,
    activate: bool,
    status: str = "active",
) -> ClothingImportSummary:
    """Backfill legacy clothing block text files into canonical Layer 1 rows.

    Source path:
    ``data/worlds/<world_id>/policies/image/blocks/clothing/**/*.txt``.
    """
    _ensure_world_exists(world_id)
    normalized_status = status.strip()
    if normalized_status not in _SUPPORTED_STATUSES:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_STATUS_INVALID",
            detail=(
                "Import status must be one of: draft, candidate, active, archived; "
                f"got {status!r}."
            ),
        )

    normalized_actor = actor.strip() or "policy-importer"
    world_root = _resolve_world_root_path(world_id)
    clothing_root = world_root / _CLOTHING_BLOCK_SOURCE_RELATIVE_DIR
    if not clothing_root.exists() or not clothing_root.is_dir():
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_CLOTHING_SOURCE_NOT_FOUND",
            detail=f"Clothing source directory not found: {clothing_root}",
        )

    clothing_files = sorted(
        [path for path in clothing_root.rglob("*.txt") if path.is_file()],
        key=lambda path: str(path.relative_to(world_root)).replace("\\", "/"),
    )
    if not clothing_files:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_CLOTHING_SOURCE_NOT_FOUND",
            detail=f"No clothing block source files found under: {clothing_root}",
        )

    entries: list[ClothingImportEntry] = []
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    activation_targets: dict[str, str] = {}

    for clothing_path in clothing_files:
        source_path = str(clothing_path)
        try:
            namespace, policy_key, variant, policy_version = _parse_clothing_block_file_identity(
                clothing_path=clothing_path,
                world_root=world_root,
            )
            content = {"text": _read_prompt_text_content(clothing_path)}
            policy_id = f"clothing_block:{namespace}:{policy_key}"
            existing_row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
            if _is_policy_variant_unchanged(
                existing_row=existing_row,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
            ):
                skipped_count += 1
                entries.append(
                    ClothingImportEntry(
                        source_path=source_path,
                        policy_id=policy_id,
                        variant=variant,
                        action="skipped",
                        detail="unchanged",
                    )
                )
                activation_targets[policy_id] = variant
                continue

            upsert_policy_variant(
                policy_id=policy_id,
                variant=variant,
                schema_version=_POLICY_SCHEMA_VERSION_V1,
                policy_version=policy_version,
                status=normalized_status,
                content=content,
                updated_by=normalized_actor,
            )
            action = "imported" if existing_row is None else "updated"
            if action == "imported":
                imported_count += 1
            else:
                updated_count += 1
            entries.append(
                ClothingImportEntry(
                    source_path=source_path,
                    policy_id=policy_id,
                    variant=variant,
                    action=action,
                    detail=f"{action} {policy_id}:{variant}",
                )
            )
            activation_targets[policy_id] = variant
        except (PolicyServiceError, ValueError, OSError) as exc:
            error_count += 1
            entries.append(
                ClothingImportEntry(
                    source_path=source_path,
                    policy_id=None,
                    variant=None,
                    action="error",
                    detail=str(exc),
                )
            )

    activated_count = 0
    activation_skipped_count = 0
    if activate and activation_targets:
        current_activations = {
            str(row["policy_id"]): str(row["variant"])
            for row in policy_repo.list_policy_activations(world_id=world_id, client_profile="")
        }
        world_scope = ActivationScope(world_id=world_id, client_profile="")
        for policy_id in sorted(activation_targets):
            target_variant = activation_targets[policy_id]
            if current_activations.get(policy_id) == target_variant:
                activation_skipped_count += 1
                continue
            try:
                set_policy_activation(
                    scope=world_scope,
                    policy_id=policy_id,
                    variant=target_variant,
                    activated_by=normalized_actor,
                )
                current_activations[policy_id] = target_variant
                activated_count += 1
            except PolicyServiceError as exc:
                error_count += 1
                entries.append(
                    ClothingImportEntry(
                        source_path="<activation>",
                        policy_id=policy_id,
                        variant=target_variant,
                        action="error",
                        detail=f"activation failed: {exc.detail}",
                    )
                )

    return ClothingImportSummary(
        world_id=world_id,
        activate=activate,
        scanned_clothing_files=len(clothing_files),
        imported_count=imported_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        activated_count=activated_count,
        activation_skipped_count=activation_skipped_count,
        entries=entries,
    )


def import_axis_manifest_policies_from_legacy_files(
    *,
    world_id: str,
    actor: str,
    activate: bool,
    status: str = "active",
) -> AxisManifestImportSummary:
    """Backfill manifest + axis bundle files into canonical policy rows.

    Imported policy types:
    1. ``manifest_bundle`` with content ``{"manifest": <manifest_yaml>}``
    2. ``axis_bundle`` with content ``{"axes": ..., "thresholds": ..., "resolution": ...}``
    """
    _ensure_world_exists(world_id)
    normalized_status = status.strip()
    if normalized_status not in _SUPPORTED_STATUSES:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_STATUS_INVALID",
            detail=(
                "Import status must be one of: draft, candidate, active, archived; "
                f"got {status!r}."
            ),
        )

    normalized_actor = actor.strip() or "policy-importer"
    world_root = _resolve_world_root_path(world_id)
    manifest_path = world_root / _MANIFEST_SOURCE_RELATIVE_PATH
    if not manifest_path.exists() or not manifest_path.is_file():
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_MANIFEST_SOURCE_NOT_FOUND",
            detail=f"Manifest source file not found: {manifest_path}",
        )

    entries: list[AxisManifestImportEntry] = []
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    activation_targets: dict[str, str] = {}
    scanned_files = 1

    manifest_payload = _read_manifest_yaml_payload(manifest_path)

    # Import manifest bundle object.
    try:
        manifest_version = _resolve_positive_int_version(
            value=((manifest_payload.get("policy_bundle") or {}).get("version")),
            default=1,
            context=f"Manifest file {manifest_path} policy_bundle.version",
        )
        manifest_variant = f"v{manifest_version}"
        manifest_policy_id = f"manifest_bundle:world.manifests:{world_id}"
        manifest_content = {"manifest": manifest_payload}
        existing_manifest = policy_repo.get_policy(
            policy_id=manifest_policy_id, variant=manifest_variant
        )
        if _is_policy_variant_unchanged(
            existing_row=existing_manifest,
            policy_version=manifest_version,
            status=normalized_status,
            content=manifest_content,
        ):
            skipped_count += 1
            entries.append(
                AxisManifestImportEntry(
                    source_path=str(manifest_path),
                    policy_id=manifest_policy_id,
                    variant=manifest_variant,
                    action="skipped",
                    detail="unchanged",
                )
            )
            activation_targets[manifest_policy_id] = manifest_variant
        else:
            upsert_policy_variant(
                policy_id=manifest_policy_id,
                variant=manifest_variant,
                schema_version=_POLICY_SCHEMA_VERSION_V1,
                policy_version=manifest_version,
                status=normalized_status,
                content=manifest_content,
                updated_by=normalized_actor,
            )
            manifest_action = "imported" if existing_manifest is None else "updated"
            if manifest_action == "imported":
                imported_count += 1
            else:
                updated_count += 1
            entries.append(
                AxisManifestImportEntry(
                    source_path=str(manifest_path),
                    policy_id=manifest_policy_id,
                    variant=manifest_variant,
                    action=manifest_action,
                    detail=f"{manifest_action} {manifest_policy_id}:{manifest_variant}",
                )
            )
            activation_targets[manifest_policy_id] = manifest_variant
    except (PolicyServiceError, ValueError, OSError) as exc:
        error_count += 1
        entries.append(
            AxisManifestImportEntry(
                source_path=str(manifest_path),
                policy_id=None,
                variant=None,
                action="error",
                detail=str(exc),
            )
        )

    # Import axis bundle object referenced by the manifest.
    try:
        axis_active_bundle = (manifest_payload.get("axis") or {}).get("active_bundle") or {}
        if not isinstance(axis_active_bundle, dict):
            raise ValueError("Manifest axis.active_bundle must be an object.")
        axis_bundle_id = str(axis_active_bundle.get("id", "")).strip()
        if not axis_bundle_id:
            raise ValueError("Manifest axis.active_bundle.id must be a non-empty string.")
        axis_bundle_version = _resolve_positive_int_version(
            value=axis_active_bundle.get("version"),
            default=1,
            context=f"Manifest file {manifest_path} axis.active_bundle.version",
        )
        axis_bundle_variant = f"v{axis_bundle_version}"

        axis_files = axis_active_bundle.get("files") or {}
        if not isinstance(axis_files, dict):
            raise ValueError("Manifest axis.active_bundle.files must be an object.")
        axes_rel_path = _require_manifest_relative_file_path(
            axis_files=axis_files,
            key="axes",
            context=f"Manifest file {manifest_path}",
        )
        thresholds_rel_path = _require_manifest_relative_file_path(
            axis_files=axis_files,
            key="thresholds",
            context=f"Manifest file {manifest_path}",
        )
        resolution_rel_path = _require_manifest_relative_file_path(
            axis_files=axis_files,
            key="resolution",
            context=f"Manifest file {manifest_path}",
        )

        axes_path = _resolve_world_relative_path(world_root=world_root, relative_path=axes_rel_path)
        thresholds_path = _resolve_world_relative_path(
            world_root=world_root, relative_path=thresholds_rel_path
        )
        resolution_path = _resolve_world_relative_path(
            world_root=world_root, relative_path=resolution_rel_path
        )
        scanned_files += 3

        axes_payload = _read_yaml_payload_file(axes_path, context=f"Axis bundle file {axes_path}")
        thresholds_payload = _read_yaml_payload_file(
            thresholds_path, context=f"Axis bundle file {thresholds_path}"
        )
        resolution_payload = _read_yaml_payload_file(
            resolution_path, context=f"Axis bundle file {resolution_path}"
        )
        axis_policy_id = f"axis_bundle:axis.bundles:{axis_bundle_id}"
        axis_content = {
            "axes": axes_payload,
            "thresholds": thresholds_payload,
            "resolution": resolution_payload,
        }
        existing_axis_bundle = policy_repo.get_policy(
            policy_id=axis_policy_id, variant=axis_bundle_variant
        )
        if _is_policy_variant_unchanged(
            existing_row=existing_axis_bundle,
            policy_version=axis_bundle_version,
            status=normalized_status,
            content=axis_content,
        ):
            skipped_count += 1
            entries.append(
                AxisManifestImportEntry(
                    source_path=str(manifest_path),
                    policy_id=axis_policy_id,
                    variant=axis_bundle_variant,
                    action="skipped",
                    detail="unchanged",
                )
            )
            activation_targets[axis_policy_id] = axis_bundle_variant
        else:
            upsert_policy_variant(
                policy_id=axis_policy_id,
                variant=axis_bundle_variant,
                schema_version=_POLICY_SCHEMA_VERSION_V1,
                policy_version=axis_bundle_version,
                status=normalized_status,
                content=axis_content,
                updated_by=normalized_actor,
            )
            axis_action = "imported" if existing_axis_bundle is None else "updated"
            if axis_action == "imported":
                imported_count += 1
            else:
                updated_count += 1
            entries.append(
                AxisManifestImportEntry(
                    source_path=str(manifest_path),
                    policy_id=axis_policy_id,
                    variant=axis_bundle_variant,
                    action=axis_action,
                    detail=f"{axis_action} {axis_policy_id}:{axis_bundle_variant}",
                )
            )
            activation_targets[axis_policy_id] = axis_bundle_variant
    except (PolicyServiceError, ValueError, OSError) as exc:
        error_count += 1
        entries.append(
            AxisManifestImportEntry(
                source_path=str(manifest_path),
                policy_id=None,
                variant=None,
                action="error",
                detail=str(exc),
            )
        )

    activated_count = 0
    activation_skipped_count = 0
    if activate and activation_targets:
        current_activations = {
            str(row["policy_id"]): str(row["variant"])
            for row in policy_repo.list_policy_activations(world_id=world_id, client_profile="")
        }
        world_scope = ActivationScope(world_id=world_id, client_profile="")
        for policy_id in sorted(activation_targets):
            target_variant = activation_targets[policy_id]
            if current_activations.get(policy_id) == target_variant:
                activation_skipped_count += 1
                continue
            try:
                set_policy_activation(
                    scope=world_scope,
                    policy_id=policy_id,
                    variant=target_variant,
                    activated_by=normalized_actor,
                )
                current_activations[policy_id] = target_variant
                activated_count += 1
            except PolicyServiceError as exc:
                error_count += 1
                entries.append(
                    AxisManifestImportEntry(
                        source_path="<activation>",
                        policy_id=policy_id,
                        variant=target_variant,
                        action="error",
                        detail=f"activation failed: {exc.detail}",
                    )
                )

    return AxisManifestImportSummary(
        world_id=world_id,
        activate=activate,
        scanned_files=scanned_files,
        imported_count=imported_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        activated_count=activated_count,
        activation_skipped_count=activation_skipped_count,
        entries=entries,
    )


def import_world_policies_from_legacy_files(
    *,
    world_id: str,
    actor: str,
    activate: bool,
    status: str = "active",
) -> WorldPolicyImportSummary:
    """Import all known legacy policy-like file domains for one world.

    The migration sequence is ordered to satisfy Layer 2 validation
    dependencies:
    1. species blocks
    2. tone profiles + prompts
    3. clothing blocks
    4. descriptor/registry Layer 2 objects
    5. axis bundle + manifest bundle
    """
    _ensure_world_exists(world_id)
    domain_entries: list[str] = []
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    activated_count = 0
    activation_skipped_count = 0

    def _accumulate(
        *,
        domain: str,
        summary: (
            SpeciesImportSummary
            | TonePromptImportSummary
            | ClothingImportSummary
            | Layer2ImportSummary
            | AxisManifestImportSummary
            | None
        ),
        error: PolicyServiceError | None = None,
    ) -> None:
        nonlocal imported_count
        nonlocal updated_count
        nonlocal skipped_count
        nonlocal error_count
        nonlocal activated_count
        nonlocal activation_skipped_count

        if error is not None:
            error_count += 1
            domain_entries.append(f"{domain}: error [{error.code}] {error.detail}")
            return
        if summary is None:
            error_count += 1
            domain_entries.append(f"{domain}: error [POLICY_IMPORT_UNKNOWN] missing summary")
            return
        imported_count += int(summary.imported_count)
        updated_count += int(summary.updated_count)
        skipped_count += int(summary.skipped_count)
        error_count += int(summary.error_count)
        activated_count += int(summary.activated_count)
        activation_skipped_count += int(summary.activation_skipped_count)
        domain_entries.append(
            f"{domain}: imported={summary.imported_count} updated={summary.updated_count} "
            f"skipped={summary.skipped_count} errors={summary.error_count}"
        )

    for domain, importer in (
        ("species", import_species_blocks_from_legacy_yaml),
        ("tone_prompt", import_tone_prompt_policies_from_legacy_files),
        ("clothing", import_clothing_block_policies_from_legacy_files),
        ("layer2", import_layer2_policies_from_legacy_files),
        ("axis_manifest", import_axis_manifest_policies_from_legacy_files),
    ):
        try:
            summary = importer(
                world_id=world_id,
                actor=actor,
                activate=activate,
                status=status,
            )
            _accumulate(domain=domain, summary=summary)
        except PolicyServiceError as exc:
            _accumulate(domain=domain, summary=None, error=exc)

    return WorldPolicyImportSummary(
        world_id=world_id,
        activate=activate,
        imported_count=imported_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        activated_count=activated_count,
        activation_skipped_count=activation_skipped_count,
        entries=domain_entries,
    )


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
        activation_row = policy_repo.set_policy_activation(
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
    _assert_activation_replay_consistency(scope=scope)
    return activation_row


def list_policy_activations(*, scope: ActivationScope) -> list[dict[str, Any]]:
    """List all active policy pointers for one scope."""
    _ensure_world_exists(scope.world_id)
    return policy_repo.list_policy_activations(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
    )


def resolve_effective_policy_activations(*, scope: ActivationScope) -> list[dict[str, Any]]:
    """Resolve effective active pointers for one runtime scope.

    Resolution rules:
    1. World-level (`client_profile == ""`) returns world-level pointers only.
    2. World+client scope overlays client pointers on top of world pointers by
       ``policy_id`` so client entries override world defaults.
    """
    _ensure_world_exists(scope.world_id)
    world_rows = policy_repo.list_policy_activations(
        world_id=scope.world_id,
        client_profile="",
    )
    if not scope.client_profile:
        return world_rows

    client_rows = policy_repo.list_policy_activations(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
    )
    merged_by_policy_id: dict[str, dict[str, Any]] = {
        str(row["policy_id"]): row for row in world_rows
    }
    for row in client_rows:
        merged_by_policy_id[str(row["policy_id"])] = row
    return [merged_by_policy_id[policy_id] for policy_id in sorted(merged_by_policy_id)]


def get_effective_policy_variant(
    *,
    scope: ActivationScope,
    policy_id: str,
) -> dict[str, Any] | None:
    """Return the effective active policy variant row for one scope + policy id.

    This helper keeps runtime callers from inferring activation state from
    ``status``. Runtime selection is driven exclusively by Layer 3 pointers.
    """
    _parse_policy_id(policy_id)
    effective_rows = resolve_effective_policy_activations(scope=scope)
    by_policy_id = {str(row["policy_id"]): row for row in effective_rows}
    activation = by_policy_id.get(policy_id)
    if activation is None:
        return None

    variant = str(activation["variant"])
    row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
    if row is None:
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_REFERENCE_MISSING",
            detail=f"Effective activation points to missing policy variant: {policy_id}:{variant}",
        )
    return row


def resolve_effective_prompt_template(
    *,
    scope: ActivationScope,
    preferred_policy_id: str | None = None,
    preferred_template_path: str | None,
) -> dict[str, str]:
    """Resolve the canonical effective prompt template for one scope.

    Selection rules:
    1. Resolve effective Layer 3 activation rows for the scope.
    2. Keep only ``prompt:*`` policy rows.
    3. If ``preferred_policy_id`` is provided, select that policy id from
       effective activations.
    4. Else if ``preferred_template_path`` maps to a canonical prompt policy id,
       select that policy id from effective activations.
    5. Otherwise, require exactly one effective prompt activation.
    6. Return canonical prompt metadata and ``content.text`` template value.
    """
    _ensure_world_exists(scope.world_id)

    selected_policy_id_hint: str | None = None
    if preferred_policy_id:
        identity = _parse_policy_id(preferred_policy_id)
        if identity.policy_type != "prompt":
            raise PolicyServiceError(
                status_code=422,
                code="POLICY_PROMPT_SELECTOR_INVALID",
                detail=(
                    "Configured prompt policy selector must reference a prompt policy_id; "
                    f"got {preferred_policy_id!r}."
                ),
            )
        selected_policy_id_hint = preferred_policy_id
    elif preferred_template_path:
        preferred_reference = _policy_reference_from_legacy_path(preferred_template_path)
        if preferred_reference is not None and str(
            preferred_reference.get("policy_id", "")
        ).startswith("prompt:"):
            selected_policy_id_hint = str(preferred_reference["policy_id"])

    effective_rows = resolve_effective_policy_activations(scope=scope)
    prompt_rows = [
        row for row in effective_rows if str(row.get("policy_id", "")).startswith("prompt:")
    ]
    if not prompt_rows:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_EFFECTIVE_PROMPT_NOT_FOUND",
            detail=(
                "No effective prompt activation found for scope "
                f"(world_id={scope.world_id!r}, client_profile={scope.client_profile!r})."
            ),
        )

    selected_activation: dict[str, Any] | None = None
    if selected_policy_id_hint is not None:
        for row in prompt_rows:
            if str(row["policy_id"]) == selected_policy_id_hint:
                selected_activation = row
                break
        if selected_activation is None:
            raise PolicyServiceError(
                status_code=404,
                code="POLICY_EFFECTIVE_PROMPT_NOT_FOUND",
                detail=(
                    "Configured prompt selector does not resolve to an effective prompt "
                    "activation "
                    f"(policy_id={preferred_policy_id!r}, template_path={preferred_template_path!r})."
                ),
            )
    elif len(prompt_rows) == 1:
        selected_activation = prompt_rows[0]
    else:
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_PROMPT_AMBIGUOUS",
            detail=(
                "Multiple effective prompt activations are present. Provide a configured "
                "prompt_policy_id (preferred) or prompt_template_path that maps to one "
                "canonical prompt policy."
            ),
        )

    selected_policy_id = str(selected_activation["policy_id"])
    selected_variant = str(selected_activation["variant"])
    selected_policy = policy_repo.get_policy(
        policy_id=selected_policy_id,
        variant=selected_variant,
    )
    if selected_policy is None:
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_REFERENCE_MISSING",
            detail=(
                "Effective prompt activation points to missing policy variant: "
                f"{selected_policy_id}:{selected_variant}"
            ),
        )

    content = selected_policy.get("content")
    if not isinstance(content, dict):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_EFFECTIVE_PROMPT_INVALID",
            detail="Effective prompt content must be an object.",
        )
    content_text = content.get("text")
    if not isinstance(content_text, str) or not content_text.strip():
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_EFFECTIVE_PROMPT_INVALID",
            detail="Effective prompt content.text must be a non-empty string.",
        )

    return {
        "policy_id": selected_policy_id,
        "variant": selected_variant,
        "namespace": str(selected_policy.get("namespace", "")),
        "policy_key": str(selected_policy.get("policy_key", "")),
        "content_text": content_text,
        "content_hash": str(selected_policy.get("content_hash", "")),
    }


def resolve_effective_axis_bundle(*, scope: ActivationScope) -> EffectiveAxisBundle:
    """Resolve canonical manifest + axis-bundle payloads for one runtime scope.

    Runtime callers should use this helper instead of reading any
    ``data/worlds/<world>/policies/*.yaml`` files directly. Resolution is fully
    activation-driven:
    1. Resolve active ``manifest_bundle`` variant for the scope.
    2. Read ``axis.active_bundle`` pointer from manifest content.
    3. Resolve active ``axis_bundle`` variant for that bundle id.
    4. Validate payload shape and return canonical bundle context.
    """
    _ensure_world_exists(scope.world_id)
    manifest_policy_id = f"manifest_bundle:world.manifests:{scope.world_id}"
    manifest_row = get_effective_policy_variant(scope=scope, policy_id=manifest_policy_id)
    if manifest_row is None:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_EFFECTIVE_MANIFEST_NOT_FOUND",
            detail=(
                "No effective manifest bundle activation found for scope "
                f"(world_id={scope.world_id!r}, client_profile={scope.client_profile!r})."
            ),
        )

    manifest_content = manifest_row.get("content")
    if not isinstance(manifest_content, dict):
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_MANIFEST_INVALID",
            detail="Effective manifest content must be an object.",
        )
    manifest_payload = manifest_content.get("manifest")
    if not isinstance(manifest_payload, dict):
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_MANIFEST_INVALID",
            detail="Effective manifest content missing object field: content.manifest.",
        )

    axis_active_bundle = (manifest_payload.get("axis") or {}).get("active_bundle")
    if not isinstance(axis_active_bundle, dict):
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_MANIFEST_INVALID",
            detail="Manifest field axis.active_bundle must be an object.",
        )
    bundle_id = str(axis_active_bundle.get("id", "")).strip()
    if not bundle_id:
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_MANIFEST_INVALID",
            detail="Manifest field axis.active_bundle.id must be a non-empty string.",
        )
    bundle_version_int = _resolve_positive_int_version(
        value=axis_active_bundle.get("version"),
        default=1,
        context="manifest axis.active_bundle.version",
    )
    bundle_version = str(bundle_version_int)
    expected_axis_variant = f"v{bundle_version_int}"
    axis_policy_id = f"axis_bundle:axis.bundles:{bundle_id}"
    axis_row = get_effective_policy_variant(scope=scope, policy_id=axis_policy_id)
    if axis_row is None:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_EFFECTIVE_AXIS_BUNDLE_NOT_FOUND",
            detail=(
                "No effective axis bundle activation found for manifest-selected bundle "
                f"{bundle_id!r} in scope (world_id={scope.world_id!r}, "
                f"client_profile={scope.client_profile!r})."
            ),
        )
    axis_variant = str(axis_row.get("variant", ""))
    if axis_variant != expected_axis_variant:
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_AXIS_BUNDLE_VERSION_MISMATCH",
            detail=(
                "Manifest selected axis bundle variant "
                f"{expected_axis_variant!r}, but activation points to {axis_variant!r} "
                f"for policy_id={axis_policy_id!r}."
            ),
        )

    axis_content = axis_row.get("content")
    if not isinstance(axis_content, dict):
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_AXIS_BUNDLE_INVALID",
            detail="Effective axis bundle content must be an object.",
        )
    axes_payload = axis_content.get("axes")
    thresholds_payload = axis_content.get("thresholds")
    resolution_payload = axis_content.get("resolution")
    if not isinstance(axes_payload, dict):
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_AXIS_BUNDLE_INVALID",
            detail="Effective axis bundle field content.axes must be an object.",
        )
    if not isinstance(thresholds_payload, dict):
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_AXIS_BUNDLE_INVALID",
            detail="Effective axis bundle field content.thresholds must be an object.",
        )
    if not isinstance(resolution_payload, dict):
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_AXIS_BUNDLE_INVALID",
            detail="Effective axis bundle field content.resolution must be an object.",
        )

    required_runtime_inputs_raw = (
        (manifest_payload.get("image") or {}).get("composition") or {}
    ).get("required_runtime_inputs") or []
    required_runtime_inputs = (
        {
            str(item).strip()
            for item in required_runtime_inputs_raw
            if isinstance(item, str) and str(item).strip()
        }
        if isinstance(required_runtime_inputs_raw, list)
        else set()
    )
    policy_hash = str(
        compute_payload_hash(
            {
                "manifest": manifest_payload,
                "axis_bundle": {
                    "axes": axes_payload,
                    "thresholds": thresholds_payload,
                    "resolution": resolution_payload,
                },
            }
        )
    )
    return EffectiveAxisBundle(
        manifest_policy_id=manifest_policy_id,
        manifest_variant=str(manifest_row["variant"]),
        axis_policy_id=axis_policy_id,
        axis_variant=axis_variant,
        bundle_id=bundle_id,
        bundle_version=bundle_version,
        manifest_payload=manifest_payload,
        axes_payload=axes_payload,
        thresholds_payload=thresholds_payload,
        resolution_payload=resolution_payload,
        required_runtime_inputs=required_runtime_inputs,
        policy_hash=policy_hash,
    )


def publish_scope(*, scope: ActivationScope, actor: str) -> dict[str, Any]:
    """Build and persist one deterministic publish manifest for a scope.

    The manifest includes only active variants for the requested scope and is
    sorted deterministically before hashing to guarantee stable output for
    equivalent activation sets.
    """
    _ensure_world_exists(scope.world_id)
    activations = resolve_effective_policy_activations(scope=scope)
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
    items_hash = str(compute_payload_hash({"items": manifest_items}))
    manifest_hash = str(
        compute_payload_hash(
            {
                "world_id": scope.world_id,
                "client_profile": scope.client_profile or None,
                "items_hash": items_hash,
                "item_count": len(manifest_items),
            }
        )
    )
    generated_at = _now_iso()
    manifest = {
        "world_id": scope.world_id,
        "client_profile": scope.client_profile or None,
        "generated_at": generated_at,
        "item_count": len(manifest_items),
        "items_hash": items_hash,
        "manifest_hash": manifest_hash,
        "items": manifest_items,
    }
    publish_run_id = policy_repo.insert_publish_run(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
        actor=actor,
        manifest=manifest,
        created_at=generated_at,
    )
    artifact = _materialize_publish_artifact(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
        manifest=manifest,
    )
    return {
        "publish_run_id": publish_run_id,
        "manifest": manifest,
        "artifact": artifact,
    }


def get_publish_run(*, publish_run_id: int) -> dict[str, Any]:
    """Get one publish run plus deterministic export artifact metadata."""
    run_row = policy_repo.get_publish_run(publish_run_id=publish_run_id)
    if run_row is None:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_PUBLISH_RUN_NOT_FOUND",
            detail=f"Publish run not found: {publish_run_id}",
        )
    world_id = str(run_row["world_id"])
    client_profile = str(run_row["client_profile"] or "")
    manifest = _normalize_manifest_for_export(
        world_id=world_id,
        client_profile=client_profile,
        manifest=run_row["manifest"],
    )
    artifact = _materialize_publish_artifact(
        world_id=world_id,
        client_profile=client_profile,
        manifest=manifest,
    )
    return {
        "publish_run_id": int(run_row["publish_run_id"]),
        "world_id": world_id,
        "client_profile": client_profile or None,
        "actor": str(run_row["actor"]),
        "created_at": str(run_row["created_at"]),
        "manifest": manifest,
        "artifact": artifact,
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


def _parse_species_filename(species_path: Path) -> tuple[str, str, int]:
    """Extract ``policy_key``, ``variant``, and version from species filename."""
    match = _SPECIES_FILENAME_PATTERN.fullmatch(species_path.stem)
    if match is None:
        raise ValueError(
            "Species filename must match '<policy_key>_v<version>.yaml'; "
            f"got {species_path.name!r}."
        )

    policy_key = match.group("policy_key")
    file_version = int(match.group("version"))
    return policy_key, f"v{file_version}", file_version


def _read_species_yaml_payload(species_path: Path) -> dict[str, Any]:
    """Read one legacy species YAML file into a dictionary payload."""
    try:
        loaded = yaml.safe_load(species_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise OSError(f"Unable to read species source file {species_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in species source file {species_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"Species source file {species_path} must contain a YAML object.")
    return loaded


def _resolve_species_policy_version(
    *,
    payload: dict[str, Any],
    file_policy_version: int,
    species_path: Path,
) -> int:
    """Resolve policy version from payload and ensure it matches filename version."""
    payload_version = payload.get("version")
    if payload_version is None:
        return file_policy_version

    if isinstance(payload_version, bool):
        raise ValueError(f"Species file {species_path} has invalid boolean version value.")

    if isinstance(payload_version, int):
        parsed_version = payload_version
    elif isinstance(payload_version, str) and payload_version.strip().isdigit():
        parsed_version = int(payload_version.strip())
    else:
        raise ValueError(
            f"Species file {species_path} version must be a positive integer; got {payload_version!r}."
        )

    if parsed_version < 1:
        raise ValueError(f"Species file {species_path} version must be >= 1.")
    if parsed_version != file_policy_version:
        raise ValueError(
            f"Species file {species_path} version={parsed_version} must match filename v{file_policy_version}."
        )
    return parsed_version


def _extract_species_text_content(
    *,
    payload: dict[str, Any],
    species_path: Path,
) -> dict[str, Any]:
    """Extract canonical species policy content payload from legacy YAML fields."""
    text_value = payload.get("text")
    if not isinstance(text_value, str) or not text_value.strip():
        raise ValueError(f"Species file {species_path} must define non-empty text content.")
    # Normalize trailing YAML block newline so repeated imports are stable.
    return {"text": text_value.rstrip()}


def _is_species_variant_unchanged(
    *,
    existing_row: dict[str, Any] | None,
    policy_version: int,
    status: str,
    content: dict[str, Any],
) -> bool:
    """Return ``True`` when existing species variant already matches import payload."""
    return _is_policy_variant_unchanged(
        existing_row=existing_row,
        policy_version=policy_version,
        status=status,
        content=content,
    )


def _parse_descriptor_filename(descriptor_path: Path) -> tuple[str, str, int]:
    """Extract ``policy_key``, ``variant``, and version from descriptor filename."""
    match = _DESCRIPTOR_FILENAME_PATTERN.fullmatch(descriptor_path.name)
    if match is None:
        raise ValueError(
            "Descriptor filename must match '<policy_key>_v<version>.(txt|json|yaml|yml)'; "
            f"got {descriptor_path.name!r}."
        )
    policy_key = match.group("policy_key")
    policy_version = int(match.group("version"))
    return policy_key, f"v{policy_version}", policy_version


def _parse_tone_profile_filename(tone_profile_path: Path) -> tuple[str, str, int]:
    """Extract ``policy_key``, ``variant``, and version from tone-profile filename."""
    match = _TONE_PROFILE_FILENAME_PATTERN.fullmatch(tone_profile_path.name)
    if match is None:
        raise ValueError(
            "Tone profile filename must match '<policy_key>_v<version>.json'; "
            f"got {tone_profile_path.name!r}."
        )
    policy_key = match.group("policy_key")
    policy_version = int(match.group("version"))
    return policy_key, f"v{policy_version}", policy_version


def _read_tone_profile_json_content(tone_profile_path: Path) -> dict[str, Any]:
    """Read one legacy tone-profile JSON file into dictionary content."""
    try:
        loaded = json.loads(tone_profile_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OSError(
            f"Unable to read tone profile source file {tone_profile_path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in tone profile source file {tone_profile_path}: {exc}"
        ) from exc
    if not isinstance(loaded, dict):
        raise ValueError(
            f"Tone profile source file {tone_profile_path} must contain a JSON object."
        )
    return loaded


def _parse_prompt_file_identity(
    *, prompt_path: Path, world_root: Path
) -> tuple[str, str, str, int]:
    """Resolve prompt namespace, policy_key, variant, and policy_version from file path."""
    match = _PROMPT_FILENAME_PATTERN.fullmatch(prompt_path.name)
    if match is None:
        raise ValueError(
            "Prompt filename must match '<policy_key>_v<version>.txt'; "
            f"got {prompt_path.name!r}."
        )

    policies_root = world_root / "policies"
    try:
        relative_path = prompt_path.relative_to(policies_root)
    except ValueError as exc:
        raise ValueError(
            f"Prompt source file {prompt_path} must be located under {policies_root}."
        ) from exc

    namespace_parts = relative_path.parts[:-1]
    if (
        len(namespace_parts) < 2
        or namespace_parts[0] not in {"image", "translation"}
        or namespace_parts[1] != "prompts"
    ):
        raise ValueError(
            f"Prompt source file {prompt_path} must be under "
            "'policies/image/prompts' or 'policies/translation/prompts'."
        )
    namespace = ".".join(namespace_parts)
    policy_key = match.group("policy_key")
    policy_version = int(match.group("version"))
    return namespace, policy_key, f"v{policy_version}", policy_version


def _parse_clothing_block_file_identity(
    *, clothing_path: Path, world_root: Path
) -> tuple[str, str, str, int]:
    """Resolve clothing namespace, policy_key, variant, and version from file path.

    Expected source location:
    ``policies/image/blocks/clothing/<category...>/<policy_key>_v<version>.txt``.
    """
    match = _CLOTHING_BLOCK_FILENAME_PATTERN.fullmatch(clothing_path.name)
    if match is None:
        raise ValueError(
            "Clothing block filename must match '<policy_key>_v<version>.txt'; "
            f"got {clothing_path.name!r}."
        )

    clothing_root = world_root / _CLOTHING_BLOCK_SOURCE_RELATIVE_DIR
    try:
        relative_path = clothing_path.relative_to(clothing_root)
    except ValueError as exc:
        raise ValueError(
            f"Clothing source file {clothing_path} must be located under {clothing_root}."
        ) from exc

    namespace_suffix = ".".join(relative_path.parts[:-1])
    namespace = "image.blocks.clothing"
    if namespace_suffix:
        namespace = f"{namespace}.{namespace_suffix}"
    policy_key = match.group("policy_key")
    policy_version = int(match.group("version"))
    return namespace, policy_key, f"v{policy_version}", policy_version


def _read_prompt_text_content(prompt_path: Path) -> str:
    """Read one legacy prompt text file and return trimmed non-empty text."""
    try:
        prompt_text = prompt_path.read_text(encoding="utf-8").rstrip()
    except OSError as exc:
        raise OSError(f"Unable to read prompt source file {prompt_path}: {exc}") from exc
    if not prompt_text.strip():
        raise ValueError(f"Prompt source file {prompt_path} must define non-empty text content.")
    return prompt_text


def _read_manifest_yaml_payload(manifest_path: Path) -> dict[str, Any]:
    """Read one world manifest YAML file into dictionary content."""
    try:
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise OSError(f"Unable to read manifest source file {manifest_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in manifest source file {manifest_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"Manifest source file {manifest_path} must contain a YAML object.")
    return loaded


def _require_manifest_relative_file_path(
    *, axis_files: dict[str, Any], key: str, context: str
) -> str:
    """Resolve one required axis-bundle file path from manifest payload."""
    raw_value = axis_files.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(f"{context} axis.active_bundle.files.{key} must be a non-empty string.")
    return raw_value.strip()


def _resolve_world_relative_path(*, world_root: Path, relative_path: str) -> Path:
    """Resolve one manifest-relative path against a world root with traversal guards."""
    normalized = relative_path.replace("\\", "/").strip()
    if not normalized:
        raise ValueError("Manifest file path must not be empty.")
    if normalized.startswith("./"):
        normalized = normalized[2:]

    normalized_path = PurePosixPath(normalized)
    if normalized_path.is_absolute():
        raise ValueError(f"Manifest file path must be relative: {relative_path!r}")
    if any(part == ".." for part in normalized_path.parts):
        raise ValueError(f"Manifest file path escapes world root: {relative_path!r}")

    candidate = (world_root / normalized_path.as_posix()).resolve()
    world_root_resolved = world_root.resolve()
    if not candidate.is_relative_to(world_root_resolved):
        raise ValueError(f"Manifest file path escapes world root: {relative_path!r}")
    return candidate


def _read_yaml_payload_file(path: Path, *, context: str) -> dict[str, Any]:
    """Read one referenced YAML file as dictionary payload."""
    if not path.exists() or not path.is_file():
        raise ValueError(f"{context} is missing.")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise OSError(f"Unable to read {context}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {context}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{context} must contain a YAML object.")
    return loaded


def _read_registry_yaml_payload(registry_path: Path) -> dict[str, Any]:
    """Read one legacy registry YAML file into a dictionary payload."""
    try:
        loaded = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise OSError(f"Unable to read registry source file {registry_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in registry source file {registry_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"Registry source file {registry_path} must contain a YAML object.")
    return loaded


def _resolve_registry_identity(
    *,
    registry_path: Path,
    payload: dict[str, Any],
) -> tuple[str, str, int]:
    """Resolve canonical registry identity tuple from filename and payload metadata."""
    filename_match = _REGISTRY_VERSIONED_FILENAME_PATTERN.fullmatch(registry_path.stem)
    registry_meta = payload.get("registry")
    if registry_meta is not None and not isinstance(registry_meta, dict):
        raise ValueError(f"Registry file {registry_path} field 'registry' must be an object.")

    payload_policy_key = str((registry_meta or {}).get("id", "")).strip()
    payload_version = (registry_meta or {}).get("version")
    if filename_match is not None:
        policy_key = filename_match.group("policy_key")
        file_version = int(filename_match.group("version"))
        resolved_version = _resolve_positive_int_version(
            value=payload_version,
            default=file_version,
            context=f"Registry file {registry_path} version",
        )
        if resolved_version != file_version:
            raise ValueError(
                f"Registry file {registry_path} version={resolved_version} must match "
                f"filename v{file_version}."
            )
        if payload_policy_key and payload_policy_key != policy_key:
            raise ValueError(
                f"Registry file {registry_path} id={payload_policy_key!r} must match "
                f"filename policy_key={policy_key!r}."
            )
        return policy_key, f"v{resolved_version}", resolved_version

    policy_key = payload_policy_key or registry_path.stem
    if not policy_key:
        raise ValueError(f"Registry file {registry_path} must define a non-empty policy key.")
    resolved_version = _resolve_positive_int_version(
        value=payload_version,
        default=None,
        context=f"Registry file {registry_path} registry.version",
    )
    return policy_key, f"v{resolved_version}", resolved_version


def _resolve_positive_int_version(*, value: Any, default: int | None, context: str) -> int:
    """Resolve one positive integer version value with strict type checks."""
    if value is None:
        if default is None:
            raise ValueError(f"{context} must be a positive integer.")
        return default
    if isinstance(value, bool):
        raise ValueError(f"{context} must not be a boolean.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise ValueError(f"{context} must be a positive integer; got {value!r}.")
    if parsed < 1:
        raise ValueError(f"{context} must be >= 1.")
    return parsed


def _extract_registry_references(
    *,
    payload: dict[str, Any],
    registry_path: Path,
) -> list[dict[str, str]]:
    """Extract canonical Layer 2 references from legacy registry payload fields."""
    explicit_references = payload.get("references")
    if explicit_references is not None:
        normalized = _normalize_reference_entries(
            references=explicit_references,
            policy_type="registry",
        )
        if normalized:
            return normalized

    candidates: list[str] = []
    entries = payload.get("entries")
    if isinstance(entries, list):
        candidates.extend(_collect_legacy_path_fields_from_entries(entries))
    slots = payload.get("slots")
    if isinstance(slots, dict):
        for slot_rows in slots.values():
            if isinstance(slot_rows, list):
                candidates.extend(_collect_legacy_path_fields_from_entries(slot_rows))

    resolved: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        reference = _policy_reference_from_legacy_path(candidate)
        if reference is None:
            continue
        identity = (reference["policy_id"], reference["variant"])
        if identity in seen:
            continue
        seen.add(identity)
        resolved.append(reference)
    if not resolved:
        raise ValueError(
            "Registry file "
            f"{registry_path} has no mappable Layer 1 references. "
            "Expected explicit content.references or legacy block/fragment/prompt/tone paths."
        )
    return resolved


def _normalize_reference_entries(*, references: Any, policy_type: str) -> list[dict[str, str]]:
    """Validate/normalize explicit Layer 2 references into canonical list form."""
    if not isinstance(references, list) or len(references) == 0:
        raise ValueError(f"{policy_type} content.references must be a non-empty list.")

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(references):
        if not isinstance(item, dict):
            raise ValueError(
                f"{policy_type} content.references[{index}] must be an object with "
                "'policy_id' and 'variant'."
            )
        policy_id = str(item.get("policy_id", "")).strip()
        variant = str(item.get("variant", "")).strip()
        if not policy_id:
            raise ValueError(f"{policy_type} content.references[{index}].policy_id is required.")
        if not variant:
            raise ValueError(f"{policy_type} content.references[{index}].variant is required.")
        normalized.append({"policy_id": policy_id, "variant": variant})
    return normalized


def _collect_legacy_path_fields_from_entries(entries: list[Any]) -> list[str]:
    """Return recognized legacy path values from one list of registry row objects."""
    values: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        for key in ("block_path", "fragment_path", "prompt_path", "tone_profile_path"):
            raw_value = item.get(key)
            if isinstance(raw_value, str) and raw_value.strip():
                values.append(raw_value.strip())
    return values


def _policy_reference_from_legacy_path(path_value: str) -> dict[str, str] | None:
    """Map one legacy path value to canonical Layer 1 policy id + variant."""
    normalized = path_value.replace("\\", "/").strip().lstrip("./")

    species_match = _LEGACY_SPECIES_BLOCK_PATH_PATTERN.fullmatch(normalized)
    if species_match is not None:
        return {
            "policy_id": f"species_block:image.blocks.species:{species_match.group('policy_key')}",
            "variant": species_match.group("variant"),
        }

    clothing_match = _LEGACY_CLOTHING_BLOCK_PATH_PATTERN.fullmatch(normalized)
    if clothing_match is not None:
        namespace = "image.blocks.clothing"
        namespace_path = clothing_match.group("namespace_path").strip("/")
        if namespace_path:
            namespace = f"{namespace}.{namespace_path.replace('/', '.')}"
        return {
            "policy_id": f"clothing_block:{namespace}:{clothing_match.group('policy_key')}",
            "variant": clothing_match.group("variant"),
        }

    prompt_match = _LEGACY_PROMPT_PATH_PATTERN.fullmatch(normalized)
    if prompt_match is not None:
        namespace = prompt_match.group("namespace_path").replace("/", ".")
        return {
            "policy_id": f"prompt:{namespace}:{prompt_match.group('policy_key')}",
            "variant": prompt_match.group("variant"),
        }

    tone_match = _LEGACY_TONE_PROFILE_PATH_PATTERN.fullmatch(normalized)
    if tone_match is not None:
        return {
            "policy_id": f"tone_profile:image.tone_profiles:{tone_match.group('policy_key')}",
            "variant": tone_match.group("variant"),
        }

    return None


def _is_policy_variant_unchanged(
    *,
    existing_row: dict[str, Any] | None,
    policy_version: int,
    status: str,
    content: dict[str, Any],
) -> bool:
    """Return ``True`` when existing variant row already matches import payload."""
    if existing_row is None:
        return False

    return (
        str(existing_row["schema_version"]) == _POLICY_SCHEMA_VERSION_V1
        and int(existing_row["policy_version"]) == policy_version
        and str(existing_row["status"]) == status
        and isinstance(existing_row.get("content"), dict)
        and existing_row["content"] == content
    )


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

    Phase 5 extends Layer 1 writes beyond the ``species_block`` pilot to
    include ``tone_profile`` and ``prompt`` objects while preserving existing
    Layer 2 composition contract checks for ``descriptor_layer`` and
    ``registry``.
    """
    errors: list[str] = []
    if identity.policy_type == _SPECIES_PILOT_POLICY_TYPE:
        if identity.namespace != _SPECIES_PILOT_NAMESPACE:
            errors.append(
                "species_block namespace must be exactly 'image.blocks.species' in Phase 1."
            )
        text_value = content.get("text")
        if not isinstance(text_value, str) or not text_value.strip():
            errors.append("species_block content.text must be a non-empty string")
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

    if identity.policy_type == "clothing_block":
        clothing_text = content.get("text")
        if not isinstance(clothing_text, str) or not clothing_text.strip():
            errors.append("clothing_block content.text must be a non-empty string")
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
        return errors

    errors.append(
        "Validation/writes currently support policy_type values: "
        "'species_block', 'clothing_block', 'prompt', 'tone_profile', "
        "'axis_bundle', 'manifest_bundle', 'descriptor_layer', 'registry'."
    )
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


def _validate_layer2_references(*, content: dict[str, Any]) -> list[str]:
    """Validate Layer 2 composition references against Layer 1 identities.

    Expected payload shape:
    ``{"references": [{"policy_id": "...", "variant": "..."}]}``
    """
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
            referenced_identity = _parse_policy_id(referenced_policy_id.strip())
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


def _assert_activation_replay_consistency(*, scope: ActivationScope) -> None:
    """Verify activation pointers are replayable from activation audit events.

    This invariant guarantees deterministic state reconstruction for one scope.
    """
    try:
        active_rows = policy_repo.list_policy_activations(
            world_id=scope.world_id,
            client_profile=scope.client_profile,
        )
        activation_events = policy_repo.list_activation_events(
            world_id=scope.world_id,
            client_profile=scope.client_profile,
        )
    except Exception as exc:
        raise PolicyServiceError(
            status_code=500,
            code="POLICY_AUDIT_REPLAY_READ_ERROR",
            detail=str(exc),
        ) from exc

    pointer_state = _activation_map_from_rows(active_rows)
    replay_state: dict[str, str] = {}
    for event in activation_events:
        replay_state[str(event["policy_id"])] = str(event["variant"])

    if replay_state != pointer_state:
        raise PolicyServiceError(
            status_code=500,
            code="POLICY_ACTIVATION_REPLAY_MISMATCH",
            detail=(
                "Activation pointer state does not match replayed activation events "
                f"for scope {scope.world_id}:{scope.client_profile}."
            ),
        )


def _activation_map_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Return ``policy_id -> variant`` map from activation row dictionaries."""
    return {str(row["policy_id"]): str(row["variant"]) for row in rows}


def _normalize_manifest_for_export(
    *,
    world_id: str,
    client_profile: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Return manifest with deterministic hash fields populated.

    Older publish rows may predate ``items_hash`` support; this helper fills
    missing fields so export artifacts stay stable across schema evolution.
    """
    normalized = dict(manifest)
    items_raw = normalized.get("items")
    if not isinstance(items_raw, list):
        items_raw = []
    items: list[dict[str, Any]] = [dict(item) for item in items_raw if isinstance(item, dict)]
    items.sort(
        key=lambda item: (
            str(item.get("policy_type", "")),
            str(item.get("namespace", "")),
            str(item.get("policy_key", "")),
        )
    )
    normalized["items"] = items
    normalized["item_count"] = int(normalized.get("item_count", len(items)))
    normalized["world_id"] = world_id
    normalized["client_profile"] = client_profile or None

    items_hash = str(normalized.get("items_hash") or compute_payload_hash({"items": items}))
    normalized["items_hash"] = items_hash
    manifest_hash = str(
        normalized.get("manifest_hash")
        or compute_payload_hash(
            {
                "world_id": world_id,
                "client_profile": client_profile or None,
                "items_hash": items_hash,
                "item_count": normalized["item_count"],
            }
        )
    )
    normalized["manifest_hash"] = manifest_hash
    return normalized


def _materialize_publish_artifact(
    *,
    world_id: str,
    client_profile: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Write deterministic export artifact and return artifact metadata.

    The artifact is intentionally non-authoritative. Runtime selection remains
    sourced from Layer 3 activation pointers and canonical DB state.
    """
    normalized_manifest = _normalize_manifest_for_export(
        world_id=world_id,
        client_profile=client_profile,
        manifest=manifest,
    )
    artifact_payload: dict[str, Any] = {
        "export_schema_version": _POLICY_EXPORT_SCHEMA_VERSION,
        "policy_authority": "mud_server",
        "mirror_mode": "non_authoritative",
        "world_id": world_id,
        "client_profile": client_profile or None,
        "manifest_hash": normalized_manifest["manifest_hash"],
        "items_hash": normalized_manifest["items_hash"],
        "item_count": normalized_manifest["item_count"],
        "items": normalized_manifest["items"],
    }
    artifact_hash = str(compute_payload_hash(artifact_payload))
    artifact_payload["artifact_hash"] = artifact_hash

    artifact_path = _publish_artifact_path(
        world_id=world_id,
        client_profile=client_profile,
        manifest_hash=str(normalized_manifest["manifest_hash"]),
    )
    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(artifact_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        raise PolicyServiceError(
            status_code=500,
            code="POLICY_PUBLISH_ARTIFACT_WRITE_ERROR",
            detail=str(exc),
        ) from exc
    return {
        "artifact_hash": artifact_hash,
        "artifact_path": str(artifact_path),
    }


def _publish_artifact_path(*, world_id: str, client_profile: str, manifest_hash: str) -> Path:
    """Return filesystem path for one deterministic publish artifact."""
    world_root = _resolve_world_root_path(world_id)
    scope_segment = _scope_segment(client_profile)
    filename = f"publish_{manifest_hash}.json"
    return world_root / _POLICY_EXPORT_DIRNAME / scope_segment / filename


def _resolve_world_root_path(world_id: str) -> Path:
    """Resolve absolute world package root path for one world id."""
    worlds_root = Path(config.worlds.worlds_root)
    if not worlds_root.is_absolute():
        worlds_root = PROJECT_ROOT / worlds_root
    return worlds_root / world_id


def _scope_segment(client_profile: str) -> str:
    """Return sanitized path segment for client-profile scope names."""
    if not client_profile:
        return "world"
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", client_profile).strip("._")
    if not sanitized:
        sanitized = "client"
    return f"client_{sanitized}"
