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
from .types import ActivationScope, EffectiveAxisBundle
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


def resolve_effective_axis_bundle(*, scope: ActivationScope) -> EffectiveAxisBundle:
    """Resolve canonical manifest+axis bundle payloads for runtime callers."""
    ensure_world_exists(scope.world_id)

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
