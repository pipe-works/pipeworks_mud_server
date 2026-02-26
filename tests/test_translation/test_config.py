"""Unit tests for TranslationLayerConfig."""


import pytest

from mud_server.translation.config import TranslationLayerConfig


class TestTranslationLayerConfigFromDict:
    """Tests for TranslationLayerConfig.from_dict."""

    def test_all_fields_populated(self, tmp_path):
        data = {
            "enabled": True,
            "model": "llama3.2",
            "ollama_base_url": "http://remote:11434",
            "timeout_seconds": 5.0,
            "strict_mode": False,
            "max_output_chars": 140,
            "prompt_template_path": "policies/custom_prompt.txt",
            "active_axes": ["demeanor", "health"],
            "deterministic": True,
        }
        cfg = TranslationLayerConfig.from_dict(data, world_root=tmp_path)
        assert cfg.enabled is True
        assert cfg.model == "llama3.2"
        assert cfg.ollama_base_url == "http://remote:11434"
        assert cfg.timeout_seconds == 5.0
        assert cfg.strict_mode is False
        assert cfg.max_output_chars == 140
        assert cfg.prompt_template_path == "policies/custom_prompt.txt"
        assert cfg.active_axes == ["demeanor", "health"]
        assert cfg.deterministic is True

    def test_defaults_for_missing_optional_fields(self, tmp_path):
        """A minimal ``{"enabled": true}`` block should apply safe defaults."""
        cfg = TranslationLayerConfig.from_dict({"enabled": True}, world_root=tmp_path)
        assert cfg.enabled is True
        assert cfg.model == "gemma2:2b"
        assert cfg.ollama_base_url == "http://localhost:11434"
        assert cfg.timeout_seconds == 10.0
        assert cfg.strict_mode is True
        assert cfg.max_output_chars == 280
        assert cfg.prompt_template_path == "policies/ic_prompt.txt"
        assert cfg.active_axes == []
        assert cfg.deterministic is False

    def test_empty_dict_defaults_to_disabled(self, tmp_path):
        cfg = TranslationLayerConfig.from_dict({}, world_root=tmp_path)
        assert cfg.enabled is False

    def test_bool_coercion(self, tmp_path):
        """Integer 1/0 values from JSON should be coerced to bool correctly."""
        cfg = TranslationLayerConfig.from_dict(
            {"enabled": 1, "strict_mode": 0, "deterministic": 1},
            world_root=tmp_path,
        )
        assert cfg.enabled is True
        assert cfg.strict_mode is False
        assert cfg.deterministic is True


class TestTranslationLayerConfigDisabled:
    """Tests for TranslationLayerConfig.disabled."""

    def test_disabled_factory_returns_disabled_config(self):
        cfg = TranslationLayerConfig.disabled()
        assert cfg.enabled is False

    def test_disabled_factory_is_frozen(self):
        cfg = TranslationLayerConfig.disabled()
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            cfg.enabled = True  # type: ignore[misc]


class TestTranslationLayerConfigApiEndpoint:
    """Tests for TranslationLayerConfig.api_endpoint property."""

    def test_api_endpoint_appends_path(self, tmp_path):
        cfg = TranslationLayerConfig.from_dict(
            {"ollama_base_url": "http://localhost:11434"},
            world_root=tmp_path,
        )
        assert cfg.api_endpoint == "http://localhost:11434/api/chat"

    def test_api_endpoint_strips_trailing_slash(self, tmp_path):
        cfg = TranslationLayerConfig.from_dict(
            {"ollama_base_url": "http://localhost:11434/"},
            world_root=tmp_path,
        )
        assert cfg.api_endpoint == "http://localhost:11434/api/chat"

    def test_api_endpoint_with_custom_host(self, tmp_path):
        cfg = TranslationLayerConfig.from_dict(
            {"ollama_base_url": "http://192.168.1.10:11434"},
            world_root=tmp_path,
        )
        assert cfg.api_endpoint == "http://192.168.1.10:11434/api/chat"
