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
"""

from __future__ import annotations

import logging
from hashlib import sha256
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from mud_server.api.models import (
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

logger = logging.getLogger(__name__)


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

    policy_root = world_root / "policies"
    axes_payload = _read_yaml(policy_root / "axes.yaml")
    thresholds_payload = _read_yaml(policy_root / "thresholds.yaml")
    resolution_payload = _read_yaml(policy_root / "resolution.yaml")

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
        source_files=[
            "policies/axes.yaml",
            "policies/thresholds.yaml",
            "policies/resolution.yaml",
        ],
        axes_order=axes_order,
        axes=normalized_axes,
        chat_rules=normalized_chat_rules,
    )


def _canonical_policy_source_files() -> list[str]:
    """Return the stable canonical file set for world policy bundles."""

    return [
        "policies/axes.yaml",
        "policies/thresholds.yaml",
        "policies/resolution.yaml",
    ]


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

        world = get_lab_world(engine, world_id)
        world_root = require_world_root(
            world,
            unavailable_detail=f"Axis policy files unavailable for world {world_id!r}.",
        )

        return _build_policy_bundle(world_id, world_root)

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
