"""Unit tests for OOCToICTranslationService and its module-level helpers.

Test organisation
-----------------
``TestBuildProfileSummary``
    Unit tests for :func:`_build_profile_summary`.  Exercises the summary
    formatter in isolation — no service or DB interaction required.

``TestExtractSnapshot``
    Unit tests for :func:`_extract_snapshot`.  Exercises the ledger
    snapshot builder in isolation.

``TestEmitTranslationEvent``
    Unit tests for :func:`_emit_translation_event`.  Exercises the
    fire-and-forget ledger helper directly with a mock append function.

``TestConstructorValidation``
    Validates that ``OOCToICTranslationService.__init__`` rejects bad args.

``TestTranslateSuccess``
    Happy-path translate() tests: IC text returned, channel injected.

``TestTranslateFallback``
    Unhappy-path translate() tests: profile missing, renderer fails,
    validation fails, service disabled.

``TestDeterministicMode``
    Verifies the ipc_hash → renderer.set_deterministic() wiring.

``TestPromptTemplate``
    Verifies template loading (custom file vs. built-in fallback).

``TestSystemPromptRendering``
    Verifies placeholder substitution in the rendered prompt, including
    the critical guard that ``{{profile_summary}}`` is always resolved.

``TestLedgerIntegration``
    End-to-end tests confirming translate() emits the correct ledger
    events through the full call stack (profile builder and renderer
    mocked; ledger append function patched at the module level).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mud_server.translation.config import TranslationLayerConfig
from mud_server.translation.service import (
    LabTranslateResult,
    OOCToICTranslationService,
    _build_profile_summary,
    _emit_translation_event,
    _extract_snapshot,
)

WORLD_ID = "test_world"


# ── Test helpers ──────────────────────────────────────────────────────────────


def _make_config(*, enabled=True, deterministic=False, **kwargs) -> TranslationLayerConfig:
    """Build a ``TranslationLayerConfig`` with sensible test defaults.

    Keyword-only flags ``enabled`` and ``deterministic`` are exposed for
    convenience.  Any other field can be overridden via ``**kwargs``.
    """
    data = {
        "enabled": enabled,
        "model": "gemma2:2b",
        "strict_mode": True,
        "max_output_chars": 280,
        "deterministic": deterministic,
        **kwargs,
    }
    return TranslationLayerConfig.from_dict(data, world_root=Path("/fake"))


def _make_service(tmp_path: Path, *, deterministic=False) -> OOCToICTranslationService:
    """Build a service instance backed by a minimal ic_prompt.txt in tmp_path.

    The template uses ``{{ooc_message}}``, ``{{demeanor_label}}``, and
    ``{{channel}}`` — individual axis placeholders rather than
    ``{{profile_summary}}``.  This keeps existing tests focused on the
    specific behaviour they were written to verify without requiring a
    fully-populated profile_summary.

    For tests that specifically verify ``{{profile_summary}}`` resolution,
    use :func:`_make_service_with_profile_summary_template` instead.
    """
    prompt_file = tmp_path / "policies" / "ic_prompt.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(
        "Translate: {{ooc_message}}\nDemeanor: {{demeanor_label}}\nChannel: {{channel}}"
    )
    cfg = _make_config(
        enabled=True,
        deterministic=deterministic,
        prompt_template_path="policies/ic_prompt.txt",
    )
    return OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)


def _make_service_with_profile_summary_template(
    tmp_path: Path,
) -> OOCToICTranslationService:
    """Build a service whose template uses the ``{{profile_summary}}`` placeholder.

    Use this helper in tests that need to confirm ``{{profile_summary}}``
    is resolved by translate() before reaching the renderer.
    """
    prompt_file = tmp_path / "policies" / "ic_prompt.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(
        "PROFILE:\n{{profile_summary}}\nMODE: {{channel}}\nMESSAGE: {{ooc_message}}"
    )
    cfg = _make_config(enabled=True, prompt_template_path="policies/ic_prompt.txt")
    return OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)


# ── TestBuildProfileSummary ───────────────────────────────────────────────────


class TestBuildProfileSummary:
    """Unit tests for the _build_profile_summary module-level helper.

    These tests exercise the summary formatter directly, independently of
    the full translate() pipeline, so that formatting regressions produce
    clear, targeted failures.

    The summary block is the fix for a production bug where
    ``{{profile_summary}}`` was forwarded to Ollama as a literal unresolved
    string, making the LLM blind to all character axis data.
    """

    def _full_profile(self) -> dict:
        """Return a profile dict matching the pipeworks_web active_axes config."""
        return {
            "character_name": "Ddishfew Withnop",
            "channel": "say",
            "demeanor_label": "timid",
            "demeanor_score": 0.069,
            "health_label": "scarred",
            "health_score": 0.655,
            "physique_label": "skinny",
            "physique_score": 0.405,
            "wealth_label": "well-kept",
            "wealth_score": 0.495,
            "facial_signal_label": "asymmetrical",
            "facial_signal_score": 0.5,
        }

    def test_contains_character_name(self) -> None:
        """The summary's first line identifies the character by name."""
        result = _build_profile_summary(self._full_profile())
        assert "Character: Ddishfew Withnop" in result

    def test_contains_all_active_axes(self) -> None:
        """Every axis in the profile appears in the summary output."""
        result = _build_profile_summary(self._full_profile())
        assert "Demeanor: timid" in result
        assert "Health: scarred" in result
        assert "Physique: skinny" in result
        assert "Wealth: well-kept" in result
        assert "Facial Signal: asymmetrical" in result

    def test_axes_in_insertion_order(self) -> None:
        """Axes appear in the order they were inserted into the profile dict.

        CharacterProfileBuilder inserts keys in active_axes order (from
        world.json), so the summary reflects the world-configured axis
        sequence without any additional sorting in _build_profile_summary.
        """
        result = _build_profile_summary(self._full_profile())
        demeanor_pos = result.index("Demeanor")
        health_pos = result.index("Health")
        physique_pos = result.index("Physique")
        wealth_pos = result.index("Wealth")
        facial_pos = result.index("Facial Signal")
        assert demeanor_pos < health_pos < physique_pos < wealth_pos < facial_pos

    def test_channel_not_in_summary(self) -> None:
        """The 'channel' field must not appear as an axis line in the summary.

        channel is handled by the separate {{channel}} placeholder in the
        template; including it here would duplicate it in the rendered prompt.
        """
        result = _build_profile_summary(self._full_profile())
        # "Channel:" would indicate the field leaked into the summary as an
        # axis line — that is the bug this test guards against.
        assert "Channel:" not in result

    def test_score_precision_two_decimal_places(self) -> None:
        """Scores are formatted to two decimal places to suppress float noise.

        The axis engine accumulates small floating-point errors across
        interactions (e.g. "0.06875230399999996").  Formatting to two
        decimal places produces a clean "0.07" that reads naturally in a
        prompt block without losing meaningful axis magnitude information.
        """
        profile = {
            "character_name": "Mira",
            "demeanor_label": "timid",
            "demeanor_score": 0.06875230399999996,
        }
        result = _build_profile_summary(profile)
        # Full-precision float must not appear — it clutters the prompt.
        assert "0.06875" not in result
        # Two-decimal form must be present — conveys the axis magnitude clearly.
        assert "0.07" in result

    def test_underscore_axis_name_formatted_as_title_case(self) -> None:
        """Axis names with underscores are rendered as space-separated Title Case.

        "facial_signal" → "Facial Signal" reads naturally in a character
        sheet block.  The LLM does not need to know the internal key name.
        """
        profile = {
            "character_name": "Mira",
            "facial_signal_label": "asymmetrical",
            "facial_signal_score": 0.5,
        }
        result = _build_profile_summary(profile)
        # Title-cased display name must be present.
        assert "Facial Signal: asymmetrical" in result
        # Raw snake_case key must not appear in the output.
        assert "facial_signal" not in result

    def test_missing_score_defaults_to_zero(self) -> None:
        """A _label key with no matching _score defaults the score to 0.00."""
        profile = {
            "character_name": "Mira",
            "demeanor_label": "timid",
            # demeanor_score deliberately absent
        }
        result = _build_profile_summary(profile)
        assert "Demeanor: timid (0.00)" in result

    def test_empty_axis_profile_returns_character_name_only(self) -> None:
        """A profile with no axis data produces a single character name line."""
        result = _build_profile_summary({"character_name": "Mira"})
        assert "Character: Mira" in result
        # Should be exactly one line — no axis entries appended.
        assert result.count("\n") == 0

    def test_missing_character_name_uses_unknown_fallback(self) -> None:
        """If character_name is absent, 'unknown' is used as a safe default."""
        result = _build_profile_summary({"demeanor_label": "timid", "demeanor_score": 0.5})
        assert "Character: unknown" in result


# ── TestExtractSnapshot ───────────────────────────────────────────────────────


class TestExtractSnapshot:
    """Unit tests for the _extract_snapshot module-level helper.

    These tests exercise the snapshot builder independently of the full
    translate() pipeline so that snapshot logic failures produce clear,
    targeted failures rather than burying the root cause in service-level
    noise.
    """

    def test_empty_profile_returns_empty_dict(self) -> None:
        """An empty profile dict produces an empty snapshot."""
        assert _extract_snapshot({}) == {}

    def test_score_and_label_grouped_by_axis(self) -> None:
        """Keys ending in _score and _label are grouped under the axis name."""
        profile = {
            "demeanor_score": 0.87,
            "demeanor_label": "proud",
        }
        result = _extract_snapshot(profile)
        assert result == {"demeanor": {"score": 0.87, "label": "proud"}}

    def test_multiple_axes_extracted(self) -> None:
        """Multiple axes each produce their own nested entry."""
        profile = {
            "demeanor_score": 0.87,
            "demeanor_label": "proud",
            "health_score": 0.72,
            "health_label": "scarred",
        }
        result = _extract_snapshot(profile)
        assert result["demeanor"] == {"score": 0.87, "label": "proud"}
        assert result["health"] == {"score": 0.72, "label": "scarred"}

    def test_non_axis_keys_ignored(self) -> None:
        """Keys like character_name, channel, and profile_summary are silently ignored."""
        profile = {
            "character_name": "Mira",
            "channel": "say",
            "profile_summary": "  Character: Mira\n  Demeanor: proud (0.87)",
            "demeanor_score": 0.87,
            "demeanor_label": "proud",
        }
        result = _extract_snapshot(profile)
        # Only the demeanor axis should appear; all non-axis keys must be absent.
        assert set(result.keys()) == {"demeanor"}

    def test_score_only_axis_produces_partial_entry(self) -> None:
        """A profile with _score but no matching _label still produces an entry."""
        profile = {"wealth_score": 0.45}
        result = _extract_snapshot(profile)
        # Entry exists but has only the score field, not the label.
        assert result == {"wealth": {"score": 0.45}}

    def test_label_only_axis_produces_partial_entry(self) -> None:
        """A profile with _label but no matching _score still produces an entry."""
        profile = {"wealth_label": "struggling"}
        result = _extract_snapshot(profile)
        assert result == {"wealth": {"label": "struggling"}}


# ── TestEmitTranslationEvent ──────────────────────────────────────────────────


class TestEmitTranslationEvent:
    """Unit tests for the _emit_translation_event module-level helper.

    These tests exercise the helper directly, independently of translate(),
    to confirm the data payload shape and error-suppression contract.
    """

    def _base_profile(self) -> dict:
        """Return a minimal profile dict with demeanor axis data."""
        return {
            "character_name": "Mira",
            "channel": "say",
            "demeanor_score": 0.87,
            "demeanor_label": "proud",
        }

    def test_calls_append_fn_once(self) -> None:
        """_emit_translation_event calls the append_fn exactly once."""
        mock_append = MagicMock(return_value="deadbeef" * 4)
        _emit_translation_event(
            mock_append,
            world_id="test_world",
            status="success",
            character_name="Mira",
            channel="say",
            ooc_message="give me the ledger",
            ic_output="Hand over the ledger.",
            profile=self._base_profile(),
            ipc_hash=None,
        )
        mock_append.assert_called_once()

    def test_passes_correct_event_type(self) -> None:
        """The append_fn is called with event_type='chat.translation'."""
        mock_append = MagicMock(return_value="a" * 32)
        _emit_translation_event(
            mock_append,
            world_id="test_world",
            status="success",
            character_name="Mira",
            channel="say",
            ooc_message="hello",
            ic_output="Greetings.",
            profile=self._base_profile(),
            ipc_hash=None,
        )
        kwargs = mock_append.call_args.kwargs
        assert kwargs["event_type"] == "chat.translation"

    def test_meta_phase_pre_axis_engine_when_ipc_hash_none(self) -> None:
        """meta.phase is 'pre_axis_engine' when ipc_hash is None.

        This marker distinguishes null-hash-era events from post-axis-engine
        events during ledger replay.
        """
        mock_append = MagicMock(return_value="a" * 32)
        _emit_translation_event(
            mock_append,
            world_id="test_world",
            status="success",
            character_name="Mira",
            channel="say",
            ooc_message="hello",
            ic_output="Greetings.",
            profile=self._base_profile(),
            ipc_hash=None,
        )
        kwargs = mock_append.call_args.kwargs
        assert kwargs["meta"] == {"phase": "pre_axis_engine"}

    def test_meta_empty_when_ipc_hash_provided(self) -> None:
        """meta is an empty dict when ipc_hash is provided.

        When the axis engine runs and produces a real ipc_hash, the hash
        itself serves as the provenance signal — no meta phase annotation
        is needed.
        """
        mock_append = MagicMock(return_value="a" * 32)
        _emit_translation_event(
            mock_append,
            world_id="test_world",
            status="success",
            character_name="Mira",
            channel="say",
            ooc_message="hello",
            ic_output="Greetings.",
            profile=self._base_profile(),
            ipc_hash="a" * 64,
        )
        kwargs = mock_append.call_args.kwargs
        assert kwargs["meta"] == {}

    def test_data_payload_shape(self) -> None:
        """The data dict contains all required fields with correct values."""
        mock_append = MagicMock(return_value="a" * 32)
        _emit_translation_event(
            mock_append,
            world_id="test_world",
            status="success",
            character_name="Mira",
            channel="yell",
            ooc_message="back off!",
            ic_output="Step away.",
            profile=self._base_profile(),
            ipc_hash=None,
        )
        data = mock_append.call_args.kwargs["data"]
        assert data["status"] == "success"
        assert data["character_name"] == "Mira"
        assert data["channel"] == "yell"
        assert data["ooc_input"] == "back off!"
        assert data["ic_output"] == "Step away."
        assert "axis_snapshot" in data

    def test_axis_snapshot_in_data(self) -> None:
        """data.axis_snapshot contains the character's axis scores and labels."""
        mock_append = MagicMock(return_value="a" * 32)
        _emit_translation_event(
            mock_append,
            world_id="test_world",
            status="success",
            character_name="Mira",
            channel="say",
            ooc_message="hello",
            ic_output="Greetings.",
            profile=self._base_profile(),
            ipc_hash=None,
        )
        snapshot = mock_append.call_args.kwargs["data"]["axis_snapshot"]
        assert snapshot["demeanor"]["score"] == 0.87
        assert snapshot["demeanor"]["label"] == "proud"

    def test_ic_output_none_on_fallback(self) -> None:
        """data.ic_output is None when status indicates a fallback."""
        mock_append = MagicMock(return_value="a" * 32)
        _emit_translation_event(
            mock_append,
            world_id="test_world",
            status="fallback.api_error",
            character_name="Mira",
            channel="say",
            ooc_message="hello",
            ic_output=None,
            profile=self._base_profile(),
            ipc_hash=None,
        )
        data = mock_append.call_args.kwargs["data"]
        assert data["ic_output"] is None

    def test_never_raises_on_append_fn_exception(self) -> None:
        """_emit_translation_event is fire-and-forget: exceptions are swallowed.

        Ledger write failures must not propagate to the game layer — the
        interaction must complete even if the audit record is lost.
        """
        exploding_append = MagicMock(side_effect=OSError("disk full"))
        # Must not raise — ledger failures are non-fatal.
        _emit_translation_event(
            exploding_append,
            world_id="test_world",
            status="success",
            character_name="Mira",
            channel="say",
            ooc_message="hello",
            ic_output="Greetings.",
            profile=self._base_profile(),
            ipc_hash=None,
        )
        # Reaching this line confirms the exception was suppressed correctly.


# ── TestConstructorValidation ─────────────────────────────────────────────────


class TestConstructorValidation:
    def test_empty_world_id_raises(self, tmp_path):
        """An empty world_id raises ValueError at construction time."""
        cfg = _make_config()
        with pytest.raises(ValueError, match="world_id"):
            OOCToICTranslationService(world_id="", config=cfg, world_root=tmp_path)


# ── TestTranslateSuccess ──────────────────────────────────────────────────────


class TestTranslateSuccess:
    def test_returns_ic_text_on_success(self, tmp_path):
        """translate() returns the validated IC text from the renderer."""
        svc = _make_service(tmp_path)
        with (
            patch.object(
                svc._profile_builder,
                "build",
                return_value={
                    "character_name": "Mira",
                    "demeanor_label": "proud",
                    "demeanor_score": 0.87,
                },
            ),
            patch.object(svc._renderer, "render", return_value="Hand over the ledger."),
        ):
            result = svc.translate("Mira", "give me the ledger")
        assert result == "Hand over the ledger."

    def test_channel_injected_into_profile(self, tmp_path):
        """The channel value appears in the rendered system prompt."""
        svc = _make_service(tmp_path)
        captured = {}

        def fake_render(system_prompt, user_message):
            captured["prompt"] = system_prompt
            return "IC text"

        with (
            patch.object(
                svc._profile_builder,
                "build",
                return_value={"character_name": "Mira", "demeanor_label": "proud"},
            ),
            patch.object(svc._renderer, "render", side_effect=fake_render),
        ):
            svc.translate("Mira", "hello", channel="yell")

        # The {{channel}} placeholder in the template resolves to "yell".
        assert "yell" in captured["prompt"]


# ── TestTranslateFallback ─────────────────────────────────────────────────────


class TestTranslateFallback:
    def test_returns_none_when_profile_build_fails(self, tmp_path):
        """translate() returns None when the character profile cannot be resolved."""
        svc = _make_service(tmp_path)
        with patch.object(svc._profile_builder, "build", return_value=None):
            assert svc.translate("Unknown", "hello") is None

    def test_returns_none_when_renderer_fails(self, tmp_path):
        """translate() returns None when the Ollama renderer returns None."""
        svc = _make_service(tmp_path)
        with (
            patch.object(
                svc._profile_builder,
                "build",
                return_value={"character_name": "Mira", "demeanor_label": "proud"},
            ),
            patch.object(svc._renderer, "render", return_value=None),
        ):
            assert svc.translate("Mira", "hello") is None

    def test_returns_none_when_validation_fails(self, tmp_path):
        """translate() returns None when the validator rejects the raw output."""
        svc = _make_service(tmp_path)
        with (
            patch.object(
                svc._profile_builder,
                "build",
                return_value={"character_name": "Mira", "demeanor_label": "proud"},
            ),
            patch.object(svc._renderer, "render", return_value="PASSTHROUGH"),
            patch.object(svc._validator, "validate", return_value=None),
        ):
            assert svc.translate("Mira", "some command") is None

    def test_returns_none_when_disabled(self, tmp_path):
        """translate() returns None immediately when config.enabled is False."""
        cfg = _make_config(enabled=False)
        svc = OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)
        # Even with a working profile/renderer it returns None immediately.
        assert svc.translate("Mira", "hello") is None


# ── TestDeterministicMode ─────────────────────────────────────────────────────


class TestDeterministicMode:
    """Deterministic mode arms the renderer when ipc_hash is provided.

    The axis engine (core/engine.py) computes the ipc_hash and passes it
    to translate().  When config.deterministic=True and the hash is not None,
    the renderer is armed with a seed derived from the hash, ensuring that
    identical game state + OOC input always produces identical IC output.
    """

    def test_deterministic_not_armed_when_ipc_hash_is_none(self, tmp_path):
        """set_deterministic is not called when ipc_hash is None.

        ipc_hash is None when the axis engine did not run (solo-room
        interaction, engine disabled, or engine failure).  In that case
        the renderer uses the configured temperature regardless of
        config.deterministic.
        """
        svc = _make_service(tmp_path, deterministic=True)
        with (
            patch.object(
                svc._profile_builder,
                "build",
                return_value={"character_name": "Mira", "demeanor_label": "proud"},
            ),
            patch.object(svc._renderer, "render", return_value="IC text"),
            patch.object(svc._renderer, "set_deterministic") as mock_det,
        ):
            svc.translate("Mira", "hello", ipc_hash=None)
        mock_det.assert_not_called()

    def test_deterministic_armed_when_ipc_hash_provided(self, tmp_path):
        """set_deterministic is called with the correct seed when ipc_hash is set."""
        svc = _make_service(tmp_path, deterministic=True)
        ipc_hash = "a3f91c9e4b12f2d8baf0000000000000"  # 32 hex chars
        expected_seed = int(ipc_hash[:16], 16)
        with (
            patch.object(
                svc._profile_builder,
                "build",
                return_value={"character_name": "Mira", "demeanor_label": "proud"},
            ),
            patch.object(svc._renderer, "render", return_value="IC text"),
            patch.object(svc._renderer, "set_deterministic") as mock_det,
        ):
            svc.translate("Mira", "hello", ipc_hash=ipc_hash)
        mock_det.assert_called_once_with(expected_seed)

    def test_deterministic_not_armed_when_config_false(self, tmp_path):
        """ipc_hash is ignored when config.deterministic is False.

        The caller may always pass an ipc_hash for ledger linkage purposes.
        Deterministic mode is opt-in via world.json — the hash alone is not
        sufficient to activate it.
        """
        svc = _make_service(tmp_path, deterministic=False)
        with (
            patch.object(
                svc._profile_builder,
                "build",
                return_value={"character_name": "Mira", "demeanor_label": "proud"},
            ),
            patch.object(svc._renderer, "render", return_value="IC text"),
            patch.object(svc._renderer, "set_deterministic") as mock_det,
        ):
            svc.translate("Mira", "hello", ipc_hash="a3f91c9e4b12f2d8")
        mock_det.assert_not_called()


# ── TestPromptTemplate ────────────────────────────────────────────────────────


class TestPromptTemplate:
    def test_missing_template_uses_fallback(self, tmp_path):
        """If ic_prompt.txt does not exist, the built-in fallback is used."""
        cfg = _make_config(
            enabled=True,
            prompt_template_path="policies/nonexistent.txt",
        )
        # Should not raise — the service degrades gracefully with a fallback.
        svc = OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)
        assert svc._prompt_template  # fallback template is non-empty

    def test_custom_template_loaded(self, tmp_path):
        """A world-specific ic_prompt.txt is loaded and stored verbatim."""
        prompt_file = tmp_path / "policies" / "ic_prompt.txt"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text("Custom template: {{ooc_message}}")
        cfg = _make_config(enabled=True, prompt_template_path="policies/ic_prompt.txt")
        svc = OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)
        assert "Custom template" in svc._prompt_template


# ── TestSystemPromptRendering ─────────────────────────────────────────────────


class TestSystemPromptRendering:
    def test_placeholders_substituted(self, tmp_path):
        """_render_system_prompt substitutes {{key}} placeholders from the profile."""
        svc = _make_service(tmp_path)
        profile = {"character_name": "Mira", "demeanor_label": "proud", "channel": "say"}
        rendered = svc._render_system_prompt(profile, "give me bread")
        assert "proud" in rendered
        assert "give me bread" in rendered

    def test_unknown_placeholder_left_as_is(self, tmp_path):
        """Placeholders with no matching profile key are left unchanged.

        This makes unresolved placeholders visible during prompt development
        rather than silently replaced with empty strings.
        """
        svc = _make_service(tmp_path)
        svc._prompt_template = "{{unknown_key}} {{ooc_message}}"
        rendered = svc._render_system_prompt({}, "hello")
        assert "{{unknown_key}}" in rendered
        assert "hello" in rendered

    def test_profile_summary_placeholder_resolved_by_translate(self, tmp_path):
        """The {{profile_summary}} placeholder must not survive into the rendered prompt.

        This is the primary guard test for the bug fixed in 0.4.1.

        The bug: ``ic_prompt.txt`` used ``{{profile_summary}}`` as a single
        aggregated placeholder for the character's axis state, but no code
        built or injected a ``profile_summary`` key into the profile dict.
        As a result, ``{{profile_summary}}`` was forwarded to Ollama as a
        literal unresolved string and the LLM was blind to all character
        axis data.

        The fix: ``translate()`` now calls ``_build_profile_summary(profile)``
        and injects the result as ``profile["profile_summary"]`` before
        ``_render_system_prompt`` runs, ensuring the placeholder resolves
        to a formatted character profile block.
        """
        svc = _make_service_with_profile_summary_template(tmp_path)
        captured: dict = {}

        def fake_render(system_prompt: str, user_message: str) -> str:
            # Capture the exact string sent to the renderer so we can
            # assert that {{profile_summary}} was resolved before this point.
            captured["prompt"] = system_prompt
            return "IC text"

        profile = {
            "character_name": "Mira",
            "demeanor_label": "proud",
            "demeanor_score": 0.87,
        }
        with (
            patch.object(svc._profile_builder, "build", return_value=profile),
            patch.object(svc._renderer, "render", side_effect=fake_render),
        ):
            svc.translate("Mira", "hello", channel="say")

        # The literal placeholder must not appear in the string passed to Ollama.
        assert "{{profile_summary}}" not in captured["prompt"]

        # The character name must appear — confirms _build_profile_summary ran
        # and its output was substituted into the prompt.
        assert "Mira" in captured["prompt"]

    def test_profile_summary_contains_axis_data_in_rendered_prompt(self, tmp_path):
        """Axis labels from the profile appear in the rendered system prompt.

        Confirms end-to-end that the character's axis state (not just the
        name) flows through _build_profile_summary into the prompt sent to
        the renderer.
        """
        svc = _make_service_with_profile_summary_template(tmp_path)
        captured: dict = {}

        def fake_render(system_prompt: str, user_message: str) -> str:
            captured["prompt"] = system_prompt
            return "IC text"

        profile = {
            "character_name": "Ddishfew Withnop",
            "demeanor_label": "timid",
            "demeanor_score": 0.07,
            "health_label": "scarred",
            "health_score": 0.65,
        }
        with (
            patch.object(svc._profile_builder, "build", return_value=profile),
            patch.object(svc._renderer, "render", side_effect=fake_render),
        ):
            svc.translate("Ddishfew Withnop", "I need work", channel="say")

        # Both axis labels must be present in the rendered prompt — the LLM
        # must see the character's mechanical state, not a placeholder string.
        assert "timid" in captured["prompt"]
        assert "scarred" in captured["prompt"]


# ── TestLedgerIntegration ─────────────────────────────────────────────────────


class TestLedgerIntegration:
    """Integration-level tests confirming translate() wires to the ledger.

    These tests patch the module-level ``_ledger_append`` name in
    ``mud_server.translation.service`` so that no real JSONL file is written.
    Patching the module-level name (rather than the class internals) mirrors
    exactly how production code resolves the function at call time, and means
    tests remain correct if the call site is refactored.

    All scenarios use a profile that includes axis data so that
    ``axis_snapshot`` is non-empty — this exercises the full happy path
    through ``_extract_snapshot``.
    """

    #: Module path of the name to patch.
    _PATCH_TARGET = "mud_server.translation.service._ledger_append"

    #: Reusable profile with demeanor + health axis data.
    _PROFILE = {
        "character_name": "Mira",
        "demeanor_score": 0.87,
        "demeanor_label": "proud",
        "health_score": 0.72,
        "health_label": "scarred",
    }

    def test_success_emits_translation_event(self, tmp_path: Path) -> None:
        """A successful translation emits one 'success' ledger event."""
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value="Hand over the ledger."),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            result = svc.translate("Mira", "give me the ledger")

        assert result == "Hand over the ledger."
        mock_append.assert_called_once()
        data = mock_append.call_args.kwargs["data"]
        assert data["status"] == "success"
        assert data["ic_output"] == "Hand over the ledger."
        assert data["ooc_input"] == "give me the ledger"

    def test_api_error_emits_fallback_event(self, tmp_path: Path) -> None:
        """An Ollama API failure emits one 'fallback.api_error' ledger event."""
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value=None),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            result = svc.translate("Mira", "hello")

        assert result is None
        mock_append.assert_called_once()
        data = mock_append.call_args.kwargs["data"]
        assert data["status"] == "fallback.api_error"
        assert data["ic_output"] is None

    def test_validation_failed_emits_fallback_event(self, tmp_path: Path) -> None:
        """A validation failure emits one 'fallback.validation_failed' event."""
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value="PASSTHROUGH"),
            patch.object(svc._validator, "validate", return_value=None),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            result = svc.translate("Mira", "some command")

        assert result is None
        mock_append.assert_called_once()
        data = mock_append.call_args.kwargs["data"]
        assert data["status"] == "fallback.validation_failed"
        assert data["ic_output"] is None

    def test_no_event_when_profile_missing(self, tmp_path: Path) -> None:
        """No ledger event is emitted when the character profile cannot be resolved.

        There is no character data to record, so emitting a partial event
        would be misleading.  The caller falls back to the OOC message
        without any ledger write.
        """
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=None),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            result = svc.translate("Unknown", "hello")

        assert result is None
        mock_append.assert_not_called()

    def test_no_event_when_disabled(self, tmp_path: Path) -> None:
        """No ledger event is emitted when the translation service is disabled.

        When ``config.enabled=False``, translate() returns None immediately
        before attempting a profile lookup or any other work.
        """
        cfg = _make_config(enabled=False)
        svc = OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)
        with patch(self._PATCH_TARGET) as mock_append:
            result = svc.translate("Mira", "hello")

        assert result is None
        mock_append.assert_not_called()

    def test_ipc_hash_null_meta_pre_axis_engine(self, tmp_path: Path) -> None:
        """meta.phase is 'pre_axis_engine' when ipc_hash is None.

        Covers solo-room interactions, axis engine disabled, and axis engine
        failure paths — all of which produce a None ipc_hash.
        """
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value="IC text"),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            svc.translate("Mira", "hello", ipc_hash=None)

        meta = mock_append.call_args.kwargs["meta"]
        assert meta == {"phase": "pre_axis_engine"}

    def test_ipc_hash_present_meta_empty(self, tmp_path: Path) -> None:
        """meta is empty when the axis engine provides a real ipc_hash.

        The hash itself serves as the provenance signal linking this event
        to the preceding chat.mechanical_resolution event in the ledger.
        """
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value="IC text"),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            svc.translate("Mira", "hello", ipc_hash="a" * 64)

        meta = mock_append.call_args.kwargs["meta"]
        assert meta == {}

    def test_ledger_failure_does_not_break_translate(self, tmp_path: Path) -> None:
        """A ledger write failure does not prevent translate() from returning IC text.

        The ledger is fire-and-forget: if the write fails, the game
        interaction completes normally and only the audit record is lost.
        This test verifies the non-fatal contract end-to-end through the
        full translate() call stack.
        """
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value="Hand over the ledger."),
            patch(self._PATCH_TARGET, side_effect=OSError("disk full")),
        ):
            # Must not raise — the game interaction must complete.
            result = svc.translate("Mira", "give me the ledger")

        assert result == "Hand over the ledger."

    def test_axis_snapshot_contains_profile_axes(self, tmp_path: Path) -> None:
        """data.axis_snapshot contains the profile's axis fields at translate time.

        The snapshot is taken before any post-translation axis mutations,
        representing the character's state as of this specific interaction —
        the exact context the LLM used to generate the IC output.
        """
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value="The ledger belongs to no one."),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            svc.translate("Mira", "whose ledger is it?")

        snapshot = mock_append.call_args.kwargs["data"]["axis_snapshot"]
        assert snapshot["demeanor"]["score"] == 0.87
        assert snapshot["demeanor"]["label"] == "proud"
        assert snapshot["health"]["score"] == 0.72
        assert snapshot["health"]["label"] == "scarred"

    def test_channel_recorded_in_event_data(self, tmp_path: Path) -> None:
        """The chat channel is recorded in the ledger event data payload."""
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value="IC text"),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            svc.translate("Mira", "hello", channel="whisper")

        data = mock_append.call_args.kwargs["data"]
        assert data["channel"] == "whisper"

    def test_event_emitted_once_per_translate_call(self, tmp_path: Path) -> None:
        """Each translate() call emits exactly one ledger event, never more."""
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value="IC text"),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            svc.translate("Mira", "first")
            svc.translate("Mira", "second")

        # Two translate() calls → two ledger writes, one per call.
        assert mock_append.call_count == 2


# ── TestTranslateWithAxes ─────────────────────────────────────────────────────


class TestTranslateWithAxes:
    """Unit tests for OOCToICTranslationService.translate_with_axes().

    ``translate_with_axes`` is the lab entry point: it accepts raw axis
    values instead of performing a character DB lookup, then runs the same
    render/validate pipeline as ``translate()``.

    All Ollama network calls are patched at the ``OllamaRenderer`` class
    level so that these tests never make real HTTP requests.
    """

    _AXES = {
        "demeanor": {"label": "timid", "score": 0.07},
        "health": {"label": "scarred", "score": 0.65},
        "physique": {"label": "lean", "score": 0.40},
    }

    def _make_svc(self, tmp_path: Path, *, active_axes=None) -> OOCToICTranslationService:
        """Build a service with a profile_summary template and explicit active_axes."""
        prompt_file = tmp_path / "policies" / "ic_prompt.txt"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(
            "PROFILE:\n{{profile_summary}}\nCHANNEL: {{channel}}\nMSG: {{ooc_message}}"
        )
        axes = active_axes if active_axes is not None else ["demeanor", "health"]
        cfg = _make_config(
            enabled=True,
            active_axes=axes,
            prompt_template_path="policies/ic_prompt.txt",
        )
        return OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)

    # ── Return type and basic structure ───────────────────────────────────────

    def test_returns_lab_translate_result(self, tmp_path: Path) -> None:
        """translate_with_axes always returns a LabTranslateResult."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "I must leave now."
            result = svc.translate_with_axes(self._AXES, "I need to go.")
        assert isinstance(result, LabTranslateResult)

    def test_config_property_returns_config(self, tmp_path: Path) -> None:
        """The config property exposes the frozen TranslationLayerConfig."""
        svc = self._make_svc(tmp_path)
        assert svc.config is svc._config

    # ── Active-axes filtering ─────────────────────────────────────────────────

    def test_axes_filtered_to_active_axes(self, tmp_path: Path) -> None:
        """Axes not in active_axes are silently excluded from the profile."""
        svc = self._make_svc(tmp_path, active_axes=["demeanor"])
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC line."
            result = svc.translate_with_axes(self._AXES, "ooc")

        # profile_summary should only mention demeanor, not health or physique
        assert "Demeanor" in result.profile_summary
        assert "Health" not in result.profile_summary
        assert "Physique" not in result.profile_summary

    def test_unknown_axes_silently_ignored(self, tmp_path: Path) -> None:
        """Axis names not in active_axes (including unknown ones) produce no error."""
        svc = self._make_svc(tmp_path, active_axes=["demeanor"])
        axes_with_extras = {
            **self._AXES,
            "unknown_axis": {"label": "foo", "score": 0.5},
        }
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC line."
            result = svc.translate_with_axes(axes_with_extras, "ooc")
        assert result.status == "success"

    # ── Profile and prompt construction ──────────────────────────────────────

    def test_profile_summary_uses_server_canonical_format(self, tmp_path: Path) -> None:
        """profile_summary uses Title Case axis names and 2dp scores (server format)."""
        svc = self._make_svc(tmp_path, active_axes=["demeanor", "health"])
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC line."
            result = svc.translate_with_axes(self._AXES, "ooc", character_name="Mira")

        assert "Character: Mira" in result.profile_summary
        assert "Demeanor: timid (0.07)" in result.profile_summary
        assert "Health: scarred (0.65)" in result.profile_summary

    def test_rendered_prompt_contains_profile_summary(self, tmp_path: Path) -> None:
        """The rendered_prompt has the profile_summary block substituted in."""
        svc = self._make_svc(tmp_path, active_axes=["demeanor"])
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC line."
            result = svc.translate_with_axes(self._AXES, "my message")

        assert "PROFILE:" in result.rendered_prompt
        assert "Demeanor" in result.rendered_prompt
        assert "{{profile_summary}}" not in result.rendered_prompt

    def test_channel_injected_into_rendered_prompt(self, tmp_path: Path) -> None:
        """The channel value is substituted into the rendered prompt."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC line."
            result = svc.translate_with_axes(self._AXES, "ooc", channel="yell")

        assert "CHANNEL: yell" in result.rendered_prompt

    # ── Per-call renderer (state isolation) ──────────────────────────────────

    def test_creates_fresh_renderer_per_call(self, tmp_path: Path) -> None:
        """A new OllamaRenderer is constructed for each translate_with_axes call."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC."
            svc.translate_with_axes(self._AXES, "first")
            svc.translate_with_axes(self._AXES, "second")

        assert MockRenderer.call_count == 2

    def test_renderer_receives_config_values(self, tmp_path: Path) -> None:
        """The fresh renderer is initialised with the world's api_endpoint and model."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC."
            svc.translate_with_axes(self._AXES, "ooc")

        call_kwargs = MockRenderer.call_args.kwargs
        assert call_kwargs["api_endpoint"] == svc.config.api_endpoint
        assert call_kwargs["model"] == svc.config.model
        assert call_kwargs["timeout_seconds"] == svc.config.timeout_seconds

    # ── Seed / deterministic mode ─────────────────────────────────────────────

    def test_seed_none_does_not_call_set_deterministic(self, tmp_path: Path) -> None:
        """When seed is None, set_deterministic is never called on the renderer."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC."
            svc.translate_with_axes(self._AXES, "ooc", seed=None)

        MockRenderer.return_value.set_deterministic.assert_not_called()

    def test_seed_value_arms_deterministic_mode(self, tmp_path: Path) -> None:
        """When seed is provided, set_deterministic is called with that seed."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC."
            svc.translate_with_axes(self._AXES, "ooc", seed=42)

        MockRenderer.return_value.set_deterministic.assert_called_once_with(42)

    def test_game_renderer_untouched_by_lab_call(self, tmp_path: Path) -> None:
        """translate_with_axes never calls set_deterministic on the service's own renderer."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC."
            with patch.object(svc._renderer, "set_deterministic") as mock_sd:
                svc.translate_with_axes(self._AXES, "ooc", seed=99)

        # The service's own renderer must be completely untouched
        mock_sd.assert_not_called()

    # ── Status outcomes ───────────────────────────────────────────────────────

    def test_success_returns_ic_text_and_status(self, tmp_path: Path) -> None:
        """On success, ic_text is set and status is 'success'."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "I must leave."
            result = svc.translate_with_axes(self._AXES, "I need to go.")

        assert result.status == "success"
        assert result.ic_text == "I must leave."

    def test_api_error_returns_fallback_status(self, tmp_path: Path) -> None:
        """When the renderer returns None, status is 'fallback.api_error'."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = None
            result = svc.translate_with_axes(self._AXES, "ooc")

        assert result.status == "fallback.api_error"
        assert result.ic_text is None

    def test_api_error_still_returns_profile_summary_and_prompt(self, tmp_path: Path) -> None:
        """Even on api_error, profile_summary and rendered_prompt are populated."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = None
            result = svc.translate_with_axes(self._AXES, "ooc")

        assert result.profile_summary != ""
        assert result.rendered_prompt != ""

    def test_validation_failed_returns_fallback_status(self, tmp_path: Path) -> None:
        """When the validator rejects output, status is 'fallback.validation_failed'."""
        svc = self._make_svc(tmp_path)
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "raw output"
            with patch.object(svc._validator, "validate", return_value=None):
                result = svc.translate_with_axes(self._AXES, "ooc")

        assert result.status == "fallback.validation_failed"
        assert result.ic_text is None

    def test_no_ledger_event_emitted(self, tmp_path: Path) -> None:
        """translate_with_axes never writes to the ledger — lab calls are not game events."""
        svc = self._make_svc(tmp_path)
        ledger_target = "mud_server.translation.service._ledger_append"
        with patch("mud_server.translation.service.OllamaRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = "IC."
            with patch(ledger_target) as mock_ledger:
                svc.translate_with_axes(self._AXES, "ooc")

        mock_ledger.assert_not_called()
