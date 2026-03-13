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

GET  /api/lab/world-image-policy-bundle/{world_id}
    Return the DB-resolved image policy bundle (composition order, runtime
    input requirements, and manifest-derived reference metadata).

POST /api/lab/compile-image-prompt
    Compile a deterministic image prompt from DB-resolved policy assets
    and runtime inputs (species, gender, axes, optional context signals).

POST /api/lab/translate
    Translate an OOC message to IC dialogue using the world's canonical
    pipeline.  Accepts raw axis values — no character DB lookup is
    performed.  Returns the IC text, outcome status, the server-formatted
    profile_summary, and the fully-rendered system prompt sent to Ollama.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pipeworks_ipc import compute_payload_hash

from mud_server.api.models import (
    LabImageCompileRequest,
    LabImageCompileResponse,
    LabImagePolicyBundleResponse,
    LabTranslateRequest,
    LabTranslateResponse,
    LabWorldConfig,
    LabWorldsResponse,
    LabWorldSummary,
)
from mud_server.api.routes.lab_support import (
    build_lab_world_config,
    get_lab_world,
    require_lab_session,
    require_translation_world,
)
from mud_server.core.engine import GameEngine
from mud_server.services import policy_service

logger = logging.getLogger(__name__)


def _build_image_policy_bundle(world_id: str) -> LabImagePolicyBundleResponse:
    """Build one DB-first image policy bundle response for diagnostic clients."""
    scope = policy_service.ActivationScope(world_id=world_id, client_profile="")
    try:
        resolved = policy_service.resolve_effective_image_policy_bundle(scope=scope)
    except policy_service.PolicyServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    return LabImagePolicyBundleResponse(
        world_id=resolved.world_id,
        policy_schema=resolved.policy_schema,
        policy_bundle_id=resolved.policy_bundle_id,
        policy_bundle_version=resolved.policy_bundle_version,
        policy_hash=resolved.policy_hash,
        composition_order=resolved.composition_order,
        required_runtime_inputs=resolved.required_runtime_inputs,
        descriptor_layer_path=resolved.descriptor_layer_path,
        tone_profile_path=resolved.tone_profile_path,
        species_registry_path=resolved.species_registry_path,
        clothing_registry_path=resolved.clothing_registry_path,
        missing_components=resolved.missing_components,
    )


def _compile_image_prompt(
    req: LabImageCompileRequest,
) -> LabImageCompileResponse:
    """Compile one deterministic image prompt from canonical DB policy objects.

    The compiler is intentionally policy-driven and deterministic:

    1. Resolve effective manifest + Layer 2 policy rows from activation state.
    2. Select species/clothing block references using registry rules.
    3. Resolve Layer 1 block text from canonical DB variants.
    4. Assemble the prompt in manifest-defined composition order.
    5. Return selection metadata and deterministic provenance hashes.

    Raises:
        HTTPException: When required canonical policy rows are missing or
            selection cannot produce required blocks.
    """
    scope = policy_service.ActivationScope(world_id=req.world_id, client_profile="")
    manifest_payload = _resolve_effective_manifest_payload(scope=scope)
    composition_order, required_runtime_inputs = _extract_manifest_image_contract(manifest_payload)

    descriptor_preferred_policy_id = _manifest_policy_id_hint(
        manifest_payload=manifest_payload,
        image_node_key="descriptor_layer",
        policy_type="descriptor_layer",
        namespace="image.descriptors",
    )
    tone_preferred_policy_id = _manifest_policy_id_hint(
        manifest_payload=manifest_payload,
        image_node_key="tone_profile",
        policy_type="tone_profile",
        namespace="image.tone_profiles",
    )

    descriptor_row, descriptor_activation = _resolve_effective_policy_row(
        scope=scope,
        policy_type="descriptor_layer",
        preferred_policy_id=descriptor_preferred_policy_id,
    )
    tone_row, tone_activation = _resolve_effective_policy_row(
        scope=scope,
        policy_type="tone_profile",
        preferred_policy_id=tone_preferred_policy_id,
    )
    species_registry_row, _ = _resolve_effective_policy_row(
        scope=scope,
        policy_type="registry",
        preferred_policy_id="registry:image.registries:species_registry",
    )
    clothing_registry_row, _ = _resolve_effective_policy_row(
        scope=scope,
        policy_type="registry",
        preferred_policy_id="registry:image.registries:clothing_registry",
    )

    descriptor_layer_text = (descriptor_row.get("content") or {}).get("text")
    tone_profile_payload = tone_row.get("content")
    species_registry = species_registry_row.get("content")
    clothing_registry = clothing_registry_row.get("content")

    if not isinstance(descriptor_layer_text, str) or not descriptor_layer_text.strip():
        raise HTTPException(
            status_code=409,
            detail=(
                "Descriptor layer content missing canonical text payload: "
                f"{descriptor_activation['policy_id']}:{descriptor_activation['variant']}"
            ),
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

    species_block_text = _resolve_registry_entry_policy_text(
        scope=scope,
        entry=selected_species_entry,
        allowed_policy_types={"species_block"},
    )

    selected_clothing_profile_id = _extract_clothing_profile_id(clothing_registry)
    selected_clothing_slots, clothing_blocks = _select_clothing_blocks(
        clothing_registry=clothing_registry,
        scope=scope,
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
            "descriptor_layer_text": descriptor_layer_text,
            "tone_profile_payload": tone_profile_payload,
            "descriptor_policy_id": descriptor_activation["policy_id"],
            "descriptor_variant": descriptor_activation["variant"],
            "tone_policy_id": tone_activation["policy_id"],
            "tone_variant": tone_activation["variant"],
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

    descriptor_id = _nested_get(manifest_payload, ["image", "descriptor_layer", "id"]) or str(
        descriptor_activation["policy_id"]
    )
    tone_id = _nested_get(manifest_payload, ["image", "tone_profile", "id"]) or str(
        tone_activation["policy_id"]
    )
    policy_schema = _nested_get(manifest_payload, ["policy_schema"])
    bundle_id = _nested_get(manifest_payload, ["policy_bundle", "id"])
    bundle_version = _nested_get(manifest_payload, ["policy_bundle", "version"])

    return LabImageCompileResponse(
        world_id=req.world_id,
        policy_schema=str(policy_schema) if policy_schema is not None else None,
        policy_bundle_id=str(bundle_id) if bundle_id is not None else None,
        policy_bundle_version=(str(bundle_version) if bundle_version is not None else None),
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


def _resolve_effective_manifest_payload(*, scope: policy_service.ActivationScope) -> dict[str, Any]:
    """Resolve manifest payload from canonical effective activation state."""
    manifest_policy_id = f"manifest_bundle:world.manifests:{scope.world_id}"
    try:
        manifest_row = policy_service.get_effective_policy_variant(
            scope=scope,
            policy_id=manifest_policy_id,
        )
    except policy_service.PolicyServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    if manifest_row is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "No effective manifest bundle activation found for compile scope "
                f"(world_id={scope.world_id!r}, client_profile={scope.client_profile!r})."
            ),
        )

    manifest_payload = (manifest_row.get("content") or {}).get("manifest")
    if not isinstance(manifest_payload, dict):
        raise HTTPException(
            status_code=409,
            detail=(
                "Effective manifest bundle row is missing content.manifest object: "
                f"{manifest_policy_id}:{manifest_row.get('variant')}"
            ),
        )
    return manifest_payload


def _extract_manifest_image_contract(
    manifest_payload: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Extract image composition contract fields from manifest payload."""
    composition = _nested_get(manifest_payload, ["image", "composition"])
    if not isinstance(composition, dict):
        raise HTTPException(
            status_code=409,
            detail="Manifest content missing image.composition object for compile.",
        )
    composition_order = composition.get("order")
    if not isinstance(composition_order, list) or not composition_order:
        raise HTTPException(
            status_code=409,
            detail="Manifest image.composition.order must be a non-empty list.",
        )
    required_runtime_inputs = composition.get("required_runtime_inputs")
    if not isinstance(required_runtime_inputs, list):
        raise HTTPException(
            status_code=409,
            detail="Manifest image.composition.required_runtime_inputs must be a list.",
        )
    return [str(value) for value in composition_order], [
        str(value) for value in required_runtime_inputs
    ]


def _manifest_policy_id_hint(
    *,
    manifest_payload: dict[str, Any],
    image_node_key: str,
    policy_type: str,
    namespace: str,
) -> str | None:
    """Build preferred canonical policy_id from one manifest image node."""
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


def _resolve_effective_policy_row(
    *,
    scope: policy_service.ActivationScope,
    policy_type: str,
    preferred_policy_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve one effective activated policy row for a requested policy type."""
    try:
        effective_rows = policy_service.resolve_effective_policy_activations(scope=scope)
    except policy_service.PolicyServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    candidates = [
        row for row in effective_rows if str(row.get("policy_id", "")).startswith(f"{policy_type}:")
    ]
    if preferred_policy_id:
        for row in candidates:
            if str(row.get("policy_id")) == preferred_policy_id:
                selected_row = row
                break
        else:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Preferred active {policy_type} policy is not activated for scope "
                    f"(world_id={scope.world_id!r}, client_profile={scope.client_profile!r}): "
                    f"{preferred_policy_id}."
                ),
            )
    else:
        if len(candidates) != 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Expected exactly one active {policy_type} policy for scope "
                    f"(world_id={scope.world_id!r}, client_profile={scope.client_profile!r}); "
                    f"found {len(candidates)}."
                ),
            )
        selected_row = candidates[0]

    policy_id = str(selected_row.get("policy_id") or "")
    variant = str(selected_row.get("variant") or "")
    try:
        policy_row = policy_service.get_policy(policy_id=policy_id, variant=variant)
    except policy_service.PolicyServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    return policy_row, selected_row


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
    scope: policy_service.ActivationScope,
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
        selected_block_texts.append(
            _resolve_registry_entry_policy_text(
                scope=scope,
                entry=selected,
                allowed_policy_types={"clothing_block"},
            )
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


def _resolve_registry_entry_policy_text(
    *,
    scope: policy_service.ActivationScope,
    entry: dict[str, Any],
    allowed_policy_types: set[str],
) -> str:
    """Resolve one registry-selected Layer 1 text block from canonical DB rows."""
    policy_reference = entry.get("policy_ref")
    if not isinstance(policy_reference, dict):
        raise HTTPException(
            status_code=409,
            detail=(
                "Registry entry missing canonical policy_ref mapping for scope "
                f"(world_id={scope.world_id!r}): {entry.get('id')!r}"
            ),
        )

    policy_id = str(policy_reference.get("policy_id") or "").strip()
    variant = str(policy_reference.get("variant") or "").strip()
    if not policy_id or not variant:
        raise HTTPException(
            status_code=409,
            detail=f"Registry entry has invalid policy_ref: {policy_reference!r}",
        )
    policy_type = policy_id.split(":", 1)[0]
    if policy_type not in allowed_policy_types:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Registry entry policy_ref type must be one of {sorted(allowed_policy_types)}; "
                f"got {policy_type!r} ({policy_id}:{variant})."
            ),
        )

    try:
        row = policy_service.get_policy(policy_id=policy_id, variant=variant)
    except policy_service.PolicyServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    content = row.get("content")
    if not isinstance(content, dict):
        raise HTTPException(
            status_code=409,
            detail=f"Policy variant content must be an object: {policy_id}:{variant}",
        )
    text_value = content.get("text")
    if not isinstance(text_value, str) or not text_value.strip():
        raise HTTPException(
            status_code=409,
            detail=f"Policy variant content.text must be non-empty: {policy_id}:{variant}",
        )
    return text_value.strip()


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
        _ = world  # Route still validates world availability via registry lookup.
        return _build_image_policy_bundle(world_id)

    @api.post("/compile-image-prompt", response_model=LabImageCompileResponse)
    async def compile_image_prompt(req: LabImageCompileRequest) -> LabImageCompileResponse:
        """Compile one deterministic image prompt from canonical policy assets."""

        require_lab_session(req.session_id)

        world = get_lab_world(engine, req.world_id)
        _ = world  # Route still validates world availability via registry lookup.
        return _compile_image_prompt(req)

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
