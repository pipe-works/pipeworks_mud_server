"""Canonical condition-axis generation service.

This module centralizes all condition-axis generation behavior so API routes
and internal callsites can rely on one stable adapter contract.

Primary responsibilities:
- Validate seed and runtime input contracts.
- Resolve policy bundle metadata and reproducibility hashes.
- Call the configured upstream entity generator adapter.
- Normalize returned axis payloads into canonical ``axis -> score`` shape.
- Map all known failures into structured, stable service errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import randbelow
from typing import Any

import requests
import yaml
from pipeworks_ipc import compute_payload_hash

from mud_server.config import config
from mud_server.policies import PolicyManifestLoader

SEED_MIN = 1
SEED_MAX = 2_147_483_647
_SERVICE_STAGE = "axis_input"


class ConditionAxisServiceError(RuntimeError):
    """Typed service error carrying stable HTTP and contract metadata.

    Attributes:
        status_code: HTTP status to be surfaced by API route handlers.
        code: Stable machine-readable error code for UI/client mapping.
        detail: Human-readable summary of the failure.
        stage: Stable processing stage key for pipeline diagnostics.
    """

    def __init__(
        self, *, status_code: int, code: str, detail: str, stage: str = _SERVICE_STAGE
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.stage = stage

    def to_response_payload(self) -> dict[str, str]:
        """Return canonical error payload for API responses."""
        return {
            "detail": self.detail,
            "code": self.code,
            "stage": self.stage,
        }


@dataclass(slots=True, frozen=True)
class ConditionAxisPolicyContext:
    """Resolved policy metadata for one generation request.

    Attributes:
        bundle_id: Effective bundle id used for the generation request.
        bundle_version: Effective bundle version string.
        policy_hash: Deterministic hash of resolved policy inputs.
        required_runtime_inputs: Runtime keys required for strict validation.
    """

    bundle_id: str
    bundle_version: str
    policy_hash: str | None
    required_runtime_inputs: set[str]


@dataclass(slots=True, frozen=True)
class ConditionAxisProvenance:
    """Canonical provenance metadata returned to clients.

    Attributes:
        source: Canonical owner identifier for the response contract.
        served_via: API route path that served the response.
        generator: Upstream generator system identifier.
        generator_version: Upstream generator version/capability value.
        generated_at: ISO-8601 timestamp for generation completion.
    """

    source: str
    served_via: str
    generator: str
    generator_version: str
    generated_at: str


@dataclass(slots=True, frozen=True)
class ConditionAxisGenerationResult:
    """Service result payload for canonical condition-axis generation.

    Attributes:
        world_id: Target world id used for policy resolution.
        bundle_id: Effective bundle id used for generation.
        bundle_version: Effective bundle version string.
        policy_hash: Deterministic policy hash for reproducibility.
        seed: Deterministic generation seed.
        axes: Canonical axis map of ``axis_name -> score``.
        provenance: Canonical provenance block for diagnostics/auditability.
        entity_state: Raw upstream entity payload for internal reuse/callers.
    """

    world_id: str
    bundle_id: str
    bundle_version: str
    policy_hash: str | None
    seed: int
    axes: dict[str, float]
    provenance: ConditionAxisProvenance
    entity_state: dict[str, Any]


def generate_condition_axis(
    *,
    world_id: str,
    world_root: Path,
    seed: int | None = None,
    bundle_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    strict_inputs: bool = False,
) -> ConditionAxisGenerationResult:
    """Generate canonical condition-axis values for one world.

    Args:
        world_id: Canonical world identifier.
        world_root: Resolved world package root.
        seed: Optional deterministic generation seed.
        bundle_id: Optional bundle override requested by caller.
        inputs: Optional runtime input payload.
        strict_inputs: Enforce strict runtime input validation when ``True``.

    Returns:
        Canonical service result with normalized axes and provenance.

    Raises:
        ConditionAxisServiceError: If input validation, policy resolution, or
            upstream generation fails.
    """
    # Resolve seed first so all downstream logic receives a deterministic value.
    resolved_seed = _resolve_seed(seed)
    policy_context = _resolve_policy_context(
        world_id=world_id, world_root=world_root, bundle_id=bundle_id
    )

    if strict_inputs:
        _validate_runtime_inputs(
            inputs=inputs,
            required_runtime_inputs=policy_context.required_runtime_inputs,
        )

    # The upstream adapter remains the current standalone entity API topology.
    entity_state, response_headers = _fetch_entity_state_from_upstream(seed=resolved_seed)
    normalized_axes = _normalize_axes(entity_state)
    if not normalized_axes:
        raise ConditionAxisServiceError(
            status_code=502,
            code="CONDITION_AXIS_UPSTREAM_GENERATION_FAILED",
            detail="Failed to generate condition axis from upstream entity generator.",
        )

    generator_version = _extract_generator_version(entity_state, response_headers)
    generated_at = _extract_generated_at(entity_state)
    return ConditionAxisGenerationResult(
        world_id=world_id,
        bundle_id=policy_context.bundle_id,
        bundle_version=policy_context.bundle_version,
        policy_hash=policy_context.policy_hash,
        seed=resolved_seed,
        axes=normalized_axes,
        provenance=ConditionAxisProvenance(
            source="mud_server_canonical",
            served_via="/api/pipeline/condition-axis/generate",
            generator="entity_state_generation",
            generator_version=generator_version,
            generated_at=generated_at,
        ),
        entity_state=entity_state,
    )


def _resolve_seed(seed: int | None) -> int:
    """Resolve and validate deterministic seed bounds.

    Args:
        seed: Optional requested seed value.

    Returns:
        Validated seed in canonical bounds.

    Raises:
        ConditionAxisServiceError: If seed is non-integer or out of bounds.
    """
    resolved = _generate_seed() if seed is None else seed
    if not isinstance(resolved, int):
        raise ConditionAxisServiceError(
            status_code=422,
            code="CONDITION_AXIS_VALIDATION_ERROR",
            detail="Invalid request payload for condition-axis generation.",
        )
    if resolved < SEED_MIN or resolved > SEED_MAX:
        raise ConditionAxisServiceError(
            status_code=422,
            code="CONDITION_AXIS_VALIDATION_ERROR",
            detail=(
                "Invalid request payload for condition-axis generation. "
                f"seed must be between {SEED_MIN} and {SEED_MAX}."
            ),
        )
    return resolved


def _generate_seed() -> int:
    """Return a replayable non-zero seed.

    Returns:
        Integer seed in range ``1..SEED_MAX``.
    """
    return randbelow(SEED_MAX) + 1


def _resolve_policy_context(
    *,
    world_id: str,
    world_root: Path,
    bundle_id: str | None,
) -> ConditionAxisPolicyContext:
    """Resolve canonical bundle metadata and policy hash for one world.

    Resolution order:
    1. Manifest-first policy bundle resolution when ``manifest.yaml`` exists.
    2. Legacy flat policy files fallback for transition compatibility.

    Args:
        world_id: Canonical world identifier.
        world_root: On-disk world package root.
        bundle_id: Optional requested bundle override.

    Returns:
        Canonical policy context for service generation.

    Raises:
        ConditionAxisServiceError: If bundle selection is invalid or world
            policy configuration cannot support generation.
    """
    policy_root = world_root / "policies"
    manifest_path = policy_root / "manifest.yaml"
    default_bundle_id = f"{world_id}_default"

    if manifest_path.exists():
        loader = PolicyManifestLoader(worlds_root=world_root.parent)
        payload, report = loader.load_from_world_root(world_id=world_id, world_root=world_root)

        axes_payload = ((payload.get("axis") or {}).get("axes")) or {}
        thresholds_payload = ((payload.get("axis") or {}).get("thresholds")) or {}
        resolution_payload = ((payload.get("axis") or {}).get("resolution")) or {}
        manifest_payload = payload.get("manifest") or {}

        if isinstance(axes_payload, dict) and axes_payload:
            resolved_bundle_id = str(report.bundle_id or default_bundle_id)
            if bundle_id and bundle_id != resolved_bundle_id:
                raise ConditionAxisServiceError(
                    status_code=404,
                    code="CONDITION_AXIS_BUNDLE_NOT_FOUND",
                    detail=(
                        f"Requested bundle {bundle_id!r} is not available for world "
                        f"{world_id!r}."
                    ),
                )

            bundle_version = str(
                report.bundle_version
                or axes_payload.get("version")
                or thresholds_payload.get("version")
                or resolution_payload.get("version")
                or "1"
            )
            manifest_inputs = {
                str(item)
                for item in (report.required_runtime_inputs or [])
                if isinstance(item, str) and item.strip()
            }
            # The manifest input list is shared with other pipelines (for example
            # image compile) and may include keys not applicable to axis
            # generation. Keep condition-axis input requirements explicit.
            required_runtime_inputs = {
                key
                for key in manifest_inputs
                if key in {"entity.identity.gender", "entity.species"}
            }
            required_runtime_inputs.update({"entity.identity.gender", "entity.species"})

            policy_hash = compute_payload_hash(
                {
                    "manifest": manifest_payload,
                    "axis_bundle": {
                        "axes": axes_payload,
                        "thresholds": thresholds_payload,
                        "resolution": resolution_payload,
                    },
                }
            )

            return ConditionAxisPolicyContext(
                bundle_id=resolved_bundle_id,
                bundle_version=bundle_version,
                policy_hash=policy_hash,
                required_runtime_inputs=required_runtime_inputs,
            )

    axes_payload = _read_yaml(policy_root / "axes.yaml")
    thresholds_payload = _read_yaml(policy_root / "thresholds.yaml")
    resolution_payload = _read_yaml(policy_root / "resolution.yaml")

    if not axes_payload:
        raise ConditionAxisServiceError(
            status_code=501,
            code="CONDITION_AXIS_UPSTREAM_UNSUPPORTED",
            detail=(
                "Condition-axis generation is not available in the current upstream "
                "configuration."
            ),
        )

    resolved_bundle_id = bundle_id or default_bundle_id
    if bundle_id and bundle_id != default_bundle_id:
        raise ConditionAxisServiceError(
            status_code=404,
            code="CONDITION_AXIS_BUNDLE_NOT_FOUND",
            detail=f"Requested bundle {bundle_id!r} is not available for world {world_id!r}.",
        )

    bundle_version = str(
        axes_payload.get("version")
        or thresholds_payload.get("version")
        or resolution_payload.get("version")
        or "1"
    )
    policy_hash = compute_payload_hash(
        {
            "axes": axes_payload,
            "thresholds": thresholds_payload,
            "resolution": resolution_payload,
        }
    )
    return ConditionAxisPolicyContext(
        bundle_id=resolved_bundle_id,
        bundle_version=bundle_version,
        policy_hash=policy_hash,
        required_runtime_inputs={"entity.identity.gender", "entity.species"},
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML file as a dict, returning an empty payload on failure.

    Args:
        path: YAML file path to parse.

    Returns:
        Parsed mapping payload when successful; ``{}`` on missing/unreadable
        or non-mapping inputs.
    """
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _validate_runtime_inputs(
    *,
    inputs: dict[str, Any] | None,
    required_runtime_inputs: set[str],
) -> None:
    """Validate runtime input payload with strict schema and key checks.

    Args:
        inputs: Runtime inputs payload from API caller.
        required_runtime_inputs: Required runtime key set for this policy.

    Raises:
        ConditionAxisServiceError: If shape/keys/required values are invalid.
    """
    if not isinstance(inputs, dict):
        raise ConditionAxisServiceError(
            status_code=422,
            code="CONDITION_AXIS_VALIDATION_ERROR",
            detail="Invalid request payload for condition-axis generation.",
        )

    allowed_inputs = {"entity"}
    unknown_inputs = sorted(set(inputs.keys()) - allowed_inputs)
    if unknown_inputs:
        raise ConditionAxisServiceError(
            status_code=422,
            code="CONDITION_AXIS_VALIDATION_ERROR",
            detail=(
                "Invalid request payload for condition-axis generation. "
                f"Unknown keys: {', '.join(unknown_inputs)}."
            ),
        )

    entity = inputs.get("entity")
    if not isinstance(entity, dict):
        raise ConditionAxisServiceError(
            status_code=422,
            code="CONDITION_AXIS_VALIDATION_ERROR",
            detail="Invalid request payload for condition-axis generation.",
        )

    allowed_entity = {"identity", "species", "axes"}
    unknown_entity = sorted(set(entity.keys()) - allowed_entity)
    if unknown_entity:
        raise ConditionAxisServiceError(
            status_code=422,
            code="CONDITION_AXIS_VALIDATION_ERROR",
            detail=(
                "Invalid request payload for condition-axis generation. "
                f"Unknown entity keys: {', '.join(unknown_entity)}."
            ),
        )

    identity = entity.get("identity")
    if not isinstance(identity, dict):
        raise ConditionAxisServiceError(
            status_code=422,
            code="CONDITION_AXIS_VALIDATION_ERROR",
            detail="Invalid request payload for condition-axis generation.",
        )

    allowed_identity = {"gender"}
    unknown_identity = sorted(set(identity.keys()) - allowed_identity)
    if unknown_identity:
        raise ConditionAxisServiceError(
            status_code=422,
            code="CONDITION_AXIS_VALIDATION_ERROR",
            detail=(
                "Invalid request payload for condition-axis generation. "
                f"Unknown identity keys: {', '.join(unknown_identity)}."
            ),
        )

    missing_inputs: list[str] = []
    if "entity.species" in required_runtime_inputs:
        species = entity.get("species")
        if not isinstance(species, str) or not species.strip():
            missing_inputs.append("entity.species")
    if "entity.identity.gender" in required_runtime_inputs:
        gender = identity.get("gender")
        if not isinstance(gender, str) or not gender.strip():
            missing_inputs.append("entity.identity.gender")
    if "entity.axes" in required_runtime_inputs:
        axes = entity.get("axes")
        if not isinstance(axes, dict) or not axes:
            missing_inputs.append("entity.axes")

    if missing_inputs:
        raise ConditionAxisServiceError(
            status_code=422,
            code="CONDITION_AXIS_VALIDATION_ERROR",
            detail=(
                "Invalid request payload for condition-axis generation. "
                f"Missing required runtime inputs: {', '.join(sorted(missing_inputs))}."
            ),
        )


def _fetch_entity_state_from_upstream(seed: int) -> tuple[dict[str, Any], dict[str, str]]:
    """Fetch axis generation payload from configured upstream entity service.

    Args:
        seed: Deterministic seed used for upstream generation request.

    Returns:
        Tuple of ``(response_payload, response_headers)``.

    Raises:
        ConditionAxisServiceError: For unsupported integration, timeouts, HTTP
            failures, malformed JSON, or non-object payloads.
    """
    if not config.integrations.entity_state_enabled:
        raise ConditionAxisServiceError(
            status_code=501,
            code="CONDITION_AXIS_UPSTREAM_UNSUPPORTED",
            detail=(
                "Condition-axis generation is not available in the current upstream "
                "configuration."
            ),
        )

    base_url = config.integrations.entity_state_base_url.strip().rstrip("/")
    if not base_url:
        raise ConditionAxisServiceError(
            status_code=501,
            code="CONDITION_AXIS_UPSTREAM_UNSUPPORTED",
            detail=(
                "Condition-axis generation is not available in the current upstream "
                "configuration."
            ),
        )

    endpoint = f"{base_url}/api/entity"
    # Preserve current production adapter behavior until a dedicated upstream
    # axis-only endpoint is introduced.
    payload = {
        "seed": seed,
        "include_prompts": config.integrations.entity_state_include_prompts,
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=config.integrations.entity_state_timeout_seconds,
        )
    except requests.exceptions.Timeout as exc:
        raise ConditionAxisServiceError(
            status_code=504,
            code="CONDITION_AXIS_UPSTREAM_TIMEOUT",
            detail="Timed out waiting for upstream condition-axis generation.",
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise ConditionAxisServiceError(
            status_code=502,
            code="CONDITION_AXIS_UPSTREAM_GENERATION_FAILED",
            detail="Failed to generate condition axis from upstream entity generator.",
        ) from exc

    if response.status_code != 200:
        if response.status_code in {404, 405, 501}:
            raise ConditionAxisServiceError(
                status_code=501,
                code="CONDITION_AXIS_UPSTREAM_UNSUPPORTED",
                detail=(
                    "Condition-axis generation is not available in the current upstream "
                    "configuration."
                ),
            )
        if response.status_code in {408, 504}:
            raise ConditionAxisServiceError(
                status_code=504,
                code="CONDITION_AXIS_UPSTREAM_TIMEOUT",
                detail="Timed out waiting for upstream condition-axis generation.",
            )
        raise ConditionAxisServiceError(
            status_code=502,
            code="CONDITION_AXIS_UPSTREAM_GENERATION_FAILED",
            detail="Failed to generate condition axis from upstream entity generator.",
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise ConditionAxisServiceError(
            status_code=502,
            code="CONDITION_AXIS_UPSTREAM_GENERATION_FAILED",
            detail="Failed to generate condition axis from upstream entity generator.",
        ) from exc

    if not isinstance(body, dict):
        raise ConditionAxisServiceError(
            status_code=502,
            code="CONDITION_AXIS_UPSTREAM_GENERATION_FAILED",
            detail="Failed to generate condition axis from upstream entity generator.",
        )

    return body, dict(response.headers)


def _normalize_axes(payload: dict[str, Any]) -> dict[str, float]:
    """Normalize upstream axis payloads to ``axis_name -> score``.

    Supported source shapes:
    - ``payload["axes"][axis]["score"]``
    - ``payload["axes"][axis]`` as numeric scalar
    - ``payload["character"][axis]`` / ``payload["occupation"][axis]`` numeric

    Args:
        payload: Raw upstream generation payload.

    Returns:
        Sorted canonical axis map.
    """
    normalized: dict[str, float] = {}

    axes_payload = payload.get("axes")
    if isinstance(axes_payload, dict):
        for axis_name, axis_value in axes_payload.items():
            score = _extract_score(axis_value)
            if score is not None:
                normalized[str(axis_name)] = score

    for group_name in ("character", "occupation"):
        group_payload = payload.get(group_name)
        if not isinstance(group_payload, dict):
            continue
        for axis_name, axis_value in group_payload.items():
            score = _extract_score(axis_value)
            if score is not None and str(axis_name) not in normalized:
                normalized[str(axis_name)] = score

    return dict(sorted(normalized.items(), key=lambda item: item[0]))


def _extract_score(axis_value: Any) -> float | None:
    """Extract a numeric score from one axis value payload.

    Args:
        axis_value: Candidate value from one upstream axis entry.

    Returns:
        Float score when extractable, else ``None``.
    """
    if isinstance(axis_value, (int, float)):
        return float(axis_value)
    if isinstance(axis_value, dict):
        score = axis_value.get("score")
        if isinstance(score, (int, float)):
            return float(score)
    return None


def _extract_generator_version(
    payload: dict[str, Any],
    headers: dict[str, str],
) -> str:
    """Resolve upstream generator version from payload/headers.

    Args:
        payload: Parsed upstream JSON payload.
        headers: Upstream HTTP response headers.

    Returns:
        Best-available version string, falling back to ``"unknown"``.
    """
    for key in ("generator_version", "version"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for header in ("x-generator-version", "X-Generator-Version"):
        value = headers.get(header)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return "unknown"


def _extract_generated_at(payload: dict[str, Any]) -> str:
    """Resolve generation timestamp from payload or use current UTC timestamp.

    Args:
        payload: Parsed upstream JSON payload.

    Returns:
        ISO-8601 UTC timestamp string.
    """
    value = payload.get("generated_at")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
