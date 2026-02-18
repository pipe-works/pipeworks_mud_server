"""Compatibility-surface tests for session helpers exported via ``db.database``.

These tests intentionally target the legacy import path used by runtime and
older tests while the implementation remains delegated through repo modules.
The goal is to keep contract coverage for session semantics while reducing
monolith density in ``test_database.py``.
"""

import sqlite3
from typing import Any, cast
from unittest.mock import Mock

import pytest

from mud_server.config import use_test_database
from mud_server.db import connection as db_connection
from mud_server.db import database
from mud_server.db.errors import DatabaseWriteError

# ============================================================================
# SESSION MANAGEMENT COMPATIBILITY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_create_session(test_db, temp_db_path, db_with_users):
    """Session creation should update login state and persist client metadata."""
    with use_test_database(temp_db_path):
        result = database.create_session("testplayer", "session-123")
        assert result is True

        players = database.get_all_users_detailed()
        matching = [player for player in players if player["username"] == "testplayer"]
        assert matching
        assert matching[0]["last_login"] is not None
        session = database.get_session_by_id("session-123")
        assert session is not None
        assert session["client_type"] == "unknown"


@pytest.mark.unit
@pytest.mark.db
def test_create_session_normalizes_client_type(test_db, temp_db_path, db_with_users):
    """Client type input should be normalized before persistence."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-456", client_type="  TUI ")
        session = database.get_session_by_id("session-456")
        assert session is not None
        assert session["client_type"] == "tui"


@pytest.mark.unit
@pytest.mark.db
def test_remove_sessions_for_character(test_db, temp_db_path, db_with_users):
    """Character-scoped session cleanup should remove matching sessions only."""
    with use_test_database(temp_db_path):
        assert database.create_session("testplayer", "session-char")
        player_character = database.get_character_by_name("testplayer_char")
        assert player_character is not None
        assert database.set_session_character(
            "session-char",
            int(player_character["id"]),
            world_id=database.DEFAULT_WORLD_ID,
        )
        session = database.get_session_by_id("session-char")
        assert session is not None
        assert session["character_id"] is not None

        removed = database.remove_sessions_for_character(int(session["character_id"]))

        assert removed is True
        assert database.get_session_by_id("session-char") is None


@pytest.mark.unit
@pytest.mark.db
def test_remove_sessions_for_character_returns_false_when_none_removed(
    test_db, temp_db_path, db_with_users
):
    """Character cleanup should return False when no matching sessions exist."""
    with use_test_database(temp_db_path):
        assert database.remove_sessions_for_character(999999) is False


@pytest.mark.unit
@pytest.mark.db
def test_remove_sessions_for_character_handles_database_error(monkeypatch):
    """Character cleanup should map DB driver failures to typed write errors."""
    monkeypatch.setattr(db_connection, "get_connection", Mock(side_effect=sqlite3.Error("db boom")))

    with pytest.raises(DatabaseWriteError):
        database.remove_sessions_for_character(42)


@pytest.mark.unit
@pytest.mark.db
def test_update_session_activity_without_sliding_expiration(test_db, temp_db_path, db_with_users):
    """When sliding expiration is disabled, activity updates should still succeed."""
    from mud_server.config import config

    original_sliding = config.session.sliding_expiration
    try:
        config.session.sliding_expiration = False
        with use_test_database(temp_db_path):
            session_id = "session-no-slide"
            database.create_session("testplayer", session_id)
            assert database.update_session_activity(session_id) is True
    finally:
        config.session.sliding_expiration = original_sliding


@pytest.mark.unit
@pytest.mark.db
def test_session_invariant_trigger_rejects_account_world_binding(
    test_db, temp_db_path, db_with_users
):
    """Account-only sessions must not set ``world_id`` without a character."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None

        conn = database.get_connection()
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError, match="account session has world_id"):
            cursor.execute(
                """
                INSERT INTO sessions (user_id, world_id, session_id)
                VALUES (?, ?, ?)
                """,
                (user_id, "pipeworks_web", "invalid-account-world"),
            )
        conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_session_invariant_trigger_rejects_character_without_world(
    test_db, temp_db_path, db_with_users
):
    """Character sessions must include a world binding."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        character = database.get_character_by_name("testplayer_char")
        assert user_id is not None
        assert character is not None

        conn = database.get_connection()
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError, match="character session missing world_id"):
            cursor.execute(
                """
                INSERT INTO sessions (user_id, character_id, session_id)
                VALUES (?, ?, ?)
                """,
                (user_id, int(character["id"]), "invalid-character-no-world"),
            )
        conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_session_invariant_trigger_rejects_world_mismatch(test_db, temp_db_path, db_with_users):
    """Session world must match the bound character world."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        character = database.get_character_by_name("testplayer_char")
        assert user_id is not None
        assert character is not None

        conn = database.get_connection()
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError, match="world mismatch for character"):
            cursor.execute(
                """
                INSERT INTO sessions (user_id, character_id, world_id, session_id)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, int(character["id"]), "daily_undertaking", "invalid-world-mismatch"),
            )
        conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_session_invariant_trigger_rejects_update_tampering(test_db, temp_db_path, db_with_users):
    """Update trigger should reject direct SQL tampering of account-only sessions."""
    with use_test_database(temp_db_path):
        assert database.create_session("testplayer", "tamper-session")

        conn = database.get_connection()
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError, match="account session has world_id"):
            cursor.execute(
                "UPDATE sessions SET world_id = ? WHERE session_id = ?",
                ("pipeworks_web", "tamper-session"),
            )
        conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_create_session_no_ttl_sets_null_expiry(test_db, temp_db_path, db_with_users):
    """A zero-minute TTL should store ``expires_at`` as ``NULL``."""
    from mud_server.config import config

    with use_test_database(temp_db_path):
        original = config.session.ttl_minutes
        config.session.ttl_minutes = 0
        try:
            database.create_session("testplayer", "session-123")
            session = database.get_session_by_id("session-123")
            assert session is not None
            assert session["expires_at"] is None
        finally:
            config.session.ttl_minutes = original


@pytest.mark.unit
@pytest.mark.db
def test_create_session_removes_old_session_when_single_session(
    test_db, temp_db_path, db_with_users
):
    """When multi-session is disabled, creating a new session evicts the old one."""
    from mud_server.config import config

    with use_test_database(temp_db_path):
        original = config.session.allow_multiple_sessions
        config.session.allow_multiple_sessions = False
        try:
            database.create_session("testplayer", "session-1")
            database.create_session("testplayer", "session-2")

            conn = database.get_connection()
            cursor = conn.cursor()
            user_id = database.get_user_id("testplayer")
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,))
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 1
        finally:
            config.session.allow_multiple_sessions = original


def test_create_session_allows_multiple_when_enabled(test_db, temp_db_path, db_with_users):
    """When enabled, session creation should keep multiple concurrent sessions."""
    from mud_server.config import config

    with use_test_database(temp_db_path):
        original = config.session.allow_multiple_sessions
        config.session.allow_multiple_sessions = True
        try:
            database.create_session("testplayer", "session-1")
            database.create_session("testplayer", "session-2")

            conn = database.get_connection()
            cursor = conn.cursor()
            user_id = database.get_user_id("testplayer")
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,))
            count = cursor.fetchone()[0]
            conn.close()

            assert count == 2
        finally:
            config.session.allow_multiple_sessions = original


@pytest.mark.unit
@pytest.mark.db
def test_remove_session(test_db, temp_db_path, db_with_users):
    """User-scoped session cleanup should remove all sessions for that user."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-123")
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        result = database.remove_sessions_for_user(user_id)
        assert result is True

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0


@pytest.mark.unit
@pytest.mark.db
def test_remove_session_by_id(test_db, temp_db_path, db_with_users):
    """Session-id cleanup should remove only the targeted session."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-123")
        result = database.remove_session_by_id("session-123")
        assert result is True

        assert database.get_session_by_id("session-123") is None


@pytest.mark.unit
@pytest.mark.db
def test_get_active_players(test_db, temp_db_path, db_with_users):
    """Active character list should include all currently bound active sessions."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")
        player_character = database.get_character_by_name("testplayer_char")
        admin_character = database.get_character_by_name("testadmin_char")
        assert player_character is not None
        assert admin_character is not None
        database.set_session_character(
            "session-1", player_character["id"], world_id=database.DEFAULT_WORLD_ID
        )
        database.set_session_character(
            "session-2", admin_character["id"], world_id=database.DEFAULT_WORLD_ID
        )

        active = database.get_active_characters(world_id=database.DEFAULT_WORLD_ID)
        assert len(active) == 2
        assert "testplayer_char" in active
        assert "testadmin_char" in active


@pytest.mark.unit
@pytest.mark.db
def test_get_active_characters_requires_explicit_world_id():
    """Active-character lookup should require explicit world scope."""
    get_active_characters = cast(Any, database.get_active_characters)
    with pytest.raises(TypeError, match="missing 1 required keyword-only argument: 'world_id'"):
        get_active_characters()


@pytest.mark.unit
@pytest.mark.db
def test_get_players_in_room(test_db, temp_db_path, db_with_users):
    """Room queries should return only active characters currently in that room."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")
        player_character = database.get_character_by_name("testplayer_char")
        admin_character = database.get_character_by_name("testadmin_char")
        assert player_character is not None
        assert admin_character is not None
        database.set_session_character(
            "session-1", player_character["id"], world_id=database.DEFAULT_WORLD_ID
        )
        database.set_session_character(
            "session-2", admin_character["id"], world_id=database.DEFAULT_WORLD_ID
        )

        database.set_character_room("testadmin_char", "forest", world_id=database.DEFAULT_WORLD_ID)

        players_in_spawn = database.get_characters_in_room(
            "spawn",
            world_id=database.DEFAULT_WORLD_ID,
        )
        assert len(players_in_spawn) == 1
        assert "testplayer_char" in players_in_spawn

        players_in_forest = database.get_characters_in_room(
            "forest",
            world_id=database.DEFAULT_WORLD_ID,
        )
        assert len(players_in_forest) == 1
        assert "testadmin_char" in players_in_forest


@pytest.mark.unit
@pytest.mark.db
def test_update_session_activity(test_db, temp_db_path, db_with_users):
    """Session activity updates should report success for existing sessions."""
    with use_test_database(temp_db_path):
        session_id = "session-123"
        database.create_session("testplayer", session_id)
        result = database.update_session_activity(session_id)
        assert result is True


# ============================================================================
# SESSION CLEANUP COMPATIBILITY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_removes_old(test_db, temp_db_path, db_with_users):
    """Expired sessions should be removed by cleanup."""
    with use_test_database(temp_db_path):
        session_id = "session-123"
        database.create_session("testplayer", session_id)
        player_character = database.get_character_by_name("testplayer_char")
        assert player_character is not None
        database.set_session_character(
            session_id, player_character["id"], world_id=database.DEFAULT_WORLD_ID
        )

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET expires_at = datetime('now', '-5 minutes') "
            "WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
        conn.close()

        removed = database.cleanup_expired_sessions()

        assert removed == 1
        active = database.get_active_characters(world_id=database.DEFAULT_WORLD_ID)
        assert "testplayer_char" not in active


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_keeps_active(test_db, temp_db_path, db_with_users):
    """Non-expired sessions should remain after cleanup."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-123")
        player_character = database.get_character_by_name("testplayer_char")
        assert player_character is not None
        database.set_session_character(
            "session-123", player_character["id"], world_id=database.DEFAULT_WORLD_ID
        )

        removed = database.cleanup_expired_sessions()

        assert removed == 0
        active = database.get_active_characters(world_id=database.DEFAULT_WORLD_ID)
        assert "testplayer_char" in active


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_mixed(test_db, temp_db_path, db_with_users):
    """Cleanup should remove only expired sessions in mixed state."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")
        player_character = database.get_character_by_name("testplayer_char")
        admin_character = database.get_character_by_name("testadmin_char")
        assert player_character is not None
        assert admin_character is not None
        database.set_session_character(
            "session-1", player_character["id"], world_id=database.DEFAULT_WORLD_ID
        )
        database.set_session_character(
            "session-2", admin_character["id"], world_id=database.DEFAULT_WORLD_ID
        )

        conn = database.get_connection()
        cursor = conn.cursor()
        user_id = database.get_user_id("testplayer")
        cursor.execute(
            "UPDATE sessions SET expires_at = datetime('now', '-10 minutes') WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
        conn.close()

        removed = database.cleanup_expired_sessions()

        assert removed == 1
        active = database.get_active_characters(world_id=database.DEFAULT_WORLD_ID)
        assert "testplayer_char" not in active
        assert "testadmin_char" in active


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_empty_db(test_db, temp_db_path):
    """Cleanup on an empty session table should return zero removed rows."""
    with use_test_database(temp_db_path):
        removed = database.cleanup_expired_sessions()
        assert removed == 0


@pytest.mark.unit
@pytest.mark.db
def test_clear_all_sessions(test_db, temp_db_path, db_with_users):
    """Global session clear should remove all active session rows."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")
        database.create_session("testsuperuser", "session-3")
        player_character = database.get_character_by_name("testplayer_char")
        admin_character = database.get_character_by_name("testadmin_char")
        super_character = database.get_character_by_name("testsuperuser_char")
        assert player_character is not None
        assert admin_character is not None
        assert super_character is not None
        database.set_session_character(
            "session-1", player_character["id"], world_id=database.DEFAULT_WORLD_ID
        )
        database.set_session_character(
            "session-2", admin_character["id"], world_id=database.DEFAULT_WORLD_ID
        )
        database.set_session_character(
            "session-3", super_character["id"], world_id=database.DEFAULT_WORLD_ID
        )

        assert len(database.get_active_characters(world_id=database.DEFAULT_WORLD_ID)) == 3

        removed = database.clear_all_sessions()

        assert removed == 3
        assert len(database.get_active_characters(world_id=database.DEFAULT_WORLD_ID)) == 0


@pytest.mark.unit
@pytest.mark.db
def test_clear_all_sessions_empty_db(test_db, temp_db_path):
    """Global session clear should report zero for an empty table."""
    with use_test_database(temp_db_path):
        removed = database.clear_all_sessions()
        assert removed == 0


@pytest.mark.unit
@pytest.mark.db
def test_clear_all_sessions_returns_count(test_db, temp_db_path, db_with_users):
    """Global clear should return the count of deleted rows."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        removed = database.clear_all_sessions()

        assert removed == 2
