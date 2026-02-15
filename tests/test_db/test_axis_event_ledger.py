"""
Tests for axis event ledger mutations.

These tests ensure:
- axis deltas update scores and snapshots
- event + delta + metadata rows are recorded
- invalid axes roll back the transaction
"""

from __future__ import annotations

import json

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD


def _seed_policy(world_id: str) -> None:
    """Seed axis registry for testing."""
    axes_payload = {
        "axes": {
            "wealth": {
                "description": "Economic status",
                "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
            }
        }
    }
    thresholds_payload = {
        "axes": {
            "wealth": {
                "values": {
                    "poor": {"min": 0.0, "max": 0.49},
                    "wealthy": {"min": 0.5, "max": 1.0},
                }
            }
        }
    }
    database.seed_axis_registry(
        world_id=world_id,
        axes_payload=axes_payload,
        thresholds_payload=thresholds_payload,
    )


@pytest.mark.unit
@pytest.mark.db
def test_apply_axis_event_updates_scores_and_snapshot(temp_db_path, monkeypatch) -> None:
    """Axis event should update scores, ledger rows, and current snapshot."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        monkeypatch.setattr(database, "_get_axis_policy_hash", lambda _world_id: "policyhash")

        world_id = "test_world"
        _seed_policy(world_id)

        assert database.create_user_with_password(
            "event_user", TEST_PASSWORD, create_default_character=False
        )
        user_id = database.get_user_id("event_user")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "event_char", world_id=world_id)
        character = database.get_character_by_name("event_char")
        assert character is not None

        # Snapshot seeds now start from a random non-zero value, so we assert
        # monotonic increment instead of a fixed literal.
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT state_seed FROM characters WHERE id = ?",
            (int(character["id"]),),
        )
        initial_seed = int(cursor.fetchone()[0])
        conn.close()

        event_id = database.apply_axis_event(
            world_id=world_id,
            character_id=int(character["id"]),
            event_type_name="unit_test_event",
            deltas={"wealth": -0.4},
            metadata={"source": "unit"},
        )

        conn = database.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM event WHERE id = ?", (event_id,))
        assert cursor.fetchone() is not None

        cursor.execute("SELECT COUNT(*) FROM event_metadata WHERE event_id = ?", (event_id,))
        assert int(cursor.fetchone()[0]) == 1

        cursor.execute(
            """
            SELECT old_score, new_score, delta
            FROM event_entity_axis_delta
            WHERE event_id = ?
            """,
            (event_id,),
        )
        old_score, new_score, delta = cursor.fetchone()
        assert old_score == pytest.approx(0.5)
        assert new_score == pytest.approx(0.1)
        assert delta == pytest.approx(-0.4)

        cursor.execute(
            """
            SELECT axis_score
            FROM character_axis_score s
            JOIN axis a ON a.id = s.axis_id
            WHERE s.character_id = ? AND a.name = 'wealth'
            """,
            (character["id"],),
        )
        assert cursor.fetchone()[0] == pytest.approx(0.1)

        cursor.execute(
            """
            SELECT current_state_json, state_seed, state_version
            FROM characters
            WHERE id = ?
            """,
            (character["id"],),
        )
        current_state_json, state_seed, state_version = cursor.fetchone()
        conn.close()

        assert state_seed == initial_seed + 1
        assert state_version == "policyhash"

        snapshot = json.loads(current_state_json)
        assert snapshot["axes"]["wealth"]["label"] == "poor"
        assert snapshot["axes"]["wealth"]["score"] == pytest.approx(0.1)


@pytest.mark.unit
@pytest.mark.db
def test_apply_axis_event_unknown_axis_raises_and_rolls_back(temp_db_path, monkeypatch) -> None:
    """Invalid axes should raise and leave no ledger rows behind."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        monkeypatch.setattr(database, "_get_axis_policy_hash", lambda _world_id: "policyhash")

        world_id = "test_world"
        _seed_policy(world_id)

        assert database.create_user_with_password(
            "event_user", TEST_PASSWORD, create_default_character=False
        )
        user_id = database.get_user_id("event_user")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "event_char", world_id=world_id)
        character = database.get_character_by_name("event_char")
        assert character is not None

        with pytest.raises(ValueError):
            database.apply_axis_event(
                world_id=world_id,
                character_id=int(character["id"]),
                event_type_name="bad_event",
                deltas={"missing_axis": 0.1},
            )

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM event")
        assert int(cursor.fetchone()[0]) == 0
        cursor.execute("SELECT COUNT(*) FROM event_entity_axis_delta")
        assert int(cursor.fetchone()[0]) == 0
        conn.close()


@pytest.mark.unit
def test_apply_axis_event_empty_deltas_raises() -> None:
    """Empty event deltas should be rejected."""
    with pytest.raises(ValueError):
        database.apply_axis_event(
            world_id="test_world",
            character_id=1,
            event_type_name="empty_event",
            deltas={},
        )


@pytest.mark.unit
@pytest.mark.db
def test_get_character_axis_events_returns_event(temp_db_path, monkeypatch) -> None:
    """Axis event query should return events with metadata and deltas."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        monkeypatch.setattr(database, "_get_axis_policy_hash", lambda _world_id: "policyhash")

        world_id = "test_world"
        _seed_policy(world_id)

        assert database.create_user_with_password(
            "event_query_user", TEST_PASSWORD, create_default_character=False
        )
        user_id = database.get_user_id("event_query_user")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "event_query_char", world_id=world_id)
        character = database.get_character_by_name("event_query_char")
        assert character is not None

        event_id = database.apply_axis_event(
            world_id=world_id,
            character_id=int(character["id"]),
            event_type_name="query_event",
            deltas={"wealth": 0.2},
            metadata={"source": "query"},
        )

        events = database.get_character_axis_events(int(character["id"]))
        assert len(events) == 1
        event = events[0]
        assert event["event_id"] == event_id
        assert event["event_type"] == "query_event"
        assert event["metadata"]["source"] == "query"
        assert event["deltas"][0]["axis_name"] == "wealth"
