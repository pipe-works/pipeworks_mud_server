"""Runtime-facing policy resolution helpers.

This module resolves effective policy payloads from canonical Layer 3
activation pointers only. It intentionally does not map legacy file paths.
"""

from __future__ import annotations

from typing import Any

from pipeworks_ipc import compute_payload_hash

from mud_server.db import policy_repo

from .activation import get_effective_policy_variant, resolve_effective_policy_activations
from .errors import PolicyServiceError
from .types import ActivationScope, EffectiveAxisBundle, EffectiveImagePolicyBundle
from .utils import ensure_world_exists, resolve_positive_int_version
from .validation import parse_policy_id


def resolve_effective_prompt_template(
    *,
    scope: ActivationScope,
    preferred_policy_id: str | None = None,
    preferred_template_path: str | None,
) -> dict[str, str]:
    """Resolve effective canonical ``prompt`` policy for one scope.

    ``preferred_template_path`` is accepted for backward signature
    compatibility only and is intentionally ignored now that legacy path-based
    selectors are removed.
    """
    ensure_world_exists(scope.world_id)

    _ = preferred_template_path

    selected_policy_id_hint: str | None = None
    if preferred_policy_id:
        identity = parse_policy_id(preferred_policy_id)
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
                    f"activation (policy_id={preferred_policy_id!r})."
                ),
            )
    elif len(prompt_rows) == 1:
        selected_activation = prompt_rows[0]
    else:
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_PROMPT_AMBIGUOUS",
            detail=(
                "Multiple effective prompt activations are present. Configure "
                "prompt_policy_id explicitly."
            ),
        )

    selected_policy_id = str(selected_activation["policy_id"])
    selected_variant = str(selected_activation["variant"])
    selected_policy = policy_repo.get_policy(policy_id=selected_policy_id, variant=selected_variant)
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


def _get_effective_manifest_payload(
    *, scope: ActivationScope
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Resolve and validate effective manifest payload for a scope.

    Returns:
        ``(manifest_payload, manifest_row, manifest_policy_id)``.

    Raises:
        PolicyServiceError: If activation is missing or manifest payload shape
            is invalid.
    """

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

    return manifest_payload, manifest_row, manifest_policy_id


def resolve_effective_axis_bundle(*, scope: ActivationScope) -> EffectiveAxisBundle:
    """Resolve canonical manifest+axis bundle payloads for runtime callers."""
    ensure_world_exists(scope.world_id)

    manifest_payload, manifest_row, manifest_policy_id = _get_effective_manifest_payload(
        scope=scope
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

    bundle_version_int = resolve_positive_int_version(
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


def _nested_get(payload: dict[str, Any], path_keys: list[str]) -> Any:
    """Return nested value from mapping path, or ``None`` if any key is missing."""

    current: Any = payload
    for key in path_keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _manifest_policy_id_hint(
    *,
    manifest_payload: dict[str, Any],
    image_node_key: str,
    policy_type: str,
    namespace: str,
) -> str | None:
    """Build preferred policy id from one manifest image node ``id``/``version``."""

    node = _nested_get(manifest_payload, ["image", image_node_key])
    if not isinstance(node, dict):
        return None

    raw_id = node.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        return None
    policy_key = raw_id.strip()

    version_value = node.get("version")
    if isinstance(version_value, int) and version_value >= 1:
        suffix = f"_v{version_value}"
        if policy_key.endswith(suffix):
            policy_key = policy_key[: -len(suffix)]

    return f"{policy_type}:{namespace}:{policy_key}"


def _select_effective_row(
    *,
    effective_rows: list[dict[str, Any]],
    scope: ActivationScope,
    policy_type: str,
    preferred_policy_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Select one effective activation row for a policy type.

    Returns:
        ``(selected_row, diagnostic_error)`` where ``diagnostic_error`` is a
        human-readable issue string for diagnostic surfaces.
    """

    candidates = [
        row for row in effective_rows if str(row.get("policy_id", "")).startswith(f"{policy_type}:")
    ]

    if preferred_policy_id:
        for row in candidates:
            if str(row.get("policy_id")) == preferred_policy_id:
                return row, None
        return (
            None,
            (
                f"missing effective {policy_type} activation for preferred policy_id "
                f"{preferred_policy_id!r} in scope "
                f"(world_id={scope.world_id!r}, client_profile={scope.client_profile!r})"
            ),
        )

    if not candidates:
        return (
            None,
            (
                f"missing effective {policy_type} activation in scope "
                f"(world_id={scope.world_id!r}, client_profile={scope.client_profile!r})"
            ),
        )

    if len(candidates) > 1:
        return (
            None,
            (
                f"ambiguous effective {policy_type} activation set in scope "
                f"(world_id={scope.world_id!r}, client_profile={scope.client_profile!r}); "
                f"found {len(candidates)}"
            ),
        )

    return candidates[0], None


def _resolve_effective_policy_payload(
    *,
    effective_rows: list[dict[str, Any]],
    scope: ActivationScope,
    policy_type: str,
    preferred_policy_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve one effective policy payload for diagnostic image-bundle reads."""

    selected_row, error = _select_effective_row(
        effective_rows=effective_rows,
        scope=scope,
        policy_type=policy_type,
        preferred_policy_id=preferred_policy_id,
    )
    if selected_row is None:
        return None, error

    policy_id = str(selected_row.get("policy_id") or "")
    variant = str(selected_row.get("variant") or "")
    row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
    if row is None:
        return (
            None,
            ("effective activation points to missing policy variant: " f"{policy_id}:{variant}"),
        )

    content = row.get("content")
    if not isinstance(content, dict):
        return None, f"policy content is not an object: {policy_id}:{variant}"

    return content, None


def resolve_effective_image_policy_bundle(*, scope: ActivationScope) -> EffectiveImagePolicyBundle:
    """Resolve image-policy diagnostic bundle from canonical DB activations.

    This keeps the existing route response shape while changing the source of
    truth from filesystem manifest parsing to canonical DB policy rows.
    """

    ensure_world_exists(scope.world_id)

    manifest_payload, _manifest_row, _manifest_policy_id = _get_effective_manifest_payload(
        scope=scope
    )

    composition_order = _nested_get(manifest_payload, ["image", "composition", "order"])
    required_inputs = _nested_get(
        manifest_payload, ["image", "composition", "required_runtime_inputs"]
    )

    missing_components: list[str] = []

    if not isinstance(composition_order, list):
        missing_components.append("manifest field missing/invalid: image.composition.order")
        composition_order = []
    if not isinstance(required_inputs, list):
        missing_components.append(
            "manifest field missing/invalid: image.composition.required_runtime_inputs"
        )
        required_inputs = []

    effective_rows = resolve_effective_policy_activations(scope=scope)

    descriptor_policy_hint = _manifest_policy_id_hint(
        manifest_payload=manifest_payload,
        image_node_key="descriptor_layer",
        policy_type="descriptor_layer",
        namespace="image.descriptors",
    )
    tone_policy_hint = _manifest_policy_id_hint(
        manifest_payload=manifest_payload,
        image_node_key="tone_profile",
        policy_type="tone_profile",
        namespace="image.tone_profiles",
    )

    descriptor_payload, descriptor_error = _resolve_effective_policy_payload(
        effective_rows=effective_rows,
        scope=scope,
        policy_type="descriptor_layer",
        preferred_policy_id=descriptor_policy_hint,
    )
    if descriptor_error:
        missing_components.append(f"descriptor_layer: {descriptor_error}")

    tone_payload, tone_error = _resolve_effective_policy_payload(
        effective_rows=effective_rows,
        scope=scope,
        policy_type="tone_profile",
        preferred_policy_id=tone_policy_hint,
    )
    if tone_error:
        missing_components.append(f"tone_profile: {tone_error}")

    species_registry_payload, species_error = _resolve_effective_policy_payload(
        effective_rows=effective_rows,
        scope=scope,
        policy_type="registry",
        preferred_policy_id="registry:image.registries:species_registry",
    )
    if species_error:
        missing_components.append(f"species_registry: {species_error}")

    clothing_registry_payload, clothing_error = _resolve_effective_policy_payload(
        effective_rows=effective_rows,
        scope=scope,
        policy_type="registry",
        preferred_policy_id="registry:image.registries:clothing_registry",
    )
    if clothing_error:
        missing_components.append(f"clothing_registry: {clothing_error}")

    axis_payload: dict[str, Any] = {}
    try:
        resolved_axis = resolve_effective_axis_bundle(scope=scope)
        axis_payload = {
            "axes": resolved_axis.axes_payload,
            "thresholds": resolved_axis.thresholds_payload,
            "resolution": resolved_axis.resolution_payload,
        }
    except PolicyServiceError as error:
        missing_components.append(f"axis_bundle: {error.detail}")

    policy_hash = str(
        compute_payload_hash(
            {
                "manifest": manifest_payload,
                "axis_bundle": axis_payload,
                "descriptor_layer_payload": descriptor_payload,
                "tone_profile_payload": tone_payload,
                "species_registry_payload": species_registry_payload,
                "clothing_registry_payload": clothing_registry_payload,
                "composition_order": [str(value) for value in composition_order],
                "required_runtime_inputs": [str(value) for value in required_inputs],
                "missing_components": list(missing_components),
            }
        )
    )

    return EffectiveImagePolicyBundle(
        world_id=scope.world_id,
        policy_schema=(
            str(manifest_payload.get("policy_schema"))
            if manifest_payload.get("policy_schema") is not None
            else None
        ),
        policy_bundle_id=(
            str(_nested_get(manifest_payload, ["policy_bundle", "id"]))
            if _nested_get(manifest_payload, ["policy_bundle", "id"]) is not None
            else None
        ),
        policy_bundle_version=_nested_get(manifest_payload, ["policy_bundle", "version"]),
        policy_hash=policy_hash,
        composition_order=[str(value) for value in composition_order],
        required_runtime_inputs=[str(value) for value in required_inputs],
        descriptor_layer_path=(
            str(_nested_get(manifest_payload, ["image", "descriptor_layer", "path"]))
            if _nested_get(manifest_payload, ["image", "descriptor_layer", "path"]) is not None
            else None
        ),
        tone_profile_path=(
            str(_nested_get(manifest_payload, ["image", "tone_profile", "path"]))
            if _nested_get(manifest_payload, ["image", "tone_profile", "path"]) is not None
            else None
        ),
        species_registry_path=(
            str(_nested_get(manifest_payload, ["image", "registries", "species"]))
            if _nested_get(manifest_payload, ["image", "registries", "species"]) is not None
            else None
        ),
        clothing_registry_path=(
            str(_nested_get(manifest_payload, ["image", "registries", "clothing"]))
            if _nested_get(manifest_payload, ["image", "registries", "clothing"]) is not None
            else None
        ),
        missing_components=missing_components,
    )
