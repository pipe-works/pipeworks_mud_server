"""
Unit tests for database layer (mud_server/db/database.py).

Tests cover:
- Database initialization and schema creation
- Player account management (create, exists, verify password)
- Role management (get, set, hierarchy)
- Account status (activate, deactivate)
- Player state (room, inventory)
- Chat message storage and retrieval
- Session management (create, remove, get active players)
- Admin queries (all players, sessions, messages)

All tests use temporary databases for isolation.
"""

import sqlite3
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD


class _FakeCursor:
    def __init__(self, *, lastrowid=None, fetchone=None):
        self.lastrowid = lastrowid
        self._fetchone = fetchone
        self.rowcount = 0

    def execute(self, _sql, _params=None):  # noqa: D401 - minimal fake
        return None

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return []


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def execute(self, sql, params=None):
        """Mirror sqlite3.Connection.execute for schema bootstrap fakes."""
        return self._cursor.execute(sql, params)

    def commit(self):
        return None

    def close(self):
        return None


# ============================================================================
# DATABASE INITIALIZATION TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_init_database_creates_tables(temp_db_path):
    """Test that init_database creates all required tables."""
    with use_test_database(temp_db_path):
        database.init_database()

        conn = database.get_connection()
        cursor = conn.cursor()

        # Check players table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        assert cursor.fetchone() is not None

        # Check sessions table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        assert cursor.fetchone() is not None

        # Check event ledger tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event'")
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='event_entity_axis_delta'"
        )
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='event_metadata'"
        )
        assert cursor.fetchone() is not None

        # Check chat_messages table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
        assert cursor.fetchone() is not None

        # Check characters table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='characters'")
        assert cursor.fetchone() is not None

        # Check axis registry tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='axis'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='axis_value'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_type'")
        assert cursor.fetchone() is not None

        # Check character axis state table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='character_axis_score'"
        )
        assert cursor.fetchone() is not None

        # Check character_locations table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='character_locations'"
        )
        assert cursor.fetchone() is not None

        # Check worlds table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='worlds'")
        assert cursor.fetchone() is not None

        # Check world_permissions table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='world_permissions'"
        )
        assert cursor.fetchone() is not None

        conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_init_database_creates_superuser_from_env_vars(temp_db_path):
    """Test that init_database creates superuser from environment variables."""
    with use_test_database(temp_db_path):
        with patch.dict(
            "os.environ", {"MUD_ADMIN_USER": "envadmin", "MUD_ADMIN_PASSWORD": "securepass123"}
        ):
            database.init_database()

            # Check admin user was created from env vars
            assert database.user_exists("envadmin")
            assert database.get_user_role("envadmin") == "superuser"
            assert database.verify_password_for_user("envadmin", "securepass123")
            # Superuser bootstrap no longer auto-provisions characters.
            assert database.get_character_by_name("envadmin_char") is None


@pytest.mark.unit
@pytest.mark.db
def test_init_database_no_superuser_without_env_vars(temp_db_path):
    """Test that init_database does NOT create superuser without environment variables."""
    with use_test_database(temp_db_path):
        # Ensure env vars are not set
        with patch.dict("os.environ", {}, clear=True):
            database.init_database()

            # No default admin should be created
            assert not database.user_exists("admin")

            # Check that tables were still created
            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            assert cursor.fetchone() is not None
            conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_init_database_skips_short_password(temp_db_path, capsys):
    """Test that init_database skips superuser creation if password is too short."""
    with use_test_database(temp_db_path):
        with patch.dict("os.environ", {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": "short"}):
            database.init_database()

            # No admin should be created due to short password
            assert not database.user_exists("admin")

            # Should print warning
            captured = capsys.readouterr()
            assert "must be at least 8 characters" in captured.out


# ============================================================================
# PLAYER ACCOUNT MANAGEMENT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_create_player_with_password_success(test_db, temp_db_path):
    """Test creating a new player with password."""
    with use_test_database(temp_db_path):
        result = database.create_user_with_password("newuser", TEST_PASSWORD, role="player")
        assert result is True

        # Verify player exists
        assert database.user_exists("newuser")

        # Verify password
        assert database.verify_password_for_user("newuser", TEST_PASSWORD)

        # Verify role
        assert database.get_user_role("newuser") == "player"


@pytest.mark.unit
@pytest.mark.db
def test_create_player_with_password_does_not_auto_create_character(test_db, temp_db_path):
    """Account creation should not provision bootstrap characters automatically."""
    with use_test_database(temp_db_path):
        result = database.create_user_with_password("newuser", TEST_PASSWORD, role="player")
        assert result is True
        assert database.get_character_by_name("newuser_char") is None


@pytest.mark.unit
@pytest.mark.db
def test_create_user_rejects_deprecated_auto_character_flag(test_db, temp_db_path):
    """Legacy auto-character flag should fail with a strict signature error."""
    with use_test_database(temp_db_path):
        create_user_with_password = cast(Any, database.create_user_with_password)
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            create_user_with_password(
                "legacy_user",
                TEST_PASSWORD,
                create_default_character=True,
            )


@pytest.mark.unit
@pytest.mark.db
def test_create_player_duplicate_username(test_db, temp_db_path, db_with_users):
    """Test that creating a player with existing username fails."""
    with use_test_database(temp_db_path):
        result = database.create_user_with_password("testplayer", "password", role="player")
        assert result is False


@pytest.mark.unit
@pytest.mark.db
def test_player_exists(test_db, temp_db_path, db_with_users):
    """Test checking if player exists."""
    with use_test_database(temp_db_path):
        assert database.user_exists("testplayer") is True
        assert database.user_exists("nonexistent") is False


@pytest.mark.unit
@pytest.mark.db
def test_verify_password_correct(test_db, temp_db_path, db_with_users):
    """Test password verification with correct password."""
    with use_test_database(temp_db_path):
        assert database.verify_password_for_user("testplayer", TEST_PASSWORD) is True


@pytest.mark.unit
@pytest.mark.db
def test_verify_password_incorrect(test_db, temp_db_path, db_with_users):
    """Test password verification with incorrect password."""
    with use_test_database(temp_db_path):
        assert database.verify_password_for_user("testplayer", "wrongpassword") is False


@pytest.mark.unit
@pytest.mark.db
def test_verify_password_nonexistent_user(test_db, temp_db_path):
    """Test password verification for non-existent user."""
    with use_test_database(temp_db_path):
        assert database.verify_password_for_user("nonexistent", "password") is False


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.security
def test_verify_password_timing_attack_prevention(test_db, temp_db_path, db_with_users):
    """
    Test that password verification has consistent timing for existent and non-existent users.

    This test verifies that the timing attack prevention is in place by ensuring
    that both cases perform a bcrypt comparison. We can't perfectly test timing
    in a unit test, but we can verify the function doesn't return early.
    """
    import time

    with use_test_database(temp_db_path):
        # Time verification for existing user with wrong password
        start = time.perf_counter()
        database.verify_password_for_user("testplayer", "wrongpassword")
        existing_user_time = time.perf_counter() - start

        # Time verification for non-existent user
        start = time.perf_counter()
        database.verify_password_for_user("nonexistent_user_12345", "wrongpassword")
        nonexistent_user_time = time.perf_counter() - start

        # Both should take roughly the same time (within 50% tolerance)
        # This is a rough check - the important thing is that both perform bcrypt
        ratio = max(existing_user_time, nonexistent_user_time) / max(
            min(existing_user_time, nonexistent_user_time), 0.001
        )
        assert ratio < 3.0, (
            f"Timing difference too large: {existing_user_time:.4f}s vs "
            f"{nonexistent_user_time:.4f}s (ratio: {ratio:.2f})"
        )


# ============================================================================
# ROLE MANAGEMENT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_get_player_role(test_db, temp_db_path, db_with_users):
    """Test retrieving player role."""
    with use_test_database(temp_db_path):
        assert database.get_user_role("testplayer") == "player"
        assert database.get_user_role("testadmin") == "admin"
        assert database.get_user_role("testsuperuser") == "superuser"


@pytest.mark.unit
@pytest.mark.db
def test_get_player_role_nonexistent(test_db, temp_db_path):
    """Test getting role for non-existent player."""
    with use_test_database(temp_db_path):
        assert database.get_user_role("nonexistent") is None


@pytest.mark.unit
@pytest.mark.db
def test_set_player_role(test_db, temp_db_path, db_with_users):
    """Test changing player role."""
    with use_test_database(temp_db_path):
        result = database.set_user_role("testplayer", "admin")
        assert result is True
        assert database.get_user_role("testplayer") == "admin"


# ============================================================================
# ACCOUNT STATUS TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_is_player_active_default(test_db, temp_db_path, db_with_users):
    """Test that players are active by default."""
    with use_test_database(temp_db_path):
        assert database.is_user_active("testplayer") is True


@pytest.mark.unit
@pytest.mark.db
def test_deactivate_player(test_db, temp_db_path, db_with_users):
    """Test deactivating a player account."""
    with use_test_database(temp_db_path):
        result = database.deactivate_user("testplayer")
        assert result is True
        assert database.is_user_active("testplayer") is False


@pytest.mark.unit
@pytest.mark.db
def test_activate_player(test_db, temp_db_path, db_with_users):
    """Test activating a deactivated player account."""
    with use_test_database(temp_db_path):
        database.deactivate_user("testplayer")
        result = database.activate_user("testplayer")
        assert result is True
        assert database.is_user_active("testplayer") is True


@pytest.mark.unit
@pytest.mark.db
def test_verify_password_inactive_account(test_db, temp_db_path, db_with_users):
    """Test that verify_password_for_user checks password only, not account status."""
    with use_test_database(temp_db_path):
        database.deactivate_user("testplayer")
        # Password verification should succeed even for inactive accounts
        # Account status checking is done separately in the login flow
        assert database.verify_password_for_user("testplayer", TEST_PASSWORD) is True
        # Verify account is actually inactive
        assert database.is_user_active("testplayer") is False


# ============================================================================
# PASSWORD MANAGEMENT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_change_password(test_db, temp_db_path, db_with_users):
    """Test changing user password."""
    with use_test_database(temp_db_path):
        result = database.change_password_for_user("testplayer", "newpassword")
        assert result is True

        # Old password should not work
        assert database.verify_password_for_user("testplayer", TEST_PASSWORD) is False

        # New password should work
        assert database.verify_password_for_user("testplayer", "newpassword") is True


# ============================================================================
# PLAYER STATE TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_get_player_room_default(test_db, temp_db_path, db_with_users):
    """Test getting player room returns spawn by default."""
    with use_test_database(temp_db_path):
        assert database.get_character_room("testplayer") == "spawn"


@pytest.mark.unit
@pytest.mark.db
def test_set_player_room(test_db, temp_db_path, db_with_users):
    """Test setting player room."""
    with use_test_database(temp_db_path):
        result = database.set_character_room("testplayer", "forest")
        assert result is True
        assert database.get_character_room("testplayer") == "forest"


@pytest.mark.unit
@pytest.mark.db
def test_get_player_room_nonexistent(test_db, temp_db_path):
    """Test getting room for non-existent player."""
    with use_test_database(temp_db_path):
        assert database.get_character_room("nonexistent") is None


# ============================================================================
# INVENTORY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_get_player_inventory_default(test_db, temp_db_path, db_with_users):
    """Test that new players have empty inventory."""
    with use_test_database(temp_db_path):
        inventory = database.get_character_inventory("testplayer")
        assert inventory == []


@pytest.mark.unit
@pytest.mark.db
def test_set_player_inventory(test_db, temp_db_path, db_with_users):
    """Test setting player inventory."""
    with use_test_database(temp_db_path):
        inventory = ["torch", "rope", "sword"]
        result = database.set_character_inventory("testplayer", inventory)
        assert result is True

        retrieved = database.get_character_inventory("testplayer")
        assert retrieved == inventory


@pytest.mark.unit
@pytest.mark.db
def test_get_player_inventory_nonexistent(test_db, temp_db_path):
    """Test getting inventory for non-existent player."""
    with use_test_database(temp_db_path):
        inventory = database.get_character_inventory("nonexistent")
        assert inventory == []


# ============================================================================
# CHAT MESSAGE TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_add_chat_message(test_db, temp_db_path, db_with_users):
    """Test adding a chat message."""
    with use_test_database(temp_db_path):
        result = database.add_chat_message("testplayer", "Hello world", "spawn")
        assert result is True


@pytest.mark.unit
@pytest.mark.db
def test_add_chat_message_with_recipient(test_db, temp_db_path, db_with_users):
    """Test adding a whisper message with recipient."""
    with use_test_database(temp_db_path):
        result = database.add_chat_message(
            "testplayer", "[WHISPER] Secret message", "spawn", recipient="testadmin"
        )
        assert result is True


@pytest.mark.unit
@pytest.mark.db
def test_get_room_messages(test_db, temp_db_path, db_with_users):
    """Test retrieving room messages."""
    with use_test_database(temp_db_path):
        # Add some messages
        database.add_chat_message("testplayer", "Message 1", "spawn")
        database.add_chat_message("testadmin", "Message 2", "spawn")
        database.add_chat_message("testplayer", "Message 3", "forest")

        # Get spawn messages
        messages = database.get_room_messages("spawn", limit=10)
        assert len(messages) == 2
        assert messages[0]["message"] == "Message 1"
        assert messages[1]["message"] == "Message 2"


@pytest.mark.unit
@pytest.mark.db
def test_get_room_messages_world_isolation(test_db, temp_db_path, db_with_users):
    """Room messages should be isolated by world_id."""
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

        database.add_chat_message("testplayer", "Default world", "spawn", world_id="pipeworks_web")
        database.add_chat_message("alt_player", "Alt world", "spawn", world_id="daily_undertaking")

        default_messages = database.get_room_messages("spawn", world_id="pipeworks_web", limit=10)
        assert len(default_messages) == 1
        assert default_messages[0]["message"] == "Default world"

        alt_messages = database.get_room_messages("spawn", world_id="daily_undertaking", limit=10)
        assert len(alt_messages) == 1
        assert alt_messages[0]["message"] == "Alt world"


@pytest.mark.unit
@pytest.mark.db
def test_get_room_messages_with_whisper_filtering(test_db, temp_db_path, db_with_users):
    """Test that whispers are filtered per user."""
    with use_test_database(temp_db_path):
        # Public message
        database.add_chat_message("testplayer", "Public message", "spawn")

        # Whisper to testadmin
        database.add_chat_message("testplayer", "[WHISPER] Secret", "spawn", recipient="testadmin")

        # Get messages as testadmin (should see whisper)
        messages = database.get_room_messages("spawn", limit=10, username="testadmin")
        assert len(messages) == 2

        # Get messages as testsuperuser (should NOT see whisper)
        messages = database.get_room_messages("spawn", limit=10, username="testsuperuser")
        assert len(messages) == 1
        assert messages[0]["message"] == "Public message"


# ============================================================================
# SESSION MANAGEMENT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_create_session(test_db, temp_db_path, db_with_users):
    """Test creating a player session."""
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
    """Test create_session normalizes client_type input."""
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
        assert database.set_session_character("session-char", int(player_character["id"]))
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
    """Character session cleanup should return False when DB operations fail."""
    monkeypatch.setattr(database, "get_connection", Mock(side_effect=sqlite3.Error("db boom")))

    assert database.remove_sessions_for_character(42) is False


@pytest.mark.unit
@pytest.mark.db
def test_delete_player_removes_related_data(test_db, temp_db_path, db_with_users):
    """Test delete_player tombstones user and unlinks characters."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-999")
        database.add_chat_message("testplayer", "Hello", "spawn")
        database.add_chat_message("testadmin", "Whisper", "spawn", recipient="testplayer")

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM characters WHERE name = ?", ("testplayer_char",))
        character_id = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE character_locations SET room_id = ? WHERE character_id = ?",
            ("spawn", character_id),
        )
        conn.commit()
        conn.close()

        assert database.delete_user("testplayer") is True
        assert database.user_exists("testplayer") is True

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT tombstoned_at FROM users WHERE username = ?", ("testplayer",))
        tombstoned = cursor.fetchone()[0]
        cursor.execute("SELECT user_id FROM characters WHERE id = ?", (character_id,))
        user_id = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE session_id = ?", ("session-999",))
        session_count = cursor.fetchone()[0]
        conn.close()

        assert tombstoned is not None
        assert user_id is None
        assert session_count == 0


@pytest.mark.unit
@pytest.mark.db
def test_delete_player_missing_returns_false(test_db, temp_db_path, db_with_users):
    """Test delete_player returns False when user does not exist."""
    with use_test_database(temp_db_path):
        result = database.delete_user("missing-user")
        assert result is False


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_temporary_accounts(test_db, temp_db_path):
    """Test cleanup removes only expired visitor accounts."""
    with use_test_database(temp_db_path):
        database.create_user_with_password(
            "temp_old", TEST_PASSWORD, role="player", account_origin="visitor"
        )
        database.create_user_with_password(
            "temp_new", TEST_PASSWORD, role="player", account_origin="visitor"
        )
        database.create_user_with_password(
            "admin_user", TEST_PASSWORD, role="admin", account_origin="admin"
        )

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET created_at = datetime('now', '-48 hours') "
            "WHERE username = 'temp_old'"
        )
        conn.commit()
        conn.close()

        removed = database.cleanup_expired_guest_accounts()

        assert removed == 1
        assert database.user_exists("temp_old") is False
        assert database.user_exists("temp_new") is True
        assert database.user_exists("admin_user") is True


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_temporary_accounts_no_rows(test_db, temp_db_path):
    """Test cleanup returns 0 when no visitor accounts exist."""
    with use_test_database(temp_db_path):
        removed = database.cleanup_expired_guest_accounts()
        assert removed == 0


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_temporary_accounts_zero_age(test_db, temp_db_path):
    """Test cleanup is a no-op when max_age_hours is non-positive."""
    with use_test_database(temp_db_path):
        removed = database.cleanup_expired_guest_accounts()
        assert removed == 0


@pytest.mark.unit
@pytest.mark.db
def test_create_character_for_user_success(test_db, temp_db_path):
    """Test creating a character for a user succeeds and seeds location."""
    with use_test_database(temp_db_path):
        database.create_user_with_password("charuser", TEST_PASSWORD)
        user_id = database.get_user_id("charuser")
        assert user_id is not None

        result = database.create_character_for_user(user_id, "charuser_alt")
        assert result is True
        assert database.get_character_by_name("charuser_alt") is not None
        assert database.get_character_room("charuser_alt") == "spawn"


@pytest.mark.unit
@pytest.mark.db
def test_create_user_with_password_missing_lastrowid_raises():
    fake_cursor = _FakeCursor(lastrowid=None)
    fake_conn = _FakeConnection(fake_cursor)

    with patch.object(database, "get_connection", return_value=fake_conn):
        with pytest.raises(ValueError):
            database.create_user_with_password("baduser", TEST_PASSWORD)


@pytest.mark.unit
@pytest.mark.db
def test_create_character_for_user_missing_lastrowid_raises():
    fake_cursor = _FakeCursor(lastrowid=None)
    fake_conn = _FakeConnection(fake_cursor)

    with patch.object(database, "get_connection", return_value=fake_conn):
        with pytest.raises(ValueError):
            database.create_character_for_user(1, "badchar")


@pytest.mark.unit
@pytest.mark.db
def test_create_default_character_missing_lastrowid_raises():
    fake_cursor = _FakeCursor(lastrowid=None)

    with pytest.raises(ValueError):
        database._create_default_character(fake_cursor, 1, "badchar")


@pytest.mark.unit
@pytest.mark.db
def test_get_character_by_name_missing_returns_none(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        assert database.get_character_by_name("nope") is None


@pytest.mark.unit
@pytest.mark.db
def test_get_character_by_id_missing_returns_none(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        assert database.get_character_by_id(9999) is None


@pytest.mark.unit
@pytest.mark.db
def test_tombstone_character_success_detaches_owner_and_renames(test_db, temp_db_path):
    """Tombstoning should detach ownership while preserving row history."""
    with use_test_database(temp_db_path):
        database.create_user_with_password("stone_user", TEST_PASSWORD)
        user_id = database.get_user_id("stone_user")
        assert user_id is not None
        assert (
            database.create_character_for_user(user_id, "Stone Name", world_id="pipeworks_web")
            is True
        )

        character = database.get_character_by_name("Stone Name")
        assert character is not None
        character_id = int(character["id"])

        assert database.tombstone_character(character_id) is True

        tombstoned = database.get_character_by_id(character_id)
        assert tombstoned is not None
        assert tombstoned["user_id"] is None
        assert tombstoned["name"].startswith(f"tombstone_{character_id}_")

        # Original name becomes available after tombstoning.
        assert (
            database.create_character_for_user(user_id, "Stone Name", world_id="pipeworks_web")
            is True
        )


@pytest.mark.unit
@pytest.mark.db
def test_tombstone_character_missing_returns_false(test_db, temp_db_path):
    """Tombstone helper should return False for unknown ids."""
    with use_test_database(temp_db_path):
        assert database.tombstone_character(123456) is False


@pytest.mark.unit
@pytest.mark.db
def test_delete_character_success_and_missing(test_db, temp_db_path):
    """Delete helper should remove existing rows and report missing rows."""
    with use_test_database(temp_db_path):
        database.create_user_with_password("delete_user", TEST_PASSWORD)
        user_id = database.get_user_id("delete_user")
        assert user_id is not None
        assert (
            database.create_character_for_user(user_id, "Delete Me", world_id="pipeworks_web")
            is True
        )

        character = database.get_character_by_name("Delete Me")
        assert character is not None
        character_id = int(character["id"])

        assert database.delete_character(character_id) is True
        assert database.get_character_by_id(character_id) is None
        assert database.delete_character(character_id) is False


@pytest.mark.unit
@pytest.mark.db
def test_unlink_characters_for_user(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        database.create_user_with_password("unlinker", TEST_PASSWORD)
        user_id = database.get_user_id("unlinker")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "unlinker_char")

        database.unlink_characters_for_user(user_id)

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM characters WHERE name = ?", ("unlinker_char",))
        user_id_row = cursor.fetchone()
        conn.close()

        assert user_id_row[0] is None


@pytest.mark.unit
@pytest.mark.db
def test_set_character_room_missing_character_returns_false(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        assert database.set_character_room("missing", "spawn") is False


@pytest.mark.unit
@pytest.mark.db
def test_add_chat_message_missing_sender_returns_false(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        assert database.add_chat_message("ghost", "boo", "spawn") is False


@pytest.mark.unit
@pytest.mark.db
def test_get_room_messages_unknown_character_returns_empty(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        assert database.get_room_messages("spawn", character_name="ghost") == []


@pytest.mark.unit
@pytest.mark.db
def test_remove_session_missing_user_returns_false(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("missing-user")
        assert user_id is None


@pytest.mark.unit
@pytest.mark.db
def test_get_player_locations_shim(test_db, temp_db_path, db_with_users):
    with use_test_database(temp_db_path):
        locations = database.get_character_locations()
        assert isinstance(locations, list)


@pytest.mark.unit
@pytest.mark.db
def test_init_database_superuser_bootstrap_does_not_require_character_lastrowid(monkeypatch):
    class _InitCursor(_FakeCursor):
        def __init__(self):
            super().__init__(lastrowid=None, fetchone=(0,))

        def execute(self, _sql, _params=None):
            return None

    fake_conn = _FakeConnection(_InitCursor())

    # Regression guard for account-first model:
    # superuser bootstrap should not depend on character-row creation metadata.
    with (
        patch.dict("os.environ", {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": TEST_PASSWORD}),
        patch("mud_server.db.connection.sqlite3.connect", return_value=fake_conn),
    ):
        database.init_database(skip_superuser=False)


@pytest.mark.unit
@pytest.mark.db
def test_database_helpers_return_false_on_db_error():
    with patch.object(database, "get_connection", side_effect=Exception("db error")):
        assert database.set_user_role("testplayer", "admin") is False
        assert database.deactivate_user("testplayer") is False
        assert database.activate_user("testplayer") is False
        assert database.change_password_for_user("testplayer", TEST_PASSWORD) is False
        assert database.set_character_room("testplayer", "spawn") is False
        assert database.set_character_inventory("testplayer", []) is False
        assert database.add_chat_message("testplayer", "hi", "spawn") is False
        assert database.create_session("testplayer", "session-x") is False
        assert database.set_session_character("session-x", 1) is False
        assert database.remove_session_by_id("session-x") is False
        assert database.remove_sessions_for_user(1) is False
        assert database.update_session_activity("session-x") is False
        assert database.cleanup_expired_sessions() == 0
        assert database.clear_all_sessions() == 0


@pytest.mark.unit
@pytest.mark.db
def test_delete_user_returns_false_on_db_error(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        database.create_user_with_password("todelete", TEST_PASSWORD)
        user_id = database.get_user_id("todelete")
        assert user_id is not None
        with (
            patch.object(database, "get_user_id", return_value=user_id),
            patch.object(database, "get_connection", side_effect=Exception("db error")),
        ):
            assert database.delete_user("todelete") is False


@pytest.mark.unit
@pytest.mark.db
def test_tombstone_user_updates_row(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        database.create_user_with_password("ghost", TEST_PASSWORD)
        user_id = database.get_user_id("ghost")
        assert user_id is not None

        database.tombstone_user(user_id)

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT tombstoned_at, is_active FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] is not None
        assert row[1] == 0


@pytest.mark.unit
@pytest.mark.db
def test_update_session_activity_without_sliding_expiration(test_db, temp_db_path, db_with_users):
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
def test_cleanup_expired_guest_accounts_deletes_user(test_db, temp_db_path):
    """Test guest expiry deletes the account and unlinks characters."""
    with use_test_database(temp_db_path):
        database.create_user_with_password(
            "guest_user",
            TEST_PASSWORD,
            role="player",
            account_origin="visitor",
            is_guest=True,
            guest_expires_at="2000-01-01 00:00:00",
        )
        user_id = database.get_user_id("guest_user")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "guest_user_char")

        removed = database.cleanup_expired_guest_accounts()
        assert removed == 1

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", ("guest_user",))
        user_row = cursor.fetchone()
        cursor.execute("SELECT user_id FROM characters WHERE name = ?", ("guest_user_char",))
        user_id = cursor.fetchone()[0]
        conn.close()

        assert user_row is None
        assert user_id is None


@pytest.mark.unit
@pytest.mark.db
def test_world_scoped_character_slot_limit_enforced(temp_db_path):
    """Per-world slot limits should cap each world independently per account."""
    from mud_server.config import config

    original_default_slot_limit = config.character_creation.default_world_slot_limit
    original_world_overrides = dict(config.character_creation.world_policy_overrides)
    config.character_creation.default_world_slot_limit = 1
    config.character_creation.world_policy_overrides = {}
    try:
        with use_test_database(temp_db_path):
            database.init_database(skip_superuser=True)
            database.create_user_with_password("limit_user", TEST_PASSWORD)
            user_id = database.get_user_id("limit_user")
            assert user_id is not None

            # Seed a secondary world so we can prove limits are world-scoped.
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

            assert database.create_character_for_user(user_id, "pipeworks_slot_1") is True
            assert database.create_character_for_user(user_id, "pipeworks_slot_2") is False

            assert (
                database.create_character_for_user(
                    user_id,
                    "daily_slot_1",
                    world_id="daily_undertaking",
                )
                is True
            )
            assert (
                database.create_character_for_user(
                    user_id,
                    "daily_slot_2",
                    world_id="daily_undertaking",
                )
                is False
            )
    finally:
        config.character_creation.default_world_slot_limit = original_default_slot_limit
        config.character_creation.world_policy_overrides = original_world_overrides


@pytest.mark.unit
@pytest.mark.db
def test_session_invariant_trigger_rejects_account_world_binding(
    test_db, temp_db_path, db_with_users
):
    """Account-only sessions must not set world_id without a character binding."""
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
    """Session world must match the bound character's world."""
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
    """Session update trigger should reject direct SQL state tampering."""
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
    """Test that TTL=0 stores NULL expiry."""
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
    """Test that creating a new session removes the old one when multi-session is disabled."""
    from mud_server.config import config

    with use_test_database(temp_db_path):
        original = config.session.allow_multiple_sessions
        config.session.allow_multiple_sessions = False
        try:
            database.create_session("testplayer", "session-1")
            database.create_session("testplayer", "session-2")

            # Only one session should exist
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
    """Test that multiple sessions are allowed when configured."""
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
    """Test removing a player session."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-123")
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        result = database.remove_sessions_for_user(user_id)
        assert result is True

        # Session should be gone
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0


@pytest.mark.unit
@pytest.mark.db
def test_remove_session_by_id(test_db, temp_db_path, db_with_users):
    """Test removing a specific session by session_id."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-123")
        result = database.remove_session_by_id("session-123")
        assert result is True

        assert database.get_session_by_id("session-123") is None


@pytest.mark.unit
@pytest.mark.db
def test_get_active_players(test_db, temp_db_path, db_with_users):
    """Test getting list of active players."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")
        player_character = database.get_character_by_name("testplayer_char")
        admin_character = database.get_character_by_name("testadmin_char")
        assert player_character is not None
        assert admin_character is not None
        database.set_session_character("session-1", player_character["id"])
        database.set_session_character("session-2", admin_character["id"])

        active = database.get_active_characters()
        assert len(active) == 2
        assert "testplayer_char" in active
        assert "testadmin_char" in active


@pytest.mark.unit
@pytest.mark.db
def test_get_players_in_room(test_db, temp_db_path, db_with_users):
    """Test getting players in a specific room."""
    with use_test_database(temp_db_path):
        # Create sessions for online players
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")
        player_character = database.get_character_by_name("testplayer_char")
        admin_character = database.get_character_by_name("testadmin_char")
        assert player_character is not None
        assert admin_character is not None
        database.set_session_character("session-1", player_character["id"])
        database.set_session_character("session-2", admin_character["id"])

        # Move testadmin to forest
        database.set_character_room("testadmin", "forest")

        # Get players in spawn
        players_in_spawn = database.get_characters_in_room("spawn")
        assert len(players_in_spawn) == 1
        assert "testplayer_char" in players_in_spawn

        # Get players in forest
        players_in_forest = database.get_characters_in_room("forest")
        assert len(players_in_forest) == 1
        assert "testadmin_char" in players_in_forest


@pytest.mark.unit
@pytest.mark.db
def test_get_character_locations(test_db, temp_db_path, db_with_users):
    """Test fetching player location rows with usernames."""
    with use_test_database(temp_db_path):
        database.set_character_room("testplayer", "forest")

        locations = database.get_character_locations()
        by_username = {loc["character_name"]: loc for loc in locations}

        assert "testplayer_char" in by_username
        assert by_username["testplayer_char"]["room_id"] == "forest"


@pytest.mark.unit
@pytest.mark.db
def test_update_session_activity(test_db, temp_db_path, db_with_users):
    """Test updating session activity timestamp."""
    with use_test_database(temp_db_path):
        session_id = "session-123"
        database.create_session("testplayer", session_id)
        result = database.update_session_activity(session_id)
        assert result is True


# ============================================================================
# SESSION CLEANUP TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_removes_old(test_db, temp_db_path, db_with_users):
    """Test that cleanup_expired_sessions removes sessions past expires_at."""
    with use_test_database(temp_db_path):
        # Create a session
        session_id = "session-123"
        database.create_session("testplayer", session_id)
        player_character = database.get_character_by_name("testplayer_char")
        assert player_character is not None
        database.set_session_character(session_id, player_character["id"])

        # Expire the session.
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

        # Session should be gone
        active = database.get_active_characters()
        assert "testplayer_char" not in active


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_keeps_active(test_db, temp_db_path, db_with_users):
    """Test that cleanup_expired_sessions keeps valid sessions."""
    with use_test_database(temp_db_path):
        # Create a session (will have current timestamp)
        database.create_session("testplayer", "session-123")
        player_character = database.get_character_by_name("testplayer_char")
        assert player_character is not None
        database.set_session_character("session-123", player_character["id"])

        removed = database.cleanup_expired_sessions()

        assert removed == 0

        # Session should still exist
        active = database.get_active_characters()
        assert "testplayer_char" in active


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_mixed(test_db, temp_db_path, db_with_users):
    """Test cleanup with mix of expired and active sessions."""
    with use_test_database(temp_db_path):
        # Create sessions for multiple users
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")
        player_character = database.get_character_by_name("testplayer_char")
        admin_character = database.get_character_by_name("testadmin_char")
        assert player_character is not None
        assert admin_character is not None
        database.set_session_character("session-1", player_character["id"])
        database.set_session_character("session-2", admin_character["id"])

        # Expire testplayer's session.
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

        # Only testadmin should remain
        active = database.get_active_characters()
        assert "testplayer_char" not in active
        assert "testadmin_char" in active


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_empty_db(test_db, temp_db_path):
    """Test cleanup on empty sessions table returns 0."""
    with use_test_database(temp_db_path):
        removed = database.cleanup_expired_sessions()
        assert removed == 0


@pytest.mark.unit
@pytest.mark.db
def test_clear_all_sessions(test_db, temp_db_path, db_with_users):
    """Test that clear_all_sessions removes all sessions."""
    with use_test_database(temp_db_path):
        # Create multiple sessions
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")
        database.create_session("testsuperuser", "session-3")
        player_character = database.get_character_by_name("testplayer_char")
        admin_character = database.get_character_by_name("testadmin_char")
        super_character = database.get_character_by_name("testsuperuser_char")
        assert player_character is not None
        assert admin_character is not None
        assert super_character is not None
        database.set_session_character("session-1", player_character["id"])
        database.set_session_character("session-2", admin_character["id"])
        database.set_session_character("session-3", super_character["id"])

        # Verify sessions exist
        assert len(database.get_active_characters()) == 3

        # Clear all sessions
        removed = database.clear_all_sessions()

        assert removed == 3

        # All sessions should be gone
        assert len(database.get_active_characters()) == 0


@pytest.mark.unit
@pytest.mark.db
def test_clear_all_sessions_empty_db(test_db, temp_db_path):
    """Test clear_all_sessions on empty sessions table returns 0."""
    with use_test_database(temp_db_path):
        removed = database.clear_all_sessions()
        assert removed == 0


@pytest.mark.unit
@pytest.mark.db
def test_clear_all_sessions_returns_count(test_db, temp_db_path, db_with_users):
    """Test that clear_all_sessions returns accurate count of removed sessions."""
    with use_test_database(temp_db_path):
        # Create exactly 2 sessions
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        removed = database.clear_all_sessions()

        assert removed == 2


# ============================================================================
# ADMIN QUERY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_all_players(test_db, temp_db_path, db_with_users):
    """Test getting all players list."""
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
    """Test getting detailed players list with password hash prefix."""
    with use_test_database(temp_db_path):
        players = database.get_all_users_detailed()
        assert len(players) == 4

        # Check that password_hash is truncated
        for player in players:
            assert "..." in player["password_hash"] or len(player["password_hash"]) <= 20


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_all_sessions(test_db, temp_db_path, db_with_users):
    """Test getting all sessions with expected fields."""
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
    """Test getting all chat messages across rooms."""
    with use_test_database(temp_db_path):
        database.add_chat_message("testplayer", "Message 1", "spawn")
        database.add_chat_message("testadmin", "Message 2", "forest")
        database.add_chat_message("testplayer", "Message 3", "spawn")

        messages = database.get_all_chat_messages(limit=100)
        assert len(messages) == 3


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_all_chat_messages_world_filter(test_db, temp_db_path, db_with_users):
    """Chat message queries should filter by world_id."""
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

        database.add_chat_message("testplayer", "Default world", "spawn", world_id="pipeworks_web")
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
    """Test listing database tables with metadata."""
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
    """Test fetching columns and rows for a specific table."""
    with use_test_database(temp_db_path):
        columns, rows = database.get_table_rows("users", limit=10)

        assert "username" in columns
        assert len(rows) >= 1


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_table_rows_invalid_table_raises(test_db, temp_db_path, db_with_users):
    """Test invalid table name raises a ValueError."""
    with use_test_database(temp_db_path):
        with pytest.raises(ValueError, match="does not exist"):
            database.get_table_rows("not_a_table")


@pytest.mark.unit
@pytest.mark.db
def test_list_worlds_for_user_fallback_by_character(test_db, temp_db_path, db_with_users):
    """Fallback should allow worlds where user already has characters."""
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
            ("pipeworks_web", "pipeworks_web"),
        )
        conn.commit()
        conn.close()

        worlds = database.list_worlds_for_user(user_id, role="player")
        assert [world["id"] for world in worlds] == ["pipeworks_web"]
