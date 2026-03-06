"""Lab-facing Pydantic models for the Axis Descriptor Lab integration."""

from typing import Any

from pydantic import BaseModel, model_validator


class LabAxisValue(BaseModel):
    """A single axis value supplied by the Axis Descriptor Lab.

    Attributes:
        label: Human-readable threshold label (e.g. ``"timid"``).
        score: Normalised axis score in the range ``[0.0, 1.0]``.
    """

    label: str
    score: float


class LabWorldConfig(BaseModel):
    """Translation layer configuration for a world, as seen by the lab.

    Returned by ``GET /api/lab/world-config/{world_id}`` and embedded in
    every ``LabTranslateResponse`` so the lab always knows which settings
    the server applied to produce a result.

    Attributes:
        world_id:           World identifier.
        name:               Display name from ``world.json``.
        model:              Ollama model tag (e.g. ``"gemma2:2b"``).
        active_axes:        Axes the world is configured to include in the
                            character profile sent to the LLM.
        strict_mode:        Whether strict output validation is enabled.
        max_output_chars:   Hard ceiling on IC output length.
        timeout_seconds:    Ollama HTTP request timeout.
        translation_enabled: ``True`` if the translation layer is active.
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
    """Brief world descriptor for the lab world-selector dropdown.

    Attributes:
        world_id:            World identifier.
        name:                Display name.
        translation_enabled: ``True`` if the translation layer is active.
    """

    world_id: str
    name: str
    translation_enabled: bool


class LabWorldsResponse(BaseModel):
    """Response to ``GET /api/lab/worlds``.

    Attributes:
        worlds: List of worlds available to the authenticated lab user.
    """

    worlds: list[LabWorldSummary]


class LabPromptFile(BaseModel):
    """A single prompt template file from the world's ``policies/`` directory.

    Attributes:
        filename:  World-relative prompt path under ``policies/`` (for example
                   ``"ic_prompt.txt"`` or ``"translation/prompts/ic/default_v1.txt"``).
        content:   Full text content of the file.
        is_active: ``True`` if this file is the world's configured
                   ``prompt_template_path``.
    """

    filename: str
    content: str
    is_active: bool


class LabWorldPromptsResponse(BaseModel):
    """Response to ``GET /api/lab/world-prompts/{world_id}``.

    Attributes:
        world_id: World identifier.
        prompts:  List of prompt template files found in the world's
                  ``policies/`` directory.
    """

    world_id: str
    prompts: list[LabPromptFile]


class LabPromptDraftCreateRequest(BaseModel):
    """Request to create a new prompt draft file for one world.

    Attributes:
        session_id: Active admin or superuser session.
        draft_name: Filename stem for the new draft, without ``.txt``.
        content: Raw prompt template text to write.
        based_on_name: Optional source artifact name the draft was derived from.
    """

    session_id: str
    draft_name: str
    content: str
    based_on_name: str | None = None


class LabPromptDraftCreateResponse(BaseModel):
    """Response returned after creating a new prompt draft.

    Attributes:
        name: Draft file stem without ``.txt``.
        origin_path: World-relative path of the created draft file.
        world_id: World that owns the created draft.
        based_on_name: Optional source artifact name copied from the request.
    """

    name: str
    origin_path: str
    world_id: str
    based_on_name: str | None = None


class LabPromptDraftSummary(BaseModel):
    """Metadata for one prompt draft file stored by the mud server.

    Attributes:
        name: Draft file stem without ``.txt``.
        origin_path: World-relative path to the draft file.
        world_id: World that owns the draft file.
        based_on_name: Optional source artifact name carried from draft creation.
    """

    name: str
    origin_path: str
    world_id: str
    based_on_name: str | None = None


class LabPromptDraftListResponse(BaseModel):
    """Response to ``GET /api/lab/world-prompts/{world_id}/drafts``.

    Attributes:
        world_id: World identifier.
        drafts: List of saved draft prompt files for that world.
    """

    world_id: str
    drafts: list[LabPromptDraftSummary]


class LabPromptDraftDocument(BaseModel):
    """Response to ``GET /api/lab/world-prompts/{world_id}/drafts/{name}``.

    Attributes:
        name: Draft file stem without ``.txt``.
        origin_path: World-relative path to the draft file.
        world_id: World that owns the draft file.
        based_on_name: Optional source artifact name carried from draft creation.
        content: Raw prompt template text stored on disk.
    """

    name: str
    origin_path: str
    world_id: str
    based_on_name: str | None = None
    content: str


class LabPromptDraftPromoteRequest(BaseModel):
    """Request to promote a prompt draft into a canonical active prompt file.

    Attributes:
        session_id: Active admin or superuser session.
        target_name: Filename stem for the canonical prompt file, without
            ``.txt``. The target must not already exist.
    """

    session_id: str
    target_name: str


class LabPromptDraftPromoteResponse(BaseModel):
    """Response returned after promoting a prompt draft to canonical status.

    Attributes:
        name: Draft file stem without ``.txt``.
        world_id: World that owns the promoted prompt.
        canonical_name: Canonical prompt file stem created by the promotion.
        canonical_path: World-relative path of the created canonical prompt.
        active_prompt_path: Updated ``translation_layer.prompt_template_path``.
    """

    name: str
    world_id: str
    canonical_name: str
    canonical_path: str
    active_prompt_path: str


class LabPolicyBundleResponse(BaseModel):
    """Normalized world policy bundle returned to the Axis Descriptor Lab.

    This response exposes the mud server's canonical policy package as one
    read-only JSON document so the lab can inspect and draft against the
    current server contract without re-parsing YAML itself.

    Attributes:
        world_id: World identifier.
        version: Policy package version mirrored from the canonical files.
        source: Human-readable provenance string describing the normalization.
        policy_hash: Deterministic hash of the combined axes/threshold payload.
        source_files: Canonical server file paths that were normalized into
            this bundle.
        axes_order: Canonical axis ordering derived from ``axes.yaml``.
        axes: Per-axis group, ordinal ordering, and threshold ranges.
        chat_rules: Chat interaction rules normalized from ``resolution.yaml``.
    """

    world_id: str
    version: str
    source: str
    policy_hash: str | None
    source_files: list[str]
    axes_order: list[str]
    axes: dict[str, Any]
    chat_rules: dict[str, Any]


class LabImagePolicyBundleResponse(BaseModel):
    """Manifest-resolved image policy bundle for one world.

    This model exposes the canonical image-policy contract the server resolves
    from ``policies/manifest.yaml`` and referenced assets. It is intentionally
    read-only and diagnostic so integration clients can verify migration state.

    Attributes:
        world_id: World identifier.
        policy_schema: Manifest schema id (for parser compatibility).
        policy_bundle_id: Active policy bundle id.
        policy_bundle_version: Active policy bundle version.
        policy_hash: Deterministic hash of manifest-resolved compiler inputs.
        composition_order: Ordered image block composition.
        required_runtime_inputs: Runtime inputs required for deterministic compile.
        descriptor_layer_path: Manifest-referenced descriptor layer path.
        tone_profile_path: Manifest-referenced tone profile path.
        species_registry_path: Manifest-referenced species registry path.
        clothing_registry_path: Manifest-referenced clothing registry path.
        missing_components: Validation/report issues from manifest resolution.
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


class LabPolicyThresholdBand(BaseModel):
    """One ordinal threshold band inside a normalized policy bundle."""

    label: str
    min: float | None = None
    max: float | None = None


class LabPolicyAxisDefinition(BaseModel):
    """Normalized axis definition used by policy bundle drafts and promotion."""

    group: str
    ordering: list[str]
    thresholds: list[LabPolicyThresholdBand]


class LabPolicyChatAxisRule(BaseModel):
    """One chat-resolution rule for an axis in the normalized bundle."""

    resolver: str
    base_magnitude: float | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> "LabPolicyChatAxisRule":
        """Require base_magnitude on any resolver that is not a no-op."""

        if self.resolver != "no_effect" and self.base_magnitude is None:
            raise ValueError("base_magnitude is required unless resolver is 'no_effect'")
        return self


class LabPolicyChatRules(BaseModel):
    """Normalized chat-resolution block used by policy bundle drafts."""

    channel_multipliers: dict[str, float]
    min_gap_threshold: float
    axes: dict[str, LabPolicyChatAxisRule]

    @model_validator(mode="after")
    def validate_channels(self) -> "LabPolicyChatRules":
        """Require the canonical say/yell/whisper chat channel set."""

        if set(self.channel_multipliers) != {"say", "yell", "whisper"}:
            raise ValueError("channel_multipliers must define exactly say, yell, and whisper")
        return self


class LabPolicyBundleDraftPayload(BaseModel):
    """Normalized policy bundle payload accepted for draft creation.

    This mirrors the lab-facing JSON bundle shape, minus ``source_files``, so
    the lab can submit edited drafts back to the mud server without needing to
    reconstruct the original YAML package layout.

    Attributes:
        world_id: World identifier that owns the draft.
        version: Draft policy bundle version string.
        source: Human-readable provenance string carried into the draft file.
        policy_hash: Optional hash copied from the canonical source bundle.
        axes_order: Canonical axis ordering used by the bundle.
        axes: Normalized per-axis metadata and threshold ranges.
        chat_rules: Normalized chat-resolution rules.
    """

    world_id: str
    version: str
    source: str
    policy_hash: str | None = None
    axes_order: list[str]
    axes: dict[str, LabPolicyAxisDefinition]
    chat_rules: LabPolicyChatRules

    @model_validator(mode="after")
    def validate_consistency(self) -> "LabPolicyBundleDraftPayload":
        """Require consistent axis coverage across the normalized bundle."""

        if self.axes_order != list(self.axes.keys()):
            raise ValueError("axes_order must match the axes object key order exactly")
        if set(self.chat_rules.axes) != set(self.axes):
            raise ValueError("chat_rules.axes must define exactly the same axis set as axes")
        return self


class LabPolicyBundleDraftCreateRequest(BaseModel):
    """Request to create a new policy bundle draft file for one world.

    Attributes:
        session_id: Active admin or superuser session.
        draft_name: Filename stem for the new draft, without ``.json``.
        content: Validated normalized policy bundle JSON to write.
        based_on_name: Optional source artifact name the draft was derived from.
    """

    session_id: str
    draft_name: str
    content: LabPolicyBundleDraftPayload
    based_on_name: str | None = None


class LabPolicyBundleDraftCreateResponse(BaseModel):
    """Response returned after creating a new policy bundle draft.

    Attributes:
        name: Draft file stem without ``.json``.
        origin_path: World-relative path of the created draft file.
        world_id: World that owns the created draft.
        version: Version declared by the saved draft payload.
        based_on_name: Optional source artifact name copied from the request.
    """

    name: str
    origin_path: str
    world_id: str
    version: str
    based_on_name: str | None = None


class LabPolicyBundleDraftSummary(BaseModel):
    """Metadata for one policy bundle draft file stored by the mud server.

    Attributes:
        name: Draft file stem without ``.json``.
        origin_path: World-relative path to the draft file.
        world_id: World that owns the draft file.
        version: Version declared inside the draft payload.
        based_on_name: Optional source artifact name carried from draft creation.
    """

    name: str
    origin_path: str
    world_id: str
    version: str
    based_on_name: str | None = None


class LabPolicyBundleDraftListResponse(BaseModel):
    """Response to ``GET /api/lab/world-policy-bundle/{world_id}/drafts``.

    Attributes:
        world_id: World identifier.
        drafts: List of saved draft bundle files for that world.
    """

    world_id: str
    drafts: list[LabPolicyBundleDraftSummary]


class LabPolicyBundleDraftDocument(BaseModel):
    """Response to ``GET /api/lab/world-policy-bundle/{world_id}/drafts/{name}``.

    Attributes:
        name: Draft file stem without ``.json``.
        origin_path: World-relative path to the draft file.
        world_id: World that owns the draft file.
        version: Version declared inside the draft payload.
        based_on_name: Optional source artifact name carried from draft creation.
        content: Full normalized policy bundle draft payload.
    """

    name: str
    origin_path: str
    world_id: str
    version: str
    based_on_name: str | None = None
    content: LabPolicyBundleDraftPayload


class LabPolicyBundleDraftPromoteRequest(BaseModel):
    """Request to promote one saved policy bundle draft into canonical files.

    Attributes:
        session_id: Active admin or superuser session.
    """

    session_id: str


class LabPolicyBundleDraftPromoteResponse(BaseModel):
    """Response returned after promoting a policy bundle draft.

    Attributes:
        name: Draft file stem without ``.json``.
        world_id: World that owns the promoted bundle.
        canonical_name: Stable lab-facing canonical bundle name.
        source_files: Canonical policy files rewritten from the bundle.
        version: Version written to the canonical policy package.
        policy_hash: Deterministic hash of the promoted axes/threshold payload.
    """

    name: str
    world_id: str
    canonical_name: str
    source_files: list[str]
    version: str
    policy_hash: str | None = None


class LabTranslateRequest(BaseModel):
    """Request to ``POST /api/lab/translate``.

    Carries raw axis values from the lab UI — no character DB lookup is
    performed server-side.  The server filters ``axes`` to the world's
    ``active_axes`` before building the profile.

    Attributes:
        session_id:     Active admin/superuser session.
        world_id:       Target world (e.g. ``"pipeworks_web"``).
        axes:           Dict of axis name → ``LabAxisValue``.  May include
                        axes not in ``active_axes``; they are ignored.
        channel:        Chat channel context.  One of ``"say"``,
                        ``"yell"``, ``"whisper"``.
        ooc_message:    Raw OOC message to translate.
        character_name: Name used in the ``profile_summary`` first line.
        seed:           Ollama seed for deterministic output.  ``-1`` means
                        non-deterministic.
        temperature:    Sampling temperature.  Ignored when seed is set.
        prompt_template_override: Optional full prompt template text.  When
                        provided, used instead of the world's configured
                        ``prompt_template_path`` for this single call only.
                        The server's canonical file is never modified.
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
    """Response from ``POST /api/lab/translate``.

    Attributes:
        ic_text:         Validated IC dialogue, or ``None`` on fallback.
        status:          ``"success"``, ``"fallback.api_error"``, or
                         ``"fallback.validation_failed"``.
        profile_summary: The ``{{profile_summary}}`` block as the server
                         formatted it (canonical format for the world).
        rendered_prompt: The fully-rendered system prompt sent to Ollama,
                         with all placeholders resolved.
        prompt_template: Raw template text before per-character variable
                         substitution.  Hash this (not ``rendered_prompt``)
                         to identify which prompt file was used.
        model:           Ollama model tag used for this translation.
        world_config:    World configuration that was applied.
    """

    ic_text: str | None
    status: str
    profile_summary: str
    rendered_prompt: str
    prompt_template: str
    model: str
    world_config: LabWorldConfig


class LabImageCompileRequest(BaseModel):
    """Request to compile one deterministic image prompt from canonical policy.

    Attributes:
        session_id: Active admin/superuser session.
        world_id: Target world identifier.
        species: Species identifier used for species block selection.
        gender: Fixed identity gender value. Phase-1 allowed values are
            ``"male"`` and ``"female"``.
        axes: Axis payload used for descriptor/clothing selection context.
        world_context: Optional world-context tags used by clothing selection
            (for example ``"coastal"``, ``"harbor"``).
        occupation_signals: Optional occupation/activity tags used by clothing
            selection (for example ``"manual_labour"``, ``"trade"``).
        model_id: Optional generation model hint returned in defaults.
        aspect_ratio: Optional aspect-ratio hint returned in defaults.
        seed: Optional generation seed hint returned in defaults.
    """

    session_id: str
    world_id: str
    species: str
    gender: str
    axes: dict[str, LabAxisValue]
    world_context: list[str] = []
    occupation_signals: list[str] = []
    model_id: str | None = None
    aspect_ratio: str | None = None
    seed: int | None = None

    @model_validator(mode="after")
    def validate_gender(self) -> "LabImageCompileRequest":
        """Normalize and validate phase-1 gender values."""
        normalized = self.gender.strip().lower()
        if normalized not in {"male", "female"}:
            raise ValueError("gender must be one of: male, female")
        self.gender = normalized
        return self


class LabImageCompileResponse(BaseModel):
    """Response from ``POST /api/lab/compile-image-prompt``.

    Attributes:
        world_id: World identifier.
        policy_schema: Manifest schema identifier.
        policy_bundle_id: Active policy bundle id.
        policy_bundle_version: Active policy bundle version.
        policy_hash: Deterministic hash of compiler policy inputs.
        axis_hash: Deterministic hash of runtime axis payload.
        required_runtime_inputs: Runtime input keys required by composition.
        selected_descriptor_layer_id: Selected descriptor layer id.
        selected_tone_profile_id: Selected tone profile id.
        selected_species_block_id: Selected species block entry id.
        selected_clothing_profile_id: Selected clothing profile id.
        selected_clothing_slot_ids: Selected clothing entry ids by slot.
        compiled_prompt: Final deterministic prompt string.
        generation_defaults: Generation defaults derived from request/manifest.
        missing_components: Non-fatal validation/report issues encountered.
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
