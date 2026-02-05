"""Tests for mud_server.config environment overrides."""

import pytest

from mud_server.config import load_config


@pytest.mark.unit
def test_session_env_overrides(monkeypatch):
    monkeypatch.setenv("MUD_SESSION_TTL_MINUTES", "30")
    monkeypatch.setenv("MUD_SESSION_SLIDING_EXPIRATION", "false")
    monkeypatch.setenv("MUD_SESSION_ALLOW_MULTIPLE", "true")

    cfg = load_config()

    assert cfg.session.ttl_minutes == 30
    assert cfg.session.sliding_expiration is False
    assert cfg.session.allow_multiple_sessions is True
