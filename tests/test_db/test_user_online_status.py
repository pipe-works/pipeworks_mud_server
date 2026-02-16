"""
Tests for online status fields in admin user lists.
"""

from __future__ import annotations

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD


@pytest.mark.unit
@pytest.mark.db
def test_get_all_users_detailed_online_status(temp_db_path) -> None:
    """User list should reflect account vs in-world online state."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        assert database.create_user_with_password(
            "online_user", TEST_PASSWORD, create_default_character=False
        )
        user_id = database.get_user_id("online_user")
        assert user_id is not None

        assert database.create_character_for_user(user_id, "online_char_a")
        assert database.create_character_for_user(user_id, "online_char_b")

        # Account-level login should remain character-less until explicit selection.
        assert database.create_session(user_id, "session-account-only")
        users = database.get_all_users_detailed()
        user = next(entry for entry in users if entry["username"] == "online_user")
        assert user["is_online_account"] is True
        assert user["is_online_in_world"] is False

        # Now simulate in-world session with a character selected.
        character = database.get_character_by_name("online_char_a")
        assert character is not None
        assert database.create_session(
            user_id, "session-in-world", character_id=int(character["id"])
        )
        users = database.get_all_users_detailed()
        user = next(entry for entry in users if entry["username"] == "online_user")
        assert user["is_online_account"] is True
        assert user["is_online_in_world"] is True
