"""Phase 1 tests for db connection/schema extraction.

These tests validate the extracted schema/connection behaviors introduced by the
0.3.10 refactor foundation work:
- connection pragma enforcement (foreign keys)
- world-scoped character uniqueness
- boolean-like CHECK constraints
- hot-path index creation
"""

from __future__ import annotations

import sqlite3

import pytest

from mud_server.db import connection as db_connection
from mud_server.db import database


@pytest.mark.unit
@pytest.mark.db
def test_get_connection_enables_foreign_keys(temp_db_path):
    """Every DB connection should enforce SQLite foreign keys."""
    database.init_database(skip_superuser=True)

    conn = db_connection.get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys")
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert int(row[0]) == 1


@pytest.mark.unit
@pytest.mark.db
def test_character_name_is_unique_per_world(temp_db_path):
    """Character names may repeat across worlds but not within one world."""
    database.init_database(skip_superuser=True)

    assert database.create_user_with_password("world_name_scope", "SecureTest#123")
    user_id = database.get_user_id("world_name_scope")
    assert user_id is not None

    assert database.create_character_for_user(user_id, "shared_name", world_id="pipeworks_web")
    assert database.create_character_for_user(user_id, "shared_name", world_id="daily_undertaking")

    # Same world duplicate should fail under UNIQUE(world_id, name).
    assert (
        database.create_character_for_user(user_id, "shared_name", world_id="pipeworks_web")
        is False
    )


@pytest.mark.unit
@pytest.mark.db
def test_schema_enforces_boolean_like_checks(temp_db_path):
    """Boolean-like integer columns should reject out-of-range values."""
    database.init_database(skip_superuser=True)

    conn = database.get_connection()
    cursor = conn.cursor()

    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, is_active)
            VALUES (?, ?, ?)
            """,
            ("bad_bool_user", "hash", 2),
        )
        conn.commit()

    conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_phase1_hot_path_indexes_exist(temp_db_path):
    """Phase 1 hot-path indexes should be present after initialization."""
    database.init_database(skip_superuser=True)

    conn = database.get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA index_list('sessions')")
    sessions_indexes = {str(row[1]) for row in cursor.fetchall()}

    cursor.execute("PRAGMA index_list('characters')")
    characters_indexes = {str(row[1]) for row in cursor.fetchall()}

    cursor.execute("PRAGMA index_list('chat_messages')")
    chat_indexes = {str(row[1]) for row in cursor.fetchall()}

    conn.close()

    assert "idx_sessions_user_activity" in sessions_indexes
    assert "idx_sessions_world_activity" in sessions_indexes
    assert "idx_sessions_user_id" in sessions_indexes
    assert "idx_sessions_character_id" in sessions_indexes
    assert "idx_sessions_world_id" in sessions_indexes
    assert "idx_characters_user_world" in characters_indexes
    assert "idx_chat_messages_world_room_timestamp" in chat_indexes
