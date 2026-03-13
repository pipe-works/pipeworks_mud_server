"""Lab-facing API models for DB-first policy and translation workflows.

This module intentionally exports only models that back active ``/api/lab/*``
routes. Legacy file-authoring draft models were removed as part of the DB-only
runtime transition, so clients interacting with this contract should assume:

1. Canonical policy state is resolved from SQLite policy tables.
2. Effective runtime behavior is selected through policy activations by scope.
3. Lab endpoints are diagnostic/authoring helpers on top of canonical DB data.
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class LabAxisValue(BaseModel):
    """One axis value supplied by a lab client.

    ``label`` carries the user-facing categorical name and ``score`` carries
    the deterministic numeric value used by downstream policy compilation.
    """

    label: str
    score: float


class LabWorldConfig(BaseModel):
    """Translation layer configuration snapshot for one world.

    Returned to clients so they can inspect which runtime translation settings
    were actually applied by the server for the selected world.
    """

    world_id: str
    name: str
    model: str
    active_axes: list[str]
    strict_mode: bool
    max_output_chars: int
    timeout_seconds: float
    translation_enabled: bool


class LabWorldSummary(BaseModel):
    """One world entry shown in the lab world-selector."""

    world_id: str
    name: str
    translation_enabled: bool


class LabWorldsResponse(BaseModel):
    """Response payload for ``GET /api/lab/worlds``."""

    worlds: list[LabWorldSummary]


class LabImagePolicyBundleResponse(BaseModel):
    """DB-resolved image policy bundle for one world scope.

    This payload mirrors the canonical image policy bundle contract consumed by
    integration clients. Path-like fields are informational identifiers retained
    for compatibility with existing clients; canonical resolution happens in DB.
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


class LabTranslateRequest(BaseModel):
    """Request payload for ``POST /api/lab/translate``.

    ``prompt_template_override`` is request-local and never mutates canonical
    prompt policy rows. It exists to support one-off lab experimentation.
    """

    session_id: str
    world_id: str
    axes: dict[str, LabAxisValue]
    channel: str = "say"
    ooc_message: str
    character_name: str = "Lab Subject"
    seed: int = -1
    temperature: float = 0.7
    prompt_template_override: str | None = None


class LabTranslateResponse(BaseModel):
    """Response payload for ``POST /api/lab/translate``.

    Includes both generated text and debugging context (rendered prompt, active
    prompt template, and world config) so operators can audit behavior.
    """

    ic_text: str | None
    status: str
    profile_summary: str
    rendered_prompt: str
    prompt_template: str
    model: str
    world_config: LabWorldConfig


class LabImageCompileRequest(BaseModel):
    """Request payload for ``POST /api/lab/compile-image-prompt``.

    The request combines fixed traits, runtime axis values, and optional
    contextual tags. The server composes these inputs against activated policy
    objects to produce a deterministic image prompt bundle output.
    """

    session_id: str
    world_id: str
    species: str
    gender: str
    axes: dict[str, LabAxisValue]
    world_context: list[str] = Field(default_factory=list)
    occupation_signals: list[str] = Field(default_factory=list)
    model_id: str | None = None
    aspect_ratio: str | None = None
    seed: int | None = None

    @model_validator(mode="after")
    def validate_gender(self) -> "LabImageCompileRequest":
        """Normalize and validate fixed-trait gender values for phase-1 compile."""
        normalized = self.gender.strip().lower()
        if normalized not in {"male", "female"}:
            raise ValueError("gender must be one of: male, female")
        self.gender = normalized
        return self


class LabImageCompileResponse(BaseModel):
    """Response payload for ``POST /api/lab/compile-image-prompt``.

    Returns selected policy object identities and deterministic hashes so
    downstream tools can trace exactly which canonical variants were used.
    """

    world_id: str
    policy_schema: str | None
    policy_bundle_id: str | None
    policy_bundle_version: int | str | None
    policy_hash: str
    axis_hash: str
    required_runtime_inputs: list[str]
    selected_descriptor_layer_id: str | None
    selected_tone_profile_id: str | None
    selected_species_block_id: str | None
    selected_clothing_profile_id: str | None
    selected_clothing_slot_ids: dict[str, str | None]
    compiled_prompt: str
    generation_defaults: dict[str, Any]
    missing_components: list[str]
