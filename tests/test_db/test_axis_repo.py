"""Focused tests for ``mud_server.db.axis_repo``."""

from __future__ import annotations

from typing import Any

from mud_server.db import axis_repo, database


def _seed_default_axis_registry(world_id: str) -> None:
    """Seed a minimal axis registry used by axis/event repository tests."""
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


def test_seed_axis_registry_via_repo(test_db):
    """Axis repo should seed axis/axis_value rows and report stats."""
    world_id = database.DEFAULT_WORLD_ID
    _seed_default_axis_registry(world_id)

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM axis WHERE world_id = ?", (world_id,))
    axis_count = int(cursor.fetchone()[0])
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM axis_value av
        JOIN axis a ON a.id = av.axis_id
        WHERE a.world_id = ?
        """,
        (world_id,),
    )
    value_count = int(cursor.fetchone()[0])
    conn.close()

    assert axis_count >= 1
    assert value_count >= 2


def test_get_character_axis_state_via_repo(test_db):
    """Axis repo state query should return seeded score + label payload."""
    world_id = database.DEFAULT_WORLD_ID
    _seed_default_axis_registry(world_id)

    assert database.create_user_with_password("axis_repo_user", "SecureTest#123")
    user_id = database.get_user_id("axis_repo_user")
    assert user_id is not None
    assert database.create_character_for_user(user_id, "axis_repo_char", world_id=world_id)

    character = database.get_character_by_name("axis_repo_char")
    assert character is not None

    state = axis_repo.get_character_axis_state(int(character["id"]))
    assert state is not None
    assert state["world_id"] == world_id
    assert any(axis["axis_name"] == "wealth" for axis in state["axes"])


def test_flatten_entity_axis_labels_via_repo():
    """Entity payload flattening should merge character and occupation labels."""
    payload = {
        "character": {"wealth": "well-kept"},
        "occupation": {"status": "respected"},
    }
    labels = axis_repo._flatten_entity_axis_labels(payload)
    assert labels["wealth"] == "well-kept"
    assert labels["status"] == "respected"
