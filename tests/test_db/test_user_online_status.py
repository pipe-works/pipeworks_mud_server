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

        assert database.create_user_with_password("online_user", TEST_PASSWORD)
        user_id = database.get_user_id("online_user")
        assert user_id is not None

        assert database.create_character_for_user(
            user_id, "online_char_a", world_id=database.DEFAULT_WORLD_ID
        )
        assert database.create_character_for_user(
            user_id, "online_char_b", world_id=database.DEFAULT_WORLD_ID
        )

        # Account-level login should remain character-less until explicit selection.
        assert database.create_session(user_id, "session-account-only")
        users = database.get_all_users_detailed()
        user = next(entry for entry in users if entry["username"] == "online_user")
        assert user["is_online_account"] is True
        assert user["is_online_in_world"] is False
        assert user["online_world_ids"] == []

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
        assert user["online_world_ids"] == [database.DEFAULT_WORLD_ID]

        # Add a second world-bound character/session and verify deterministic
        # world-list projection for the online indicator.
        assert database.create_character_for_user(
            user_id, "online_char_daily", world_id="daily_undertaking"
        )
        daily_character = database.get_character_by_name("online_char_daily")
        assert daily_character is not None
        assert database.create_session(
            user_id,
            "session-in-world-daily",
            character_id=int(daily_character["id"]),
        )

        users = database.get_all_users_detailed()
        user = next(entry for entry in users if entry["username"] == "online_user")
        assert user["online_world_ids"] == ["daily_undertaking", database.DEFAULT_WORLD_ID]


@pytest.mark.unit
@pytest.mark.db
def test_get_all_users_detailed_excludes_tombstoned_accounts(temp_db_path) -> None:
    """
    Active-users query should hide tombstoned accounts.

    Section 2 of the admin card requirements separates live operational rows
    from archival/deleted account records. Tombstoned users should therefore be
    absent from ``get_all_users_detailed()`` even though their row still exists
    in the ``users`` table for audit/history purposes.
    """
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        assert database.create_user_with_password("active_account", TEST_PASSWORD)
        assert database.create_user_with_password("to_be_tombstoned", TEST_PASSWORD)

        assert database.delete_user("to_be_tombstoned") is True

        # Verify the row still exists in storage as a tombstone record.
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tombstoned_at FROM users WHERE username = ?",
            ("to_be_tombstoned",),
        )
        tombstone_row = cursor.fetchone()
        conn.close()
        assert tombstone_row is not None
        assert tombstone_row[0] is not None

        users = database.get_all_users_detailed()
        usernames = {entry["username"] for entry in users}
        assert "active_account" in usernames
        assert "to_be_tombstoned" not in usernames
