"""Tests for mud_server.config environment overrides."""

import configparser

import pytest

from mud_server.config import ServerConfig, _load_from_ini, load_config, print_config_summary


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


@pytest.mark.unit
def test_entity_integration_ini_overrides():
    """Integration settings should load from the INI [integrations] section."""
    parser = configparser.ConfigParser()
    parser.read_dict(
        {
            "integrations": {
                "entity_state_enabled": "true",
                "entity_state_base_url": "https://entity.pipe-works.org",
                "entity_state_timeout_seconds": "4.25",
                "entity_state_include_prompts": "false",
            }
        }
    )

    cfg = ServerConfig()
    _load_from_ini(parser, cfg)

    assert cfg.integrations.entity_state_enabled is True
    assert cfg.integrations.entity_state_base_url == "https://entity.pipe-works.org"
    assert cfg.integrations.entity_state_timeout_seconds == 4.25
    assert cfg.integrations.entity_state_include_prompts is False


@pytest.mark.unit
def test_namegen_integration_env_overrides(monkeypatch):
    """Name generation integration settings should load from env vars."""
    monkeypatch.setenv("MUD_NAMEGEN_ENABLED", "false")
    monkeypatch.setenv("MUD_NAMEGEN_BASE_URL", "https://name.example.org")
    monkeypatch.setenv("MUD_NAMEGEN_TIMEOUT_SECONDS", "8.5")

    cfg = load_config()

    assert cfg.integrations.namegen_enabled is False
    assert cfg.integrations.namegen_base_url == "https://name.example.org"
    assert cfg.integrations.namegen_timeout_seconds == 8.5


@pytest.mark.unit
def test_namegen_integration_ini_overrides():
    """Name generation settings should load from the INI [integrations] section."""
    parser = configparser.ConfigParser()
    parser.read_dict(
        {
            "integrations": {
                "namegen_enabled": "true",
                "namegen_base_url": "https://name.pipe-works.org",
                "namegen_timeout_seconds": "5.75",
            }
        }
    )

    cfg = ServerConfig()
    _load_from_ini(parser, cfg)

    assert cfg.integrations.namegen_enabled is True
    assert cfg.integrations.namegen_base_url == "https://name.pipe-works.org"
    assert cfg.integrations.namegen_timeout_seconds == 5.75


@pytest.mark.unit
def test_print_config_summary_includes_entity_api_line(capsys):
    """Config summary should include the entity integration diagnostics line."""
    print_config_summary()
    output = capsys.readouterr().out
    assert "Entity API:" in output
    assert "Name API:" in output
