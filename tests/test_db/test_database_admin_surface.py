"""Database compatibility-surface tests for admin inspector query helpers."""

from __future__ import annotations

import pytest

from mud_server.config import use_test_database
from mud_server.db import database


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_all_players(test_db, temp_db_path, db_with_users):
    """Compatibility surface should return all user rows."""
    with use_test_database(temp_db_path):
        players = database.get_all_users()
        assert len(players) == 4

        usernames = [p["username"] for p in players]
        assert "testplayer" in usernames
        assert "testadmin" in usernames


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_all_players_detailed(test_db, temp_db_path, db_with_users):
    """Compatibility surface should return masked password hash previews."""
    with use_test_database(temp_db_path):
        players = database.get_all_users_detailed()
        assert len(players) == 4

        for player in players:
            assert "..." in player["password_hash"] or len(player["password_hash"]) <= 20


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_all_sessions(test_db, temp_db_path, db_with_users):
    """Compatibility surface should return session rows with expected fields."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        sessions = database.get_all_sessions()
        assert len(sessions) == 2
        assert "created_at" in sessions[0]
        assert "expires_at" in sessions[0]
        assert sessions[0]["client_type"] == "unknown"


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_all_chat_messages(test_db, temp_db_path, db_with_users):
    """Compatibility surface should return recent chat messages across rooms."""
    with use_test_database(temp_db_path):
        database.add_chat_message(
            "testplayer_char",
            "Message 1",
            "spawn",
            world_id=database.DEFAULT_WORLD_ID,
        )
        database.add_chat_message(
            "testadmin_char",
            "Message 2",
            "forest",
            world_id=database.DEFAULT_WORLD_ID,
        )
        database.add_chat_message(
            "testplayer_char",
            "Message 3",
            "spawn",
            world_id=database.DEFAULT_WORLD_ID,
        )

        messages = database.get_all_chat_messages(limit=100)
        assert len(messages) == 3


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_all_chat_messages_world_filter(test_db, temp_db_path, db_with_users):
    """Compatibility surface chat queries should support world filtering."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        assert database.create_character_for_user(
            user_id, "alt_player", world_id="daily_undertaking"
        )

        database.add_chat_message(
            "testplayer_char", "Default world", "spawn", world_id="pipeworks_web"
        )
        database.add_chat_message("alt_player", "Alt world", "spawn", world_id="daily_undertaking")

        default_messages = database.get_all_chat_messages(limit=100, world_id="pipeworks_web")
        assert len(default_messages) == 1
        assert default_messages[0]["message"] == "Default world"

        alt_messages = database.get_all_chat_messages(limit=100, world_id="daily_undertaking")
        assert len(alt_messages) == 1
        assert alt_messages[0]["message"] == "Alt world"


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_list_tables(test_db, temp_db_path, db_with_users):
    """Compatibility surface should expose admin table metadata rows."""
    with use_test_database(temp_db_path):
        tables = database.list_tables()
        table_names = {table["name"] for table in tables}

        assert {
            "users",
            "characters",
            "character_locations",
            "sessions",
            "chat_messages",
            "worlds",
            "world_permissions",
        }.issubset(table_names)
        assert all("columns" in table for table in tables)
        assert all("row_count" in table for table in tables)


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_table_rows(test_db, temp_db_path, db_with_users):
    """Compatibility surface should return columns and rows for an existing table."""
    with use_test_database(temp_db_path):
        columns, rows = database.get_table_rows("users", limit=10)

        assert "username" in columns
        assert len(rows) >= 1


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_table_rows_invalid_table_raises(test_db, temp_db_path, db_with_users):
    """Compatibility surface should preserve invalid-table value error behavior."""
    with use_test_database(temp_db_path):
        with pytest.raises(ValueError, match="does not exist"):
            database.get_table_rows("not_a_table")
