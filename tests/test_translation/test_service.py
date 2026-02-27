"""Unit tests for OOCToICTranslationService."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mud_server.translation.config import TranslationLayerConfig
from mud_server.translation.service import (
    OOCToICTranslationService,
    _emit_translation_event,
    _extract_snapshot,
)

WORLD_ID = "test_world"


def _make_config(*, enabled=True, deterministic=False, **kwargs) -> TranslationLayerConfig:
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
    """Build a service with a minimal ic_prompt.txt in tmp_path."""
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


class TestConstructorValidation:
    def test_empty_world_id_raises(self, tmp_path):
        cfg = _make_config()
        with pytest.raises(ValueError, match="world_id"):
            OOCToICTranslationService(world_id="", config=cfg, world_root=tmp_path)


class TestTranslateSuccess:
    def test_returns_ic_text_on_success(self, tmp_path):
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

        # The rendered system prompt should contain the channel value
        assert "yell" in captured["prompt"]


class TestTranslateFallback:
    def test_returns_none_when_profile_build_fails(self, tmp_path):
        svc = _make_service(tmp_path)
        with patch.object(svc._profile_builder, "build", return_value=None):
            assert svc.translate("Unknown", "hello") is None

    def test_returns_none_when_renderer_fails(self, tmp_path):
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
        cfg = _make_config(enabled=False)
        svc = OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)
        # Even with a working profile/renderer it returns None immediately
        assert svc.translate("Mira", "hello") is None


class TestDeterministicMode:
    """Deterministic mode arms the renderer when ipc_hash is provided.

    IPC hash sourcing (FUTURE — axis engine integration):
    These tests verify the wiring from ipc_hash → renderer.set_deterministic.
    Currently ipc_hash will always be None in production because the axis
    engine is not yet integrated.  Once it is, the hash will be passed
    through and these code paths will activate in live gameplay.
    """

    def test_deterministic_not_armed_when_ipc_hash_is_none(self, tmp_path):
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
            # No ipc_hash provided — deterministic mode must NOT be armed
            svc.translate("Mira", "hello", ipc_hash=None)
        mock_det.assert_not_called()

    def test_deterministic_armed_when_ipc_hash_provided(self, tmp_path):
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
        """Config deterministic=False means ipc_hash is ignored even if provided."""
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


class TestPromptTemplate:
    def test_missing_template_uses_fallback(self, tmp_path):
        """If ic_prompt.txt does not exist, a built-in fallback is used."""
        cfg = _make_config(
            enabled=True,
            prompt_template_path="policies/nonexistent.txt",
        )
        # Should not raise; service uses built-in fallback
        svc = OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)
        assert svc._prompt_template  # fallback template is non-empty

    def test_custom_template_loaded(self, tmp_path):
        prompt_file = tmp_path / "policies" / "ic_prompt.txt"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text("Custom template: {{ooc_message}}")
        cfg = _make_config(enabled=True, prompt_template_path="policies/ic_prompt.txt")
        svc = OOCToICTranslationService(world_id=WORLD_ID, config=cfg, world_root=tmp_path)
        assert "Custom template" in svc._prompt_template


class TestSystemPromptRendering:
    def test_placeholders_substituted(self, tmp_path):
        svc = _make_service(tmp_path)
        profile = {"character_name": "Mira", "demeanor_label": "proud", "channel": "say"}
        rendered = svc._render_system_prompt(profile, "give me bread")
        assert "proud" in rendered
        assert "give me bread" in rendered

    def test_unknown_placeholder_left_as_is(self, tmp_path):
        """Placeholders with no matching profile key are left unchanged."""
        svc = _make_service(tmp_path)
        svc._prompt_template = "{{unknown_key}} {{ooc_message}}"
        rendered = svc._render_system_prompt({}, "hello")
        assert "{{unknown_key}}" in rendered
        assert "hello" in rendered


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
        """Keys like character_name and channel are silently ignored."""
        profile = {
            "character_name": "Mira",
            "channel": "say",
            "demeanor_score": 0.87,
            "demeanor_label": "proud",
        }
        result = _extract_snapshot(profile)
        # Only the demeanor axis should appear; non-axis keys must be absent.
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
        """meta.phase is 'pre_axis_engine' when ipc_hash is None."""
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
        """meta is an empty dict (not pre_axis_engine) when ipc_hash is provided."""
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
        # When the axis engine provides an ipc_hash, meta is empty — the
        # ipc_hash itself serves as the provenance signal.
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
        """_emit_translation_event is fire-and-forget: exceptions are swallowed."""
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
        # If we reach this line, the exception was suppressed correctly.


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
        """meta.phase is 'pre_axis_engine' on every event while ipc_hash is None.

        This covers all three status outcomes — pre-axis-engine metadata
        is determined solely by ipc_hash, not by the translation result.
        """
        svc = _make_service(tmp_path)
        with (
            patch.object(svc._profile_builder, "build", return_value=dict(self._PROFILE)),
            patch.object(svc._renderer, "render", return_value="IC text"),
            patch(self._PATCH_TARGET) as mock_append,
        ):
            # ipc_hash is explicitly None — simulates pre-axis-engine era.
            svc.translate("Mira", "hello", ipc_hash=None)

        meta = mock_append.call_args.kwargs["meta"]
        assert meta == {"phase": "pre_axis_engine"}

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

        The snapshot is taken before the axis engine (when integrated) can
        mutate scores, so it represents the character's state as of this
        specific interaction — the exact context the LLM used to generate
        the IC output.
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
        """The chat channel is recorded in the event data payload."""
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
