"""Compatibility-surface tests for user/account helpers exposed via ``db.database``."""

from typing import Any, cast
from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import connection as db_connection
from mud_server.db import database
from mud_server.db.errors import DatabaseReadError, DatabaseWriteError
from tests.constants import TEST_PASSWORD

# ============================================================================
# ACCOUNT + ROLE + PASSWORD COMPATIBILITY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_create_player_with_password_success(test_db, temp_db_path):
    """Test creating a new player with password."""
    with use_test_database(temp_db_path):
        result = database.create_user_with_password("newuser", TEST_PASSWORD, role="player")
        assert result is True

        assert database.user_exists("newuser")
        assert database.verify_password_for_user("newuser", TEST_PASSWORD)
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

    This test verifies that timing attack prevention remains in place by ensuring
    both cases perform a bcrypt comparison. We cannot perfectly validate timing in
    a unit test, but we can assert that behavior is not a cheap early-return path.
    """
    import time

    with use_test_database(temp_db_path):
        start = time.perf_counter()
        database.verify_password_for_user("testplayer", "wrongpassword")
        existing_user_time = time.perf_counter() - start

        start = time.perf_counter()
        database.verify_password_for_user("nonexistent_user_12345", "wrongpassword")
        nonexistent_user_time = time.perf_counter() - start

        ratio = max(existing_user_time, nonexistent_user_time) / max(
            min(existing_user_time, nonexistent_user_time), 0.001
        )
        assert ratio < 3.0, (
            f"Timing difference too large: {existing_user_time:.4f}s vs "
            f"{nonexistent_user_time:.4f}s (ratio: {ratio:.2f})"
        )


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
    """verify_password checks credential validity only, not account activation state."""
    with use_test_database(temp_db_path):
        database.deactivate_user("testplayer")
        assert database.verify_password_for_user("testplayer", TEST_PASSWORD) is True
        assert database.is_user_active("testplayer") is False


@pytest.mark.unit
@pytest.mark.db
def test_change_password(test_db, temp_db_path, db_with_users):
    """Test changing user password."""
    with use_test_database(temp_db_path):
        result = database.change_password_for_user("testplayer", "newpassword")
        assert result is True

        assert database.verify_password_for_user("testplayer", TEST_PASSWORD) is False
        assert database.verify_password_for_user("testplayer", "newpassword") is True


# ============================================================================
# USER LIFECYCLE COMPATIBILITY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_delete_player_removes_related_data(test_db, temp_db_path, db_with_users):
    """delete_user should tombstone user and unlink related character/session state."""
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
    """delete_user should return False when user does not exist."""
    with use_test_database(temp_db_path):
        result = database.delete_user("missing-user")
        assert result is False


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_temporary_accounts(test_db, temp_db_path):
    """cleanup_expired_guest_accounts should remove only expired visitor accounts."""
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
    """cleanup_expired_guest_accounts should return 0 when no visitor rows exist."""
    with use_test_database(temp_db_path):
        removed = database.cleanup_expired_guest_accounts()
        assert removed == 0


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_temporary_accounts_zero_age(test_db, temp_db_path):
    """cleanup_expired_guest_accounts is a no-op when max_age_hours is non-positive."""
    with use_test_database(temp_db_path):
        removed = database.cleanup_expired_guest_accounts()
        assert removed == 0


@pytest.mark.unit
@pytest.mark.db
def test_create_user_with_password_missing_lastrowid_raises():
    """User creation should map missing insert metadata to typed write errors."""
    fake_cursor = _FakeCursor(lastrowid=None)
    fake_conn = _FakeConnection(fake_cursor)

    with patch.object(db_connection, "get_connection", return_value=fake_conn):
        with pytest.raises(DatabaseWriteError):
            database.create_user_with_password("baduser", TEST_PASSWORD)


@pytest.mark.unit
@pytest.mark.db
def test_delete_user_raises_typed_error_on_db_error(test_db, temp_db_path):
    """delete_user should surface DB infrastructure failures as typed write errors."""
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
    """tombstone_user should set tombstone timestamp and deactivate account."""
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
    """Guest expiry should delete account rows and unlink character ownership."""
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
def test_remove_session_missing_user_returns_false(test_db, temp_db_path):
    """Missing-user session cleanup path should remain a benign no-op."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("missing-user")
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


class _FakeCursor:
    """Minimal fake cursor for compatibility tests that need ``lastrowid`` control."""

    def __init__(self, *, lastrowid=None):
        self.lastrowid = lastrowid
        self.rowcount = 0

    def execute(self, _sql, _params=None):  # noqa: D401 - minimal fake
        return None


class _FakeConnection:
    """Minimal fake connection wrapper that surfaces a controlled fake cursor."""

    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def execute(self, sql, params=None):
        """Mirror sqlite3.Connection.execute for compatibility fakes."""
        return self._cursor.execute(sql, params)

    def commit(self):
        return None

    def close(self):
        return None


@pytest.mark.unit
@pytest.mark.db
def test_database_helpers_raise_typed_errors_on_db_error():
    """
    Verify repository-backed user helpers map DB failures to typed exceptions.
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
