"""Lab endpoints for the Axis Descriptor Lab research tool.

These endpoints expose the world's OOC→IC translation pipeline directly via
a JSON API, bypassing the game engine's character DB lookup.  They are
intended exclusively for use by the Axis Descriptor Lab — a single-user
research tool for testing IC prompt behaviour against deterministic axis
payloads.

Auth
----
Session-based — same mechanism as all other server endpoints.  Admin or
superuser role is required.  The lab logs in interactively via its UI; no
credentials are stored anywhere on disk.

Endpoints
---------
GET  /api/lab/worlds
    List all active worlds with a flag indicating whether the translation
    layer is enabled.  Used to populate the lab's world-selector dropdown.

GET  /api/lab/world-config/{world_id}
    Return the translation layer configuration for a specific world (model,
    active_axes, strict_mode, etc.).  Used by the lab UI to reflect what the
    server will actually apply to a translation request.

GET  /api/lab/world-prompts/{world_id}
    Return the canonical prompt template files from the world's ``policies/``
    directory.

GET  /api/lab/world-prompts/{world_id}/drafts
    List saved prompt draft files under the world's ``policies/drafts``
    directory.

GET  /api/lab/world-prompts/{world_id}/drafts/{name}
    Load one saved prompt draft for Artifact Editor inspection.

POST /api/lab/world-prompts/{world_id}/drafts
    Create a new prompt draft under the world's ``policies/drafts``
    directory without overwriting any canonical files.

POST /api/lab/world-prompts/{world_id}/drafts/{name}/promote
    Promote one draft into a new canonical ``policies/<name>.txt`` file and
    make it the active prompt_template_path without overwriting any existing
    canonical files.

GET  /api/lab/world-policy-bundle/{world_id}
    Return the canonical world policy package normalised into one JSON bundle
    for Artifact Editor inspection.

GET  /api/lab/world-image-policy-bundle/{world_id}
    Return the manifest-resolved image policy bundle (composition order,
    runtime input requirements, and image policy asset references).

POST /api/lab/compile-image-prompt
    Compile a deterministic image prompt from manifest-resolved policy assets
    and runtime inputs (species, gender, axes, optional context signals).

GET  /api/lab/world-policy-bundle/{world_id}/drafts
    List saved JSON draft bundles under the world's ``policies/drafts``
    directory.

GET  /api/lab/world-policy-bundle/{world_id}/drafts/{name}
    Load one saved JSON draft bundle for Artifact Editor inspection.

POST /api/lab/world-policy-bundle/{world_id}/drafts
    Create a new draft JSON bundle under the world's ``policies/drafts``
    directory without overwriting any canonical files.

POST /api/lab/world-policy-bundle/{world_id}/drafts/{name}/promote
    Promote one draft into the canonical ``policies/axes.yaml``,
    ``policies/thresholds.yaml``, and ``policies/resolution.yaml`` files and
    reload the world's axis engine explicitly.

POST /api/lab/translate
    Translate an OOC message to IC dialogue using the world's canonical
    pipeline.  Accepts raw axis values — no character DB lookup is
    performed.  Returns the IC text, outcome status, the server-formatted
    profile_summary, and the fully-rendered system prompt sent to Ollama.

Legacy file-backed prompt/policy routes
---------------------------------------
Prompt and policy-bundle file authoring/listing routes are disabled by
default and return ``410`` unless explicitly enabled via
``MUD_LAB_ENABLE_LEGACY_FILE_AUTHORING=1``. This keeps canonical DB policy
authoring on ``/api/policies`` as the default operator workflow.
"""

from __future__ import annotations

import logging
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pipeworks_ipc import compute_payload_hash

from mud_server.api.models import (
    LabImageCompileRequest,
    LabImageCompileResponse,
    LabImagePolicyBundleResponse,
    LabPolicyAxisDefinition,
    LabPolicyBundleDraftCreateRequest,
    LabPolicyBundleDraftCreateResponse,
    LabPolicyBundleDraftDocument,
    LabPolicyBundleDraftListResponse,
    LabPolicyBundleDraftPayload,
    LabPolicyBundleDraftPromoteRequest,
    LabPolicyBundleDraftPromoteResponse,
    LabPolicyBundleResponse,
    LabPolicyChatAxisRule,
    LabPolicyThresholdBand,
    LabPromptDraftCreateRequest,
    LabPromptDraftCreateResponse,
    LabPromptDraftDocument,
    LabPromptDraftListResponse,
    LabPromptDraftPromoteRequest,
    LabPromptDraftPromoteResponse,
    LabTranslateRequest,
    LabTranslateResponse,
    LabWorldConfig,
    LabWorldPromptsResponse,
    LabWorldsResponse,
    LabWorldSummary,
)
from mud_server.api.routes.lab_policy_support import (
    create_world_policy_bundle_draft as create_world_policy_bundle_draft_document,
)
from mud_server.api.routes.lab_policy_support import (
    get_world_policy_bundle_draft as get_world_policy_bundle_draft_document,
)
from mud_server.api.routes.lab_policy_support import (
    list_world_policy_bundle_drafts as list_world_policy_bundle_drafts_document,
)
from mud_server.api.routes.lab_policy_support import (
    promote_world_policy_bundle_draft as promote_world_policy_bundle_draft_document,
)
from mud_server.api.routes.lab_prompt_support import (
    create_world_prompt_draft as create_world_prompt_draft_document,
)
from mud_server.api.routes.lab_prompt_support import (
    get_world_prompt_draft as get_world_prompt_draft_document,
)
from mud_server.api.routes.lab_prompt_support import (
    list_world_prompt_drafts as list_world_prompt_drafts_document,
)
from mud_server.api.routes.lab_prompt_support import (
    list_world_prompts as list_world_prompts_document,
)
from mud_server.api.routes.lab_prompt_support import (
    promote_world_prompt_draft as promote_world_prompt_draft_document,
)
from mud_server.api.routes.lab_support import (
    build_lab_world_config,
    get_lab_world,
    require_lab_session,
    require_translation_world,
    require_world_root,
)
from mud_server.core.engine import GameEngine
from mud_server.policies import PolicyManifestLoader

logger = logging.getLogger(__name__)

_LEGACY_LAB_FILE_AUTHORING_ENV = "MUD_LAB_ENABLE_LEGACY_FILE_AUTHORING"


def _legacy_lab_file_authoring_enabled() -> bool:
    """Return whether legacy file-backed lab authoring routes are enabled."""
    raw_value = os.getenv(_LEGACY_LAB_FILE_AUTHORING_ENV, "").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _require_legacy_lab_file_authoring_enabled() -> None:
    """Reject legacy file-backed lab endpoints unless explicitly enabled."""
    if _legacy_lab_file_authoring_enabled():
        return
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy file-backed lab policy routes are disabled. "
            "Use canonical policy APIs under /api/policies and /api/policy-activations. "
            f"Set {_LEGACY_LAB_FILE_AUTHORING_ENV}=1 only for transitional migration/debug flows."
        ),
    )


def _read_yaml(path: Path) -> dict:
    """Read one YAML file from a world policy package.

    Missing files return an empty dict so the route can surface consistent
    contract errors rather than failing with an unhandled file exception.
    """

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _hash_policy_payload(axes_payload: dict, thresholds_payload: dict) -> str:
    """Compute the canonical policy hash for the normalized bundle."""

    serialized = yaml.safe_dump(
        {"axes": axes_payload, "thresholds": thresholds_payload},
        sort_keys=True,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _write_yaml(path: Path, payload: dict) -> None:
    """Persist one YAML payload using a deterministic block-map style."""

    serialized = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    path.write_text(serialized, encoding="utf-8")


def _build_policy_bundle(world_id: str, world_root: Path) -> LabPolicyBundleResponse:
    """Normalize a world's policy package into the lab-facing JSON bundle shape."""
    axes_payload, thresholds_payload, resolution_payload, source_files = (
        _load_world_axis_policy_files(world_id, world_root)
    )

    axes_raw = axes_payload.get("axes") or {}
    thresholds_raw = (
        (thresholds_payload.get("axes") or {}) if isinstance(thresholds_payload, dict) else {}
    )
    chat_raw = (
        ((resolution_payload.get("interactions") or {}).get("chat") or {})
        if isinstance(resolution_payload, dict)
        else {}
    )
    chat_axes_raw = chat_raw.get("axes") or {}

    axes_order = list(axes_raw.keys())
    if not axes_order:
        raise HTTPException(
            status_code=404,
            detail=f"Axis policy files unavailable for world {world_id!r}.",
        )

    normalized_axes: dict[str, dict] = {}
    for axis_name, axis_meta in axes_raw.items():
        ordering_values = (((axis_meta or {}).get("ordering") or {}).get("values")) or []
        threshold_values = ((thresholds_raw.get(axis_name) or {}).get("values")) or {}
        normalized_axes[axis_name] = {
            "group": (axis_meta or {}).get("group", "character"),
            "ordering": list(ordering_values),
            "thresholds": [
                {
                    "label": label,
                    "min": ranges.get("min"),
                    "max": ranges.get("max"),
                }
                for label, ranges in threshold_values.items()
            ],
        }

    normalized_chat_rules = {
        "channel_multipliers": dict(chat_raw.get("channel_multipliers") or {}),
        "min_gap_threshold": chat_raw.get("min_gap_threshold"),
        "axes": {
            axis_name: {
                key: value
                for key, value in (chat_axes_raw.get(axis_name) or {}).items()
                if key in {"resolver", "base_magnitude"}
            }
            for axis_name in axes_order
        },
    }

    return LabPolicyBundleResponse(
        world_id=world_id,
        version=str(
            axes_payload.get("version")
            or thresholds_payload.get("version")
            or resolution_payload.get("version")
            or ""
        ),
        source="mud_server policy package normalized to JSON",
        policy_hash=_hash_policy_payload(axes_payload, thresholds_payload),
        source_files=source_files,
        axes_order=axes_order,
        axes=normalized_axes,
        chat_rules=normalized_chat_rules,
    )


def _load_world_axis_policy_files(
    world_id: str, world_root: Path
) -> tuple[dict, dict, dict, list[str]]:
    """Load axis policy files with manifest-first resolution and flat fallback.

    Resolution order:
    1. If ``policies/manifest.yaml`` exists and includes valid axis bundle paths,
       load axis/thresholds/resolution from referenced files.
    2. Otherwise fall back to legacy flat files under ``policies/``.

    This helper keeps existing lab behavior working during migration.
    """

    policy_root = world_root / "policies"
    manifest_path = policy_root / "manifest.yaml"

    if manifest_path.exists():
        manifest_loader = PolicyManifestLoader(worlds_root=world_root.parent)
        payload, report = manifest_loader.load_from_world_root(
            world_id=world_id, world_root=world_root
        )

        axes_payload = ((payload.get("axis") or {}).get("axes")) or {}
        thresholds_payload = ((payload.get("axis") or {}).get("thresholds")) or {}
        resolution_payload = ((payload.get("axis") or {}).get("resolution")) or {}

        if (
            isinstance(axes_payload, dict)
            and isinstance(thresholds_payload, dict)
            and isinstance(resolution_payload, dict)
            and axes_payload
        ):
            source_files = [
                report.referenced_paths.get("axis.axes", "policies/axis/axes.yaml"),
                report.referenced_paths.get("axis.thresholds", "policies/axis/thresholds.yaml"),
                report.referenced_paths.get("axis.resolution", "policies/axis/resolution.yaml"),
            ]
            return axes_payload, thresholds_payload, resolution_payload, source_files

        # TODO(refactor-cleanup): remove after manifest migration complete.
        # Fall back to legacy flat files when manifest exists but axis assets
        # are incomplete or invalid during the transition period.
        logger.warning(
            "World %r manifest axis assets incomplete, falling back to legacy policy files: %s",
            world_id,
            ", ".join(report.missing_components),
        )

    return (
        _read_yaml(policy_root / "axes.yaml"),
        _read_yaml(policy_root / "thresholds.yaml"),
        _read_yaml(policy_root / "resolution.yaml"),
        ["policies/axes.yaml", "policies/thresholds.yaml", "policies/resolution.yaml"],
    )


def _canonical_policy_source_files() -> list[str]:
    """Return the stable canonical file set for world policy bundles."""

    return [
        "policies/axes.yaml",
        "policies/thresholds.yaml",
        "policies/resolution.yaml",
    ]


def _build_image_policy_bundle(world_id: str, world_root: Path) -> LabImagePolicyBundleResponse:
    """Build one manifest-resolved image policy bundle response.

    This helper returns a diagnostic contract snapshot for integration clients.
    It does not perform prompt compilation; it only reports resolved references
    and manifest validation state.
    """

    manifest_path = world_root / "policies" / "manifest.yaml"
    if not manifest_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Image policy files unavailable for world {world_id!r}.",
        )

    loader = PolicyManifestLoader(worlds_root=world_root.parent)
    payload, report = loader.load_from_world_root(world_id=world_id, world_root=world_root)

    # Hash compiler inputs resolved from manifest references only. Runtime
    # entity inputs (for example gender/species/axes values) are intentionally
    # excluded so this hash remains stable for a fixed policy package.
    bundle_policy_hash = compute_payload_hash(
        {
            "manifest": payload.get("manifest") or {},
            "axis_bundle": payload.get("axis") or {},
            "descriptor_layer_text": (payload.get("image") or {}).get("descriptor_layer"),
            "tone_profile_payload": (payload.get("image") or {}).get("tone_profile"),
            "species_registry_payload": (payload.get("image") or {}).get("species_registry"),
            "clothing_registry_payload": (payload.get("image") or {}).get("clothing_registry"),
            "composition_order": (payload.get("image") or {}).get("composition_order") or [],
            "required_runtime_inputs": (payload.get("image") or {}).get("required_runtime_inputs")
            or [],
        }
    )

    image_payload = payload.get("image") or {}
    return LabImagePolicyBundleResponse(
        world_id=world_id,
        policy_schema=report.policy_schema,
        policy_bundle_id=report.bundle_id,
        policy_bundle_version=report.bundle_version,
        policy_hash=bundle_policy_hash,
        composition_order=list(image_payload.get("composition_order") or []),
        required_runtime_inputs=list(image_payload.get("required_runtime_inputs") or []),
        descriptor_layer_path=report.referenced_paths.get("image.descriptor_layer"),
        tone_profile_path=report.referenced_paths.get("image.tone_profile"),
        species_registry_path=report.referenced_paths.get("image.species_registry"),
        clothing_registry_path=report.referenced_paths.get("image.clothing_registry"),
        missing_components=list(report.missing_components),
    )


def _compile_image_prompt(
    req: LabImageCompileRequest, *, world_root: Path
) -> LabImageCompileResponse:
    """Compile one deterministic image prompt from manifest-resolved policy assets.

    The compiler is intentionally policy-driven and deterministic:

    1. Load manifest + referenced assets via ``PolicyManifestLoader``.
    2. Select species/clothing blocks using registry rules + runtime inputs.
    3. Assemble the prompt in manifest-defined composition order.
    4. Return selection metadata and deterministic provenance hashes.

    Raises:
        HTTPException: When required manifest assets are missing or selection
            cannot produce required blocks.
    """

    loader = PolicyManifestLoader(worlds_root=world_root.parent)
    payload, report = loader.load_from_world_root(world_id=req.world_id, world_root=world_root)

    if report.missing_components:
        raise HTTPException(
            status_code=409,
            detail=(
                "Image policy manifest is incomplete for compile: "
                + "; ".join(report.missing_components)
            ),
        )

    manifest_payload = payload.get("manifest") or {}
    image_payload = payload.get("image") or {}
    composition_order = list(image_payload.get("composition_order") or [])
    required_runtime_inputs = list(image_payload.get("required_runtime_inputs") or [])
    descriptor_layer_text = image_payload.get("descriptor_layer")
    tone_profile_payload = image_payload.get("tone_profile")
    species_registry = image_payload.get("species_registry")
    clothing_registry = image_payload.get("clothing_registry")

    if not isinstance(descriptor_layer_text, str):
        raise HTTPException(
            status_code=409, detail="Descriptor layer text missing in policy bundle."
        )
    if not isinstance(tone_profile_payload, dict):
        raise HTTPException(
            status_code=409, detail="Tone profile payload missing in policy bundle."
        )
    if not isinstance(species_registry, dict):
        raise HTTPException(
            status_code=409, detail="Species registry payload missing in policy bundle."
        )
    if not isinstance(clothing_registry, dict):
        raise HTTPException(
            status_code=409, detail="Clothing registry payload missing in policy bundle."
        )

    axis_labels = {axis_name: axis_value.label for axis_name, axis_value in req.axes.items()}
    _validate_compile_runtime_inputs(
        required_runtime_inputs=required_runtime_inputs,
        species=req.species,
        gender=req.gender,
        axes=req.axes,
    )
    selected_species_entry = _select_species_entry(
        species_registry=species_registry,
        species=req.species,
        gender=req.gender,
    )
    if selected_species_entry is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No active species block matched species={req.species!r} and "
                f"gender={req.gender!r}."
            ),
        )

    species_block_text = _read_registry_block_text(
        world_root=world_root,
        rel_path=str(selected_species_entry.get("block_path") or ""),
    )

    selected_clothing_profile_id = _extract_clothing_profile_id(clothing_registry)
    selected_clothing_slots, clothing_blocks = _select_clothing_blocks(
        clothing_registry=clothing_registry,
        world_root=world_root,
        gender=req.gender,
        axis_labels=axis_labels,
        world_context=req.world_context,
        occupation_signals=req.occupation_signals,
    )

    tone_block_text = _render_tone_profile_block(tone_profile_payload)
    compiled_prompt = _assemble_compiled_prompt(
        composition_order=composition_order,
        species_block_text=species_block_text,
        descriptor_layer_text=descriptor_layer_text,
        clothing_block_text="\n".join(clothing_blocks).strip(),
        tone_block_text=tone_block_text,
    )

    # Hash policy/compiler inputs only (no runtime axis/gender in policy hash).
    policy_hash = compute_payload_hash(
        {
            "manifest": manifest_payload,
            "axis_bundle": payload.get("axis") or {},
            "descriptor_layer_text": descriptor_layer_text,
            "tone_profile_payload": tone_profile_payload,
            "composition_order": composition_order,
            "selected_blocks": {
                "species": {
                    "id": selected_species_entry.get("id"),
                    "content": species_block_text,
                },
                "clothing_profile_id": selected_clothing_profile_id,
                "clothing_slots": selected_clothing_slots,
                "clothing_block_texts": clothing_blocks,
            },
        }
    )
    axis_hash = compute_payload_hash(
        {
            axis_name: {"label": axis_value.label, "score": axis_value.score}
            for axis_name, axis_value in sorted(req.axes.items(), key=lambda item: item[0])
        }
    )

    descriptor_id = _nested_get(manifest_payload, ["image", "descriptor_layer", "id"])
    tone_id = _nested_get(manifest_payload, ["image", "tone_profile", "id"])

    return LabImageCompileResponse(
        world_id=req.world_id,
        policy_schema=report.policy_schema,
        policy_bundle_id=report.bundle_id,
        policy_bundle_version=report.bundle_version,
        policy_hash=policy_hash,
        axis_hash=axis_hash,
        required_runtime_inputs=required_runtime_inputs,
        selected_descriptor_layer_id=str(descriptor_id) if descriptor_id is not None else None,
        selected_tone_profile_id=str(tone_id) if tone_id is not None else None,
        selected_species_block_id=str(selected_species_entry.get("id") or ""),
        selected_clothing_profile_id=selected_clothing_profile_id,
        selected_clothing_slot_ids=selected_clothing_slots,
        compiled_prompt=compiled_prompt,
        generation_defaults={
            "model_id": req.model_id or "flux-2-klein-4b",
            "aspect_ratio": req.aspect_ratio or "1:1",
            "seed": req.seed,
        },
        missing_components=[],
    )


def _validate_compile_runtime_inputs(
    *,
    required_runtime_inputs: list[str],
    species: str,
    gender: str,
    axes: dict[str, Any],
) -> None:
    """Validate required runtime inputs declared by manifest composition contract."""
    missing: list[str] = []
    required = set(required_runtime_inputs)

    if "entity.species" in required and not str(species).strip():
        missing.append("entity.species")
    if "entity.identity.gender" in required and not str(gender).strip():
        missing.append("entity.identity.gender")
    if "entity.axes" in required and not axes:
        missing.append("entity.axes")

    if missing:
        raise HTTPException(
            status_code=409,
            detail=("Missing required runtime inputs for compile: " + ", ".join(sorted(missing))),
        )


def _select_species_entry(
    *, species_registry: dict[str, Any], species: str, gender: str
) -> dict[str, Any] | None:
    """Select one active species registry entry deterministically."""
    entries = species_registry.get("entries") or []
    if not isinstance(entries, list):
        return None

    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status", "")).lower() != "active":
            continue
        if str(entry.get("block_type", "")) != "species":
            continue
        if not _matches_species(entry, species):
            continue
        if not _matches_gender(entry, gender):
            continue
        if not _matches_species_rule(entry, species):
            continue
        candidates.append(entry)

    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            -int(item.get("render_priority", 0)),
            str(item.get("id", "")),
        ),
    )[0]


def _select_clothing_blocks(
    *,
    clothing_registry: dict[str, Any],
    world_root: Path,
    gender: str,
    axis_labels: dict[str, str],
    world_context: list[str],
    occupation_signals: list[str],
) -> tuple[dict[str, str | None], list[str]]:
    """Select one clothing block per slot and return ids + block texts."""
    slots = clothing_registry.get("slots") or {}
    if not isinstance(slots, dict):
        return {}, []

    selected_slot_ids: dict[str, str | None] = {}
    selected_block_texts: list[str] = []

    for slot_name in clothing_registry.get("composition_contract", {}).get("slots", []):
        slot_entries = slots.get(slot_name) or []
        selected = _select_clothing_slot_entry(
            slot_entries=slot_entries,
            slot_name=str(slot_name),
            gender=gender,
            axis_labels=axis_labels,
            world_context=world_context,
            occupation_signals=occupation_signals,
        )
        if selected is None:
            selected_slot_ids[str(slot_name)] = None
            continue

        selected_slot_ids[str(slot_name)] = str(selected.get("id") or "")
        rel_path = str(selected.get("fragment_path") or "")
        if rel_path:
            selected_block_texts.append(
                _read_registry_block_text(world_root=world_root, rel_path=rel_path)
            )

    return selected_slot_ids, selected_block_texts


def _select_clothing_slot_entry(
    *,
    slot_entries: Any,
    slot_name: str,
    gender: str,
    axis_labels: dict[str, str],
    world_context: list[str],
    occupation_signals: list[str],
) -> dict[str, Any] | None:
    """Select one clothing entry for a slot using deterministic match ordering."""
    if not isinstance(slot_entries, list):
        return None

    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for entry in slot_entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status", "")).lower() != "active":
            continue
        if str(entry.get("block_type", "")) != "clothing_fragment":
            continue
        if not _matches_gender(entry, gender):
            continue

        matched, fallback = _matches_clothing_rules(
            entry=entry,
            slot_name=slot_name,
            axis_labels=axis_labels,
            world_context=world_context,
            occupation_signals=occupation_signals,
        )
        if not matched:
            continue

        match_score = 0 if fallback else 1
        candidates.append(
            (
                -match_score,
                -int(entry.get("render_priority", 0)),
                str(entry.get("id", "")),
                entry,
            )
        )

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def _matches_clothing_rules(
    *,
    entry: dict[str, Any],
    slot_name: str,
    axis_labels: dict[str, str],
    world_context: list[str],
    occupation_signals: list[str],
) -> tuple[bool, bool]:
    """Evaluate clothing entry rules and return ``(matched, fallback_match)``."""
    rules = ((entry.get("selection_rules") or {}).get("when")) or {}
    if not isinstance(rules, dict):
        return True, False

    fallback = bool(rules.get("fallback", False))
    axis_rule_any = _nested_get(rules, ["axis_labels", "wealth_any"])
    if axis_rule_any is not None:
        axis_label = axis_labels.get("wealth")
        if axis_label not in set(axis_rule_any if isinstance(axis_rule_any, list) else []):
            return False, fallback

    world_any = rules.get("world_context_any")
    if world_any is not None:
        world_set = set(world_context)
        if not world_set.intersection(set(world_any if isinstance(world_any, list) else [])):
            return False, fallback

    occupation_any = rules.get("occupation_signal_any")
    if occupation_any is not None:
        occupation_set = set(occupation_signals)
        if not occupation_set.intersection(
            set(occupation_any if isinstance(occupation_any, list) else [])
        ):
            return False, fallback

    _ = slot_name  # Explicitly unused in v0; retained for future per-slot rule logic.
    return True, fallback


def _extract_clothing_profile_id(clothing_registry: dict[str, Any]) -> str | None:
    """Extract default clothing profile id from registry payload."""
    defaults = clothing_registry.get("defaults") or {}
    profile_id = defaults.get("profile_id")
    return str(profile_id) if isinstance(profile_id, str) else None


def _assemble_compiled_prompt(
    *,
    composition_order: list[str],
    species_block_text: str,
    descriptor_layer_text: str,
    clothing_block_text: str,
    tone_block_text: str,
) -> str:
    """Assemble final prompt in strict composition order."""
    block_map = {
        "species_canon_block": species_block_text.strip(),
        "descriptor_layer_output": descriptor_layer_text.strip(),
        "clothing_block": clothing_block_text.strip(),
        "tone_profile_block": tone_block_text.strip(),
    }
    blocks = [block_map.get(block_name, "") for block_name in composition_order]
    return "\n\n".join([block for block in blocks if block])


def _render_tone_profile_block(tone_profile_payload: dict[str, Any]) -> str:
    """Render a tone-profile block from JSON payload.

    The v0 implementation prefers ``prompt_block`` when present. Otherwise it
    composes one conservative sentence from a subset of known tone fields.
    """
    prompt_block = tone_profile_payload.get("prompt_block")
    if isinstance(prompt_block, str) and prompt_block.strip():
        return prompt_block

    linework = str(tone_profile_payload.get("linework_style") or "").strip()
    palette = str(tone_profile_payload.get("palette_descriptor") or "").strip()
    context = str(tone_profile_payload.get("presentation_context") or "").strip()
    phrases = [phrase for phrase in [linework, palette, context] if phrase]
    if not phrases:
        return ""
    return ". ".join(phrases).rstrip(".") + "."


def _read_registry_block_text(*, world_root: Path, rel_path: str) -> str:
    """Read a species/clothing block file and return normalized text content."""
    if not rel_path:
        raise HTTPException(status_code=409, detail="Registry entry missing block path.")

    path = world_root / rel_path
    if not path.exists():
        raise HTTPException(status_code=409, detail=f"Referenced block file missing: {rel_path}")

    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8").strip()

    if path.suffix.lower() in {".yaml", ".yml"}:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            for key in ("text", "anatomy_block", "prompt_block"):
                value = loaded.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return yaml.safe_dump(loaded, sort_keys=False).strip()

    return path.read_text(encoding="utf-8").strip()


def _matches_species(entry: dict[str, Any], species: str) -> bool:
    """Return whether species entry matches requested species."""
    values = entry.get("compatible_species") or []
    if isinstance(values, list) and values:
        return species in values
    return True


def _matches_gender(entry: dict[str, Any], gender: str) -> bool:
    """Return whether entry supports requested gender."""
    values = entry.get("compatible_genders") or []
    if isinstance(values, list) and values:
        return gender in values
    return True


def _matches_species_rule(entry: dict[str, Any], species: str) -> bool:
    """Return whether species selection rules allow the requested species."""
    when = ((entry.get("selection_rules") or {}).get("when")) or {}
    if not isinstance(when, dict):
        return True
    species_any = when.get("species_any")
    if species_any is None:
        return True
    if isinstance(species_any, list):
        return species in species_any
    return False


def _nested_get(payload: dict[str, Any], path_keys: list[str]) -> Any:
    """Get nested value from mapping path, returning ``None`` when missing."""
    current: Any = payload
    for key in path_keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _build_axes_yaml_payload(payload: LabPolicyBundleDraftPayload) -> dict:
    """Convert one normalized bundle draft into canonical ``axes.yaml`` data."""

    axes: dict[str, dict] = {}
    for axis_name in payload.axes_order:
        axis: LabPolicyAxisDefinition = payload.axes[axis_name]
        ordering = list(axis.ordering)
        axes[axis_name] = {
            "group": axis.group,
            "values": ordering,
            "ordering": {"type": "ordinal", "values": ordering},
        }
    return {
        "version": payload.version,
        "source": payload.source,
        "axes": axes,
    }


def _build_thresholds_yaml_payload(payload: LabPolicyBundleDraftPayload) -> dict:
    """Convert one normalized bundle draft into canonical ``thresholds.yaml`` data."""

    axes: dict[str, dict] = {}
    for axis_name in payload.axes_order:
        axis: LabPolicyAxisDefinition = payload.axes[axis_name]
        values: dict[str, dict[str, float | None]] = {}
        for band in axis.thresholds:
            threshold: LabPolicyThresholdBand = band
            values[threshold.label] = {"min": threshold.min, "max": threshold.max}
        axes[axis_name] = {"scale": "ordinal", "values": values}
    return {
        "version": payload.version,
        "axes": axes,
    }


def _build_resolution_yaml_payload(payload: LabPolicyBundleDraftPayload) -> dict:
    """Convert one normalized bundle draft into canonical ``resolution.yaml`` data."""

    axes: dict[str, dict] = {}
    for axis_name in payload.axes_order:
        rule: LabPolicyChatAxisRule = payload.chat_rules.axes[axis_name]
        axis_rule: dict[str, object] = {"resolver": rule.resolver}
        if rule.base_magnitude is not None:
            axis_rule["base_magnitude"] = rule.base_magnitude
        axes[axis_name] = axis_rule
    return {
        "version": payload.version,
        "interactions": {
            "chat": {
                "channel_multipliers": dict(payload.chat_rules.channel_multipliers),
                "min_gap_threshold": payload.chat_rules.min_gap_threshold,
                "axes": axes,
            }
        },
    }


def _validate_policy_bundle_active_axes(
    world, world_data: dict, payload: LabPolicyBundleDraftPayload
) -> None:
    """Reject promotion when translation ``active_axes`` would drift from policy axes."""

    translation_data = world_data.get("translation_layer") or {}
    active_axes = list(translation_data.get("active_axes") or [])
    missing_axes = [axis_name for axis_name in active_axes if axis_name not in payload.axes]
    if missing_axes:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot promote policy bundle because translation_layer.active_axes "
                f"references axes missing from the promoted bundle: {', '.join(missing_axes)}."
            ),
        )


def _reload_world_axis_engine(world, world_data: dict) -> None:
    """Reload the world's axis engine after canonical policy files change."""

    axis_engine_enabled = bool((world_data.get("axis_engine") or {}).get("enabled", False))
    world.reload_axis_engine(world_data)
    if axis_engine_enabled and world.get_axis_engine() is None:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Promoted policy bundle for world {world.world_id!r} was written, "
                "but the axis engine failed to reload."
            ),
        )


def router(engine: GameEngine) -> APIRouter:
    """Build and return the lab API router.

    Args:
        engine: The live ``GameEngine`` instance, used to access the world
                registry and translation services.

    Returns:
        Configured ``APIRouter`` with all lab endpoints registered.
    """
    api = APIRouter(prefix="/api/lab", tags=["lab"])

    @api.get("/worlds", response_model=LabWorldsResponse)
    async def list_lab_worlds(session_id: str) -> LabWorldsResponse:
        """List all active worlds with translation-layer availability.

        Returns every active world known to the server, flagged with whether
        its translation layer is enabled.  Used to populate the lab UI's
        world-selector dropdown.

        Requires admin or superuser role.
        """
        require_lab_session(session_id)

        worlds_data = engine.world_registry.list_worlds()
        result: list[LabWorldSummary] = []
        for row in worlds_data:
            wid = row.get("world_id") or row.get("id", "")
            translation_enabled = False
            try:
                world = get_lab_world(engine, wid)
                translation_enabled = world.translation_layer_enabled()
            except Exception:
                # World failed to load or is inactive — surface it with
                # translation_enabled=False so the lab can still show it.
                logger.debug("World %r: translation check skipped (load error)", wid)
            result.append(
                LabWorldSummary(
                    world_id=wid,
                    name=row.get("name", wid),
                    translation_enabled=translation_enabled,
                )
            )

        return LabWorldsResponse(worlds=result)

    @api.get("/world-config/{world_id}", response_model=LabWorldConfig)
    async def get_world_config(world_id: str, session_id: str) -> LabWorldConfig:
        """Return the translation layer configuration for a world.

        Used by the lab UI to reflect the server's canonical active_axes,
        model, and validation settings without hardcoding them in the lab.

        Returns 404 if the world does not exist, is inactive, or has its
        translation layer disabled.

        Requires admin or superuser role.
        """
        require_lab_session(session_id)

        world = get_lab_world(engine, world_id)
        service = require_translation_world(world, world_id)

        return build_lab_world_config(world_id, service)

    @api.get("/world-prompts/{world_id}", response_model=LabWorldPromptsResponse)
    async def get_world_prompts(world_id: str, session_id: str) -> LabWorldPromptsResponse:
        """List prompt template files from the world's ``policies/`` directory.

        Returns each ``.txt`` file's name and content, and flags which one is
        the world's active ``prompt_template_path``.

        Requires admin or superuser role.
        """
        require_lab_session(session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        return list_world_prompts_document(world, world_id)

    @api.post(
        "/world-prompts/{world_id}/drafts",
        response_model=LabPromptDraftCreateResponse,
    )
    async def create_world_prompt_draft(
        world_id: str,
        req: LabPromptDraftCreateRequest,
    ) -> LabPromptDraftCreateResponse:
        """Create a new prompt-template draft file for one world.

        The lab may build on canonical server prompts, but it must never
        overwrite active policy files. This endpoint therefore writes only to
        ``policies/drafts`` and rejects any filename collision with either
        canonical prompt files or existing drafts.

        Requires admin or superuser role.
        """

        require_lab_session(req.session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        return create_world_prompt_draft_document(world, world_id, req)

    @api.get(
        "/world-prompts/{world_id}/drafts",
        response_model=LabPromptDraftListResponse,
    )
    async def list_world_prompt_drafts(
        world_id: str,
        session_id: str,
    ) -> LabPromptDraftListResponse:
        """List saved prompt-template drafts for one world.

        Draft files live under ``policies/drafts`` and are returned only if
        they can still be read as UTF-8 text files. Invalid files are skipped
        so the Artifact Editor sees a stable listing instead of a hard failure.

        Requires admin or superuser role.
        """

        require_lab_session(session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        return list_world_prompt_drafts_document(world, world_id)

    @api.get(
        "/world-prompts/{world_id}/drafts/{draft_name}",
        response_model=LabPromptDraftDocument,
    )
    async def get_world_prompt_draft(
        world_id: str,
        draft_name: str,
        session_id: str,
    ) -> LabPromptDraftDocument:
        """Load one saved prompt-template draft for one world.

        Requires admin or superuser role.
        """

        require_lab_session(session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        return get_world_prompt_draft_document(world, world_id, draft_name)

    @api.post(
        "/world-prompts/{world_id}/drafts/{draft_name}/promote",
        response_model=LabPromptDraftPromoteResponse,
    )
    async def promote_world_prompt_draft(
        world_id: str,
        draft_name: str,
        req: LabPromptDraftPromoteRequest,
    ) -> LabPromptDraftPromoteResponse:
        """Promote one prompt draft into a new canonical active prompt file.

        Promotion is explicit and create-only: the draft remains in place, a
        new canonical ``policies/<target>.txt`` file is created, and the
        world's active ``prompt_template_path`` is updated to point to it.
        Existing canonical prompt files are never overwritten.

        Requires admin or superuser role.
        """

        require_lab_session(req.session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        return promote_world_prompt_draft_document(world, world_id, draft_name, req)

    @api.get("/world-policy-bundle/{world_id}", response_model=LabPolicyBundleResponse)
    async def get_world_policy_bundle(world_id: str, session_id: str) -> LabPolicyBundleResponse:
        """Return one world's normalized canonical policy bundle for the lab.

        This endpoint is read-only.  It exposes the current server policy
        package as a single JSON document so the Axis Descriptor Lab can use
        the mud server as the canonical source of truth while still offering
        a text-box driven editing experience for drafts.
        """

        require_lab_session(session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        world_root = require_world_root(
            world,
            unavailable_detail=f"Axis policy files unavailable for world {world_id!r}.",
        )

        return _build_policy_bundle(world_id, world_root)

    @api.get(
        "/world-image-policy-bundle/{world_id}",
        response_model=LabImagePolicyBundleResponse,
    )
    async def get_world_image_policy_bundle(
        world_id: str, session_id: str
    ) -> LabImagePolicyBundleResponse:
        """Return one world's manifest-resolved image policy bundle.

        This endpoint is intended for integration clients that need the
        canonical image policy references and composition contract before
        calling prompt compilation/generation endpoints.
        """
        require_lab_session(session_id)

        world = get_lab_world(engine, world_id)
        world_root = require_world_root(
            world,
            unavailable_detail=f"Image policy files unavailable for world {world_id!r}.",
        )
        return _build_image_policy_bundle(world_id, world_root)

    @api.post("/compile-image-prompt", response_model=LabImageCompileResponse)
    async def compile_image_prompt(req: LabImageCompileRequest) -> LabImageCompileResponse:
        """Compile one deterministic image prompt from canonical policy assets."""

        require_lab_session(req.session_id)

        world = get_lab_world(engine, req.world_id)
        world_root = require_world_root(
            world,
            unavailable_detail=f"Image policy files unavailable for world {req.world_id!r}.",
        )
        return _compile_image_prompt(req, world_root=world_root)

    @api.post(
        "/world-policy-bundle/{world_id}/drafts",
        response_model=LabPolicyBundleDraftCreateResponse,
    )
    async def create_world_policy_bundle_draft(
        world_id: str,
        req: LabPolicyBundleDraftCreateRequest,
    ) -> LabPolicyBundleDraftCreateResponse:
        """Create a new normalized policy bundle draft for one world.

        The lab may build on canonical server artifacts, but it must never
        overwrite active policy files. This endpoint therefore writes only to
        ``policies/drafts`` and rejects any filename collision.

        Requires admin or superuser role.
        """

        require_lab_session(req.session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        return create_world_policy_bundle_draft_document(
            world,
            world_id,
            req,
            build_policy_bundle=_build_policy_bundle,
        )

    @api.get(
        "/world-policy-bundle/{world_id}/drafts",
        response_model=LabPolicyBundleDraftListResponse,
    )
    async def list_world_policy_bundle_drafts(
        world_id: str,
        session_id: str,
    ) -> LabPolicyBundleDraftListResponse:
        """List saved normalized policy bundle drafts for one world.

        Draft files live under ``policies/drafts`` and are returned only if
        they still parse as valid normalized bundle JSON for the selected
        world. Invalid files are skipped so the Artifact Editor sees a stable
        listing instead of a hard failure.

        Requires admin or superuser role.
        """

        require_lab_session(session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        return list_world_policy_bundle_drafts_document(
            world,
            world_id,
            build_policy_bundle=_build_policy_bundle,
        )

    @api.get(
        "/world-policy-bundle/{world_id}/drafts/{draft_name}",
        response_model=LabPolicyBundleDraftDocument,
    )
    async def get_world_policy_bundle_draft(
        world_id: str,
        draft_name: str,
        session_id: str,
    ) -> LabPolicyBundleDraftDocument:
        """Load one saved normalized policy bundle draft for one world.

        Requires admin or superuser role.
        """

        require_lab_session(session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        return get_world_policy_bundle_draft_document(
            world,
            world_id,
            draft_name,
            build_policy_bundle=_build_policy_bundle,
        )

    @api.post(
        "/world-policy-bundle/{world_id}/drafts/{draft_name}/promote",
        response_model=LabPolicyBundleDraftPromoteResponse,
    )
    async def promote_world_policy_bundle_draft(
        world_id: str,
        draft_name: str,
        req: LabPolicyBundleDraftPromoteRequest,
    ) -> LabPolicyBundleDraftPromoteResponse:
        """Promote one saved policy bundle draft into canonical policy files.

        Promotion is explicit and destructive only to the canonical policy
        package: the draft remains in place, while ``policies/axes.yaml``,
        ``policies/thresholds.yaml``, and ``policies/resolution.yaml`` are
        rewritten from the normalized draft payload and the world's axis
        engine is reloaded.

        Requires admin or superuser role.
        """

        require_lab_session(req.session_id)
        _require_legacy_lab_file_authoring_enabled()

        world = get_lab_world(engine, world_id)
        return promote_world_policy_bundle_draft_document(
            world,
            world_id,
            draft_name,
            req,
            build_policy_bundle=_build_policy_bundle,
            build_axes_yaml_payload=_build_axes_yaml_payload,
            build_thresholds_yaml_payload=_build_thresholds_yaml_payload,
            build_resolution_yaml_payload=_build_resolution_yaml_payload,
            write_yaml=_write_yaml,
            reload_world_axis_engine=_reload_world_axis_engine,
            validate_policy_bundle_active_axes=_validate_policy_bundle_active_axes,
            canonical_policy_source_files=_canonical_policy_source_files,
            hash_policy_payload=_hash_policy_payload,
        )

    @api.post("/translate", response_model=LabTranslateResponse)
    async def lab_translate(req: LabTranslateRequest) -> LabTranslateResponse:
        """Translate an OOC message using the world's canonical pipeline.

        Accepts raw axis values from the lab — no character DB lookup is
        performed.  The server filters the supplied axes to the world's
        ``active_axes``, builds the ``profile_summary`` in the server's
        canonical format, renders the system prompt, calls Ollama, and runs
        the validator.

        The response includes ``rendered_prompt`` so the lab can display
        exactly what was sent to Ollama, and ``world_config`` so the lab
        knows which axes and settings were applied.

        Returns 404 if the world is not found or inactive.
        Returns 503 if the world's translation layer is disabled.

        Requires admin or superuser role.
        """
        require_lab_session(req.session_id)

        world = get_lab_world(engine, req.world_id)
        service = require_translation_world(world, req.world_id, status_code=503)

        axes_raw = {name: ax.model_dump() for name, ax in req.axes.items()}
        seed = req.seed if req.seed != -1 else None

        result = service.translate_with_axes(
            axes_raw,
            req.ooc_message,
            character_name=req.character_name,
            channel=req.channel,
            seed=seed,
            temperature=req.temperature,
            prompt_template_override=req.prompt_template_override,
        )

        cfg = service.config
        world_config = build_lab_world_config(req.world_id, service)

        return LabTranslateResponse(
            ic_text=result.ic_text,
            status=result.status,
            profile_summary=result.profile_summary,
            rendered_prompt=result.rendered_prompt,
            prompt_template=result.prompt_template,
            model=cfg.model,
            world_config=world_config,
        )

    return api
