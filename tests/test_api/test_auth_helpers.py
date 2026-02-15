"""Unit tests for auth route helper functions."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from mud_server.api.routes import auth


@pytest.mark.unit
def test_fetch_entity_state_returns_none_when_integration_disabled(monkeypatch):
    """Entity helper should short-circuit when integration is disabled."""
    monkeypatch.setattr(auth.config.integrations, "entity_state_enabled", False)

    payload, error = auth._fetch_entity_state_for_character(seed=101)

    assert payload is None
    assert error is None


@pytest.mark.unit
def test_fetch_entity_state_returns_error_for_blank_base_url(monkeypatch):
    """Entity helper should reject empty/blank integration base URLs."""
    monkeypatch.setattr(auth.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(auth.config.integrations, "entity_state_base_url", "   ")

    payload, error = auth._fetch_entity_state_for_character(seed=102)

    assert payload is None
    assert error is not None
    assert "base url" in error.lower()


@pytest.mark.unit
def test_fetch_entity_state_returns_error_for_non_200(monkeypatch):
    """Entity helper should surface upstream HTTP status code failures."""
    monkeypatch.setattr(auth.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        auth.config.integrations, "entity_state_base_url", "https://entity.example.org"
    )

    fake_response = Mock(status_code=503)
    monkeypatch.setattr(auth.requests, "post", lambda *args, **kwargs: fake_response)

    payload, error = auth._fetch_entity_state_for_character(seed=103)

    assert payload is None
    assert error == "Entity state API returned HTTP 503."


@pytest.mark.unit
def test_fetch_entity_state_returns_error_for_non_object_payload(monkeypatch):
    """Entity helper should reject JSON payloads that are not objects."""
    monkeypatch.setattr(auth.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        auth.config.integrations, "entity_state_base_url", "https://entity.example.org"
    )

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = ["not", "an", "object"]
    monkeypatch.setattr(auth.requests, "post", lambda *args, **kwargs: fake_response)

    payload, error = auth._fetch_entity_state_for_character(seed=104)

    assert payload is None
    assert error == "Entity state API returned a non-object payload."


@pytest.mark.unit
def test_fetch_entity_state_returns_error_for_invalid_json(monkeypatch):
    """Entity helper should handle malformed JSON responses safely."""
    monkeypatch.setattr(auth.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        auth.config.integrations, "entity_state_base_url", "https://entity.example.org"
    )

    fake_response = Mock(status_code=200)
    fake_response.json.side_effect = ValueError("invalid json")
    monkeypatch.setattr(auth.requests, "post", lambda *args, **kwargs: fake_response)

    payload, error = auth._fetch_entity_state_for_character(seed=105)

    assert payload is None
    assert error == "Entity state API returned invalid JSON."


@pytest.mark.unit
def test_fetch_entity_state_returns_payload_for_valid_response(monkeypatch):
    """Entity helper should return upstream JSON object payloads."""
    monkeypatch.setattr(auth.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        auth.config.integrations, "entity_state_base_url", "https://entity.example.org/"
    )
    monkeypatch.setattr(auth.config.integrations, "entity_state_timeout_seconds", 9.5)
    monkeypatch.setattr(auth.config.integrations, "entity_state_include_prompts", True)

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {"seed": 106, "character": {"wealth": "poor"}}
    post_mock = Mock(return_value=fake_response)
    monkeypatch.setattr(auth.requests, "post", post_mock)

    payload, error = auth._fetch_entity_state_for_character(seed=106)

    assert error is None
    assert payload == {"seed": 106, "character": {"wealth": "poor"}}
    post_mock.assert_called_once_with(
        "https://entity.example.org/api/entity",
        json={"seed": 106, "include_prompts": True},
        timeout=9.5,
    )


@pytest.mark.unit
def test_fetch_local_axis_snapshot_returns_error_when_missing(monkeypatch):
    """Local snapshot helper should return an explicit missing-state error."""
    monkeypatch.setattr(auth.database, "get_character_axis_state", lambda _character_id: None)

    payload, error = auth._fetch_local_axis_snapshot_for_character(character_id=201)

    assert payload is None
    assert error == "Character axis state unavailable."


@pytest.mark.unit
def test_fetch_local_axis_snapshot_returns_error_when_snapshot_missing(monkeypatch):
    """Local snapshot helper should reject missing/non-dict current_state values."""
    monkeypatch.setattr(
        auth.database,
        "get_character_axis_state",
        lambda _character_id: {"current_state": "invalid"},
    )

    payload, error = auth._fetch_local_axis_snapshot_for_character(character_id=202)

    assert payload is None
    assert error == "Character axis snapshot missing."


@pytest.mark.unit
def test_fetch_local_axis_snapshot_returns_current_state(monkeypatch):
    """Local snapshot helper should return the persisted current snapshot."""
    snapshot = {"seed": 0, "axes": {"health": {"label": "weary", "score": 0.5}}}
    monkeypatch.setattr(
        auth.database,
        "get_character_axis_state",
        lambda _character_id: {"current_state": snapshot},
    )

    payload, error = auth._fetch_local_axis_snapshot_for_character(character_id=203)

    assert error is None
    assert payload == snapshot
