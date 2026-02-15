"""Tests for mud_server.config environment overrides."""

import pytest

from mud_server.config import load_config


@pytest.mark.unit
def test_session_env_overrides(monkeypatch):
    monkeypatch.setenv("MUD_SESSION_TTL_MINUTES", "30")
    monkeypatch.setenv("MUD_SESSION_SLIDING_EXPIRATION", "false")
    monkeypatch.setenv("MUD_SESSION_ALLOW_MULTIPLE", "true")
    monkeypatch.setenv("MUD_SESSION_ACTIVE_WINDOW_MINUTES", "45")

    cfg = load_config()

    assert cfg.session.ttl_minutes == 30
    assert cfg.session.sliding_expiration is False
    assert cfg.session.allow_multiple_sessions is True
    assert cfg.session.active_window_minutes == 45


@pytest.mark.unit
def test_character_env_overrides(monkeypatch):
    monkeypatch.setenv("MUD_CHAR_DEFAULT_SLOTS", "3")
    monkeypatch.setenv("MUD_CHAR_MAX_SLOTS", "9")

    cfg = load_config()

    assert cfg.characters.default_slots == 3
    assert cfg.characters.max_slots == 9


@pytest.mark.unit
def test_world_env_overrides(monkeypatch):
    monkeypatch.setenv("MUD_WORLDS_ROOT", "/tmp/worlds")
    monkeypatch.setenv("MUD_DEFAULT_WORLD_ID", "pipeworks_web")
    monkeypatch.setenv("MUD_ALLOW_MULTI_WORLD_CHARACTERS", "true")

    cfg = load_config()

    assert cfg.worlds.worlds_root == "/tmp/worlds"
    assert cfg.worlds.default_world_id == "pipeworks_web"
    assert cfg.worlds.allow_multi_world_characters is True


@pytest.mark.unit
def test_entity_integration_env_overrides(monkeypatch):
    monkeypatch.setenv("MUD_ENTITY_STATE_ENABLED", "false")
    monkeypatch.setenv("MUD_ENTITY_STATE_BASE_URL", "https://entity.example.org")
    monkeypatch.setenv("MUD_ENTITY_STATE_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("MUD_ENTITY_STATE_INCLUDE_PROMPTS", "true")

    cfg = load_config()

    assert cfg.integrations.entity_state_enabled is False
    assert cfg.integrations.entity_state_base_url == "https://entity.example.org"
    assert cfg.integrations.entity_state_timeout_seconds == 7.5
    assert cfg.integrations.entity_state_include_prompts is True
