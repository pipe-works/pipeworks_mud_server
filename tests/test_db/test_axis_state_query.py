"""
Tests for fetching character axis state.
"""

from __future__ import annotations

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD


def _seed_policy(world_id: str) -> None:
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
def test_get_character_axis_state_returns_snapshot(temp_db_path, monkeypatch) -> None:
    """Axis state query should include snapshot data and labeled scores."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)
        monkeypatch.setattr(database, "_get_axis_policy_hash", lambda _world_id: "policyhash")

        world_id = "test_world"
        _seed_policy(world_id)

        assert database.create_user_with_password(
            "axis_state_user", TEST_PASSWORD, create_default_character=False
        )
        user_id = database.get_user_id("axis_state_user")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "axis_state_char", world_id=world_id)
        character = database.get_character_by_name("axis_state_char")
        assert character is not None

        state = database.get_character_axis_state(int(character["id"]))
        assert state is not None
        assert state["world_id"] == world_id
        assert state["state_version"] == "policyhash"
        assert state["current_state"]["axes"]["wealth"]["label"] == "wealthy"
        assert state["axes"][0]["axis_name"] == "wealth"
