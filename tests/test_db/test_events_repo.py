"""Focused tests for ``mud_server.db.events_repo``."""

from __future__ import annotations

from typing import Any

from mud_server.db import axis_repo, database, events_repo


def _seed_default_axis_registry(world_id: str) -> None:
    """Seed a minimal axis registry for event repository tests."""
    axes_payload: dict[str, Any] = {
        "axes": {
            "wealth": {
                "description": "Economic status",
                "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
            }
        }
    }
    thresholds_payload: dict[str, Any] = {
        "axes": {
            "wealth": {
                "values": {
                    "poor": {"min": 0.0, "max": 0.5},
                    "wealthy": {"min": 0.5, "max": 1.0},
                }
            }
        }
    }
    axis_repo.seed_axis_registry(
        world_id=world_id,
        axes_payload=axes_payload,
        thresholds_payload=thresholds_payload,
    )


def test_apply_axis_event_and_query_via_repo(test_db, monkeypatch):
    """Events repo should write ledger rows and query them back."""
    world_id = database.DEFAULT_WORLD_ID
    _seed_default_axis_registry(world_id)
    monkeypatch.setattr(database, "_get_axis_policy_hash", lambda _world_id: "policyhash")

    assert database.create_user_with_password("events_repo_user", "SecureTest#123")
    user_id = database.get_user_id("events_repo_user")
    assert user_id is not None
    assert database.create_character_for_user(user_id, "events_repo_char", world_id=world_id)
    character = database.get_character_by_name("events_repo_char")
    assert character is not None

    event_id = events_repo.apply_axis_event(
        world_id=world_id,
        character_id=int(character["id"]),
        event_type_name="test_repo_event",
        deltas={"wealth": 0.25},
        metadata={"source": "events_repo_test"},
    )
    assert isinstance(event_id, int)

    events = events_repo.get_character_axis_events(int(character["id"]), limit=5)
    assert events
    assert events[0]["event_id"] == event_id
    assert any(delta["axis_name"] == "wealth" for delta in events[0]["deltas"])
