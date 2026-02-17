"""
Tests for applying external entity-state payloads to character axis scores.

These tests validate label-to-score conversion and ledger writes for the
entity-profile bootstrap path used by admin character provisioning.
"""

from __future__ import annotations

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD


def _seed_entity_test_registry(world_id: str) -> None:
    """Seed a small axis registry with one character and one occupation axis."""
    axes_payload = {
        "axes": {
            "wealth": {
                "description": "Economic status",
                "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
            },
            "legitimacy": {
                "description": "Occupation legitimacy",
                "ordering": {"type": "ordinal", "values": ["sanctioned", "illicit"]},
            },
        }
    }
    thresholds_payload = {
        "axes": {
            "wealth": {
                "values": {
                    "poor": {"min": 0.0, "max": 0.49},
                    "wealthy": {"min": 0.50, "max": 1.0},
                }
            },
            "legitimacy": {
                "values": {
                    "sanctioned": {"min": 0.0, "max": 0.49},
                    "illicit": {"min": 0.50, "max": 1.0},
                }
            },
        }
    }
    database.seed_axis_registry(
        world_id=world_id,
        axes_payload=axes_payload,
        thresholds_payload=thresholds_payload,
    )


@pytest.mark.unit
@pytest.mark.db
def test_flatten_entity_axis_labels_handles_character_and_occupation() -> None:
    """Flatten helper should normalize both entity API and snapshot-like payloads."""
    payload = {
        "character": {"wealth": "poor"},
        "occupation": {"legitimacy": "illicit"},
        "axes": {"age": {"label": "old"}},
    }

    labels = database._flatten_entity_axis_labels(payload)

    assert labels == {"wealth": "poor", "legitimacy": "illicit", "age": "old"}


@pytest.mark.unit
@pytest.mark.db
def test_apply_entity_state_to_character_writes_axis_event_and_updates_scores(temp_db_path) -> None:
    """Entity payload should write one event and update both axis groups."""
    world_id = "entity_test_world"
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)
        _seed_entity_test_registry(world_id)

        assert database.create_user_with_password(
            "entity_profile_user",
            TEST_PASSWORD,
        )
        user_id = database.get_user_id("entity_profile_user")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "entity_profile_char", world_id=world_id)

        character = database.get_character_by_name("entity_profile_char")
        assert character is not None
        character_id = int(character["id"])

        event_id = database.apply_entity_state_to_character(
            character_id=character_id,
            world_id=world_id,
            entity_state={
                "character": {"wealth": "poor"},
                "occupation": {"legitimacy": "illicit"},
            },
            seed=777,
        )

        assert isinstance(event_id, int)
        axis_state = database.get_character_axis_state(character_id)
        assert axis_state is not None
        labels = {axis["axis_name"]: axis["axis_label"] for axis in axis_state["axes"]}
        assert labels["wealth"] == "poor"
        assert labels["legitimacy"] == "illicit"

        events = database.get_character_axis_events(character_id, limit=5)
        assert events
        assert events[0]["event_type"] == "entity_profile_seeded"
        assert events[0]["metadata"]["seed"] == "777"


@pytest.mark.unit
@pytest.mark.db
def test_apply_entity_state_to_character_returns_none_when_no_axis_mappings(temp_db_path) -> None:
    """No-op payloads should not create ledger events."""
    world_id = "entity_test_world"
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)
        _seed_entity_test_registry(world_id)

        assert database.create_user_with_password(
            "entity_noop_user",
            TEST_PASSWORD,
        )
        user_id = database.get_user_id("entity_noop_user")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "entity_noop_char", world_id=world_id)

        character = database.get_character_by_name("entity_noop_char")
        assert character is not None

        event_id = database.apply_entity_state_to_character(
            character_id=int(character["id"]),
            world_id=world_id,
            entity_state={"character": {"unknown_axis": "ghosted"}},
            seed=9090,
        )

        assert event_id is None
        events = database.get_character_axis_events(int(character["id"]), limit=5)
        assert events == []
