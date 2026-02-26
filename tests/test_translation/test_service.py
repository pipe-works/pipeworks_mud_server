"""Unit tests for OOCToICTranslationService."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mud_server.translation.config import TranslationLayerConfig
from mud_server.translation.service import OOCToICTranslationService

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
