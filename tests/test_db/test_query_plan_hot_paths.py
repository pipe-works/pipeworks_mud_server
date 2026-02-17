"""Query-plan guards for Phase 5 world-scoped hot paths."""

from __future__ import annotations

import sqlite3

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD


def _query_plan_details(cursor: sqlite3.Cursor, sql: str, params: tuple[object, ...]) -> list[str]:
    """Return ``EXPLAIN QUERY PLAN`` detail strings for a SQL statement."""
    cursor.execute(f"EXPLAIN QUERY PLAN {sql}", params)  # nosec B608
    return [str(row[3]) for row in cursor.fetchall()]


def _seed_world_scoped_activity() -> tuple[int, int]:
    """Seed one account/character/session/message row for hot-path plan checks."""
    assert database.create_user_with_password("plan_user", TEST_PASSWORD)
    user_id = database.get_user_id("plan_user")
    assert user_id is not None

    assert database.create_character_for_user(
        user_id, "plan_char", world_id=database.DEFAULT_WORLD_ID
    )
    character = database.get_character_by_name("plan_char")
    assert character is not None
    character_id = int(character["id"])

    assert database.create_session(
        user_id,
        "plan-session",
        character_id=character_id,
        world_id=database.DEFAULT_WORLD_ID,
    )
    assert database.add_chat_message(
        "plan_char",
        "hello",
        "spawn",
        world_id=database.DEFAULT_WORLD_ID,
    )

    return user_id, character_id


@pytest.mark.unit
@pytest.mark.db
def test_hot_path_character_lookup_uses_world_scoped_character_index(test_db, temp_db_path):
    """Character-by-user+world query should use ``idx_characters_user_world``."""
    with use_test_database(temp_db_path):
        user_id, _character_id = _seed_world_scoped_activity()
        conn = database.get_connection()
        cursor = conn.cursor()
        details = _query_plan_details(
            cursor,
            (
                "SELECT id, name, world_id, is_guest_created, created_at, updated_at "
                "FROM characters "
                "WHERE user_id = ? AND world_id = ? "
                "ORDER BY created_at ASC"
            ),
            (user_id, database.DEFAULT_WORLD_ID),
        )
        conn.close()

        assert any("idx_characters_user_world" in detail for detail in details)


@pytest.mark.unit
@pytest.mark.db
def test_hot_path_chat_history_uses_world_room_timestamp_index(test_db, temp_db_path):
    """Room chat-history query should use ``idx_chat_messages_world_room_timestamp``."""
    with use_test_database(temp_db_path):
        _seed_world_scoped_activity()
        conn = database.get_connection()
        cursor = conn.cursor()
        details = _query_plan_details(
            cursor,
            (
                "SELECT id, character_id, user_id, message, room, timestamp, recipient_character_id "
                "FROM chat_messages "
                "WHERE world_id = ? AND room = ? "
                "ORDER BY timestamp DESC LIMIT ?"
            ),
            (database.DEFAULT_WORLD_ID, "spawn", 50),
        )
        conn.close()

        assert any("idx_chat_messages_world_room_timestamp" in detail for detail in details)


@pytest.mark.unit
@pytest.mark.db
def test_hot_path_active_connections_uses_sessions_world_index(test_db, temp_db_path):
    """Active-connection world filter should use ``idx_sessions_world_id``."""
    with use_test_database(temp_db_path):
        _seed_world_scoped_activity()
        conn = database.get_connection()
        cursor = conn.cursor()
        details = _query_plan_details(
            cursor,
            (
                "SELECT s.id, s.user_id, s.character_id, s.world_id, s.session_id, "
                "s.created_at, s.last_activity, s.expires_at, s.client_type "
                "FROM sessions s "
                "WHERE (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now')) "
                "AND s.world_id = ? "
                "ORDER BY s.last_activity DESC"
            ),
            (database.DEFAULT_WORLD_ID,),
        )
        conn.close()

        assert any("idx_sessions_world_id" in detail for detail in details)


@pytest.mark.unit
@pytest.mark.db
def test_hot_path_world_admin_count_uses_sessions_world_activity_index(test_db, temp_db_path):
    """World admin active-count query should use ``idx_sessions_world_activity``."""
    with use_test_database(temp_db_path):
        _seed_world_scoped_activity()
        conn = database.get_connection()
        cursor = conn.cursor()
        details = _query_plan_details(
            cursor,
            (
                "SELECT COUNT(*) FROM sessions s "
                "WHERE s.world_id = ? "
                "AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))"
            ),
            (database.DEFAULT_WORLD_ID,),
        )
        conn.close()

        assert any("idx_sessions_world_activity" in detail for detail in details)
