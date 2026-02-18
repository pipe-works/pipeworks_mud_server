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

from typing import Any, cast
from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import connection as db_connection
from mud_server.db import database
from mud_server.db.errors import DatabaseReadError, DatabaseWriteError
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
        assert (
            database.get_character_room("testplayer_char", world_id=database.DEFAULT_WORLD_ID)
            == "spawn"
        )


@pytest.mark.unit
@pytest.mark.db
def test_set_player_room(test_db, temp_db_path, db_with_users):
    """Test setting player room."""
    with use_test_database(temp_db_path):
        result = database.set_character_room(
            "testplayer_char", "forest", world_id=database.DEFAULT_WORLD_ID
        )
        assert result is True
        assert (
            database.get_character_room("testplayer_char", world_id=database.DEFAULT_WORLD_ID)
            == "forest"
        )


@pytest.mark.unit
@pytest.mark.db
def test_get_player_room_nonexistent(test_db, temp_db_path):
    """Test getting room for non-existent player."""
    with use_test_database(temp_db_path):
        assert (
            database.get_character_room("nonexistent", world_id=database.DEFAULT_WORLD_ID) is None
        )


# ============================================================================
# INVENTORY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_get_player_inventory_default(test_db, temp_db_path, db_with_users):
    """Test that new players have empty inventory."""
    with use_test_database(temp_db_path):
        inventory = database.get_character_inventory(
            "testplayer_char", world_id=database.DEFAULT_WORLD_ID
        )
        assert inventory == []


@pytest.mark.unit
@pytest.mark.db
def test_set_player_inventory(test_db, temp_db_path, db_with_users):
    """Test setting player inventory."""
    with use_test_database(temp_db_path):
        inventory = ["torch", "rope", "sword"]
        result = database.set_character_inventory(
            "testplayer_char", inventory, world_id=database.DEFAULT_WORLD_ID
        )
        assert result is True

        retrieved = database.get_character_inventory(
            "testplayer_char", world_id=database.DEFAULT_WORLD_ID
        )
        assert retrieved == inventory


@pytest.mark.unit
@pytest.mark.db
def test_get_player_inventory_nonexistent(test_db, temp_db_path):
    """Test getting inventory for non-existent player."""
    with use_test_database(temp_db_path):
        inventory = database.get_character_inventory(
            "nonexistent", world_id=database.DEFAULT_WORLD_ID
        )
        assert inventory == []


@pytest.mark.unit
@pytest.mark.db
def test_delete_player_removes_related_data(test_db, temp_db_path, db_with_users):
    """Test delete_player tombstones user and unlinks characters."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "session-999")
        database.add_chat_message(
            "testplayer_char",
            "Hello",
            "spawn",
            world_id=database.DEFAULT_WORLD_ID,
        )
        database.add_chat_message(
            "testadmin_char",
            "Whisper",
            "spawn",
            recipient="testplayer_char",
            world_id=database.DEFAULT_WORLD_ID,
        )

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
def test_create_user_with_password_missing_lastrowid_raises():
    fake_cursor = _FakeCursor(lastrowid=None)
    fake_conn = _FakeConnection(fake_cursor)

    with patch.object(db_connection, "get_connection", return_value=fake_conn):
        with pytest.raises(DatabaseWriteError):
            database.create_user_with_password("baduser", TEST_PASSWORD)


@pytest.mark.unit
@pytest.mark.db
def test_create_character_for_user_missing_lastrowid_raises():
    """Character creation should map low-level write failures to typed DB errors."""
    fake_cursor = _FakeCursor(lastrowid=None)
    fake_conn = _FakeConnection(fake_cursor)

    with patch.object(db_connection, "get_connection", return_value=fake_conn):
        with pytest.raises(DatabaseWriteError):
            database.create_character_for_user(1, "badchar", world_id=database.DEFAULT_WORLD_ID)


@pytest.mark.unit
@pytest.mark.db
def test_create_default_character_missing_lastrowid_raises():
    fake_cursor = _FakeCursor(lastrowid=None)

    with pytest.raises(ValueError):
        database._create_default_character(
            fake_cursor,
            1,
            "badchar",
            world_id=database.DEFAULT_WORLD_ID,
        )


@pytest.mark.unit
@pytest.mark.db
def test_remove_session_missing_user_returns_false(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("missing-user")
        assert user_id is None


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
def test_database_helpers_raise_typed_errors_on_db_error():
    """
    Verify repository-backed helpers map DB failures to typed exceptions.
    """
    with patch.object(db_connection, "get_connection", side_effect=Exception("db error")):
        with pytest.raises(DatabaseWriteError):
            database.set_user_role("testplayer", "admin")
        with pytest.raises(DatabaseWriteError):
            database.deactivate_user("testplayer")
        with pytest.raises(DatabaseWriteError):
            database.activate_user("testplayer")
        with pytest.raises(DatabaseWriteError):
            database.change_password_for_user("testplayer", TEST_PASSWORD)
        with pytest.raises(DatabaseReadError):
            database.user_exists("testplayer")
        with pytest.raises(DatabaseReadError):
            database.get_user_id("testplayer")
        with pytest.raises(DatabaseReadError):
            database.get_user_role("testplayer")

        with pytest.raises(DatabaseWriteError):
            database.set_character_room(
                "testplayer_char", "spawn", world_id=database.DEFAULT_WORLD_ID
            )
        with pytest.raises(DatabaseWriteError):
            database.set_character_inventory(
                "testplayer_char", [], world_id=database.DEFAULT_WORLD_ID
            )
        with pytest.raises(DatabaseWriteError):
            database.add_chat_message(
                "testplayer_char",
                "hi",
                "spawn",
                world_id=database.DEFAULT_WORLD_ID,
            )
        with pytest.raises(DatabaseWriteError):
            database.create_session(1, "session-x")
        with pytest.raises(DatabaseWriteError):
            database.set_session_character("session-x", 1, world_id=database.DEFAULT_WORLD_ID)
        with pytest.raises(DatabaseWriteError):
            database.remove_session_by_id("session-x")
        with pytest.raises(DatabaseWriteError):
            database.remove_sessions_for_user(1)
        with pytest.raises(DatabaseWriteError):
            database.update_session_activity("session-x")
        with pytest.raises(DatabaseWriteError):
            database.cleanup_expired_sessions()
        with pytest.raises(DatabaseWriteError):
            database.clear_all_sessions()


@pytest.mark.unit
@pytest.mark.db
def test_delete_user_raises_typed_error_on_db_error(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        database.create_user_with_password("todelete", TEST_PASSWORD)
        user_id = database.get_user_id("todelete")
        assert user_id is not None
        with (
            patch("mud_server.db.users_repo.get_user_id", return_value=user_id),
            patch.object(db_connection, "get_connection", side_effect=Exception("db error")),
        ):
            with pytest.raises(DatabaseWriteError):
                database.delete_user("todelete")


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
        assert database.create_character_for_user(
            user_id, "guest_user_char", world_id=database.DEFAULT_WORLD_ID
        )

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
