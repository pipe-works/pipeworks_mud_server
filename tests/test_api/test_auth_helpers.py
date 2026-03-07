"""Unit tests for auth route helper functions."""

from __future__ import annotations

import pytest

from mud_server.api.routes import auth


@pytest.mark.unit
def test_fetch_entity_state_delegates_to_provisioning_helper(monkeypatch):
    """Auth helper should delegate entity fetch to shared provisioning helper."""
    observed: dict[str, object] = {}

    def _fake_fetch(*, seed: int, world_id: str | None):
        observed["seed"] = seed
        observed["world_id"] = world_id
        return {"seed": seed, "axes": {"health": 0.5}}, None

    monkeypatch.setattr(auth, "provisioning_fetch_entity_state_for_seed", _fake_fetch)

    payload, error = auth._fetch_entity_state_for_character(seed=101)

    assert payload == {"seed": 101, "axes": {"health": 0.5}}
    assert error is None
    assert observed == {"seed": 101, "world_id": None}


@pytest.mark.unit
def test_fetch_entity_state_surfaces_provisioning_helper_error(monkeypatch):
    """Auth helper should preserve stable non-fatal errors from shared helper."""
    monkeypatch.setattr(
        auth,
        "provisioning_fetch_entity_state_for_seed",
        lambda *, seed, world_id: (None, "Entity state API unavailable."),
    )

    payload, error = auth._fetch_entity_state_for_character(seed=102)

    assert payload is None
    assert error == "Entity state API unavailable."


@pytest.mark.unit
def test_fetch_entity_state_forwards_explicit_world_id(monkeypatch):
    """Auth helper should forward explicit world overrides to shared helper."""
    observed: dict[str, object] = {}

    def _fake_fetch(*, seed: int, world_id: str | None):
        observed["seed"] = seed
        observed["world_id"] = world_id
        return None, None

    monkeypatch.setattr(auth, "provisioning_fetch_entity_state_for_seed", _fake_fetch)

    payload, error = auth._fetch_entity_state_for_character(seed=106, world_id="pipeworks_web")

    assert payload is None
    assert error is None
    assert observed == {"seed": 106, "world_id": "pipeworks_web"}


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
