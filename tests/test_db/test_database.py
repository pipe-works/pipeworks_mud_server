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
from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD

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
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'")
        assert cursor.fetchone() is not None

        # Check sessions table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        assert cursor.fetchone() is not None

        # Check chat_messages table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
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
            assert database.player_exists("envadmin")
            assert database.get_player_role("envadmin") == "superuser"
            assert database.verify_password_for_user("envadmin", "securepass123")


@pytest.mark.unit
@pytest.mark.db
def test_init_database_no_superuser_without_env_vars(temp_db_path):
    """Test that init_database does NOT create superuser without environment variables."""
    with use_test_database(temp_db_path):
        # Ensure env vars are not set
        with patch.dict("os.environ", {}, clear=True):
            database.init_database()

            # No default admin should be created
            assert not database.player_exists("admin")

            # Check that tables were still created
            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'")
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
            assert not database.player_exists("admin")

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
        result = database.create_player_with_password("newuser", TEST_PASSWORD, "player")
        assert result is True

        # Verify player exists
        assert database.player_exists("newuser")

        # Verify password
        assert database.verify_password_for_user("newuser", TEST_PASSWORD)

        # Verify role
        assert database.get_player_role("newuser") == "player"


@pytest.mark.unit
@pytest.mark.db
def test_create_player_duplicate_username(test_db, temp_db_path, db_with_users):
    """Test that creating a player with existing username fails."""
    with use_test_database(temp_db_path):
        result = database.create_player_with_password("testplayer", "password", "player")
        assert result is False


@pytest.mark.unit
@pytest.mark.db
def test_player_exists(test_db, temp_db_path, db_with_users):
    """Test checking if player exists."""
    with use_test_database(temp_db_path):
        assert database.player_exists("testplayer") is True
        assert database.player_exists("nonexistent") is False


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
        assert database.get_player_role("testplayer") == "player"
        assert database.get_player_role("testadmin") == "admin"
        assert database.get_player_role("testsuperuser") == "superuser"


@pytest.mark.unit
@pytest.mark.db
def test_get_player_role_nonexistent(test_db, temp_db_path):
    """Test getting role for non-existent player."""
    with use_test_database(temp_db_path):
        assert database.get_player_role("nonexistent") is None


@pytest.mark.unit
@pytest.mark.db
def test_set_player_role(test_db, temp_db_path, db_with_users):
    """Test changing player role."""
    with use_test_database(temp_db_path):
        result = database.set_player_role("testplayer", "admin")
        assert result is True
        assert database.get_player_role("testplayer") == "admin"


# ============================================================================
# ACCOUNT STATUS TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_is_player_active_default(test_db, temp_db_path, db_with_users):
    """Test that players are active by default."""
    with use_test_database(temp_db_path):
        assert database.is_player_active("testplayer") is True


@pytest.mark.unit
@pytest.mark.db
def test_deactivate_player(test_db, temp_db_path, db_with_users):
    """Test deactivating a player account."""
    with use_test_database(temp_db_path):
        result = database.deactivate_player("testplayer")
        assert result is True
        assert database.is_player_active("testplayer") is False


@pytest.mark.unit
@pytest.mark.db
def test_activate_player(test_db, temp_db_path, db_with_users):
    """Test activating a deactivated player account."""
    with use_test_database(temp_db_path):
        database.deactivate_player("testplayer")
        result = database.activate_player("testplayer")
        assert result is True
        assert database.is_player_active("testplayer") is True


@pytest.mark.unit
@pytest.mark.db
def test_verify_password_inactive_account(test_db, temp_db_path, db_with_users):
    """Test that verify_password_for_user checks password only, not account status."""
    with use_test_database(temp_db_path):
        database.deactivate_player("testplayer")
        # Password verification should succeed even for inactive accounts
        # Account status checking is done separately in the login flow
        assert database.verify_password_for_user("testplayer", TEST_PASSWORD) is True
        # Verify account is actually inactive
        assert database.is_player_active("testplayer") is False


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
        assert database.get_player_room("testplayer") == "spawn"


@pytest.mark.unit
@pytest.mark.db
def test_set_player_room(test_db, temp_db_path, db_with_users):
    """Test setting player room."""
    with use_test_database(temp_db_path):
        result = database.set_player_room("testplayer", "forest")
        assert result is True
        assert database.get_player_room("testplayer") == "forest"


@pytest.mark.unit
@pytest.mark.db
def test_get_player_room_nonexistent(test_db, temp_db_path):
    """Test getting room for non-existent player."""
    with use_test_database(temp_db_path):
        assert database.get_player_room("nonexistent") is None


# ============================================================================
# INVENTORY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.db
def test_get_player_inventory_default(test_db, temp_db_path, db_with_users):
    """Test that new players have empty inventory."""
    with use_test_database(temp_db_path):
        inventory = database.get_player_inventory("testplayer")
        assert inventory == []


@pytest.mark.unit
@pytest.mark.db
def test_set_player_inventory(test_db, temp_db_path, db_with_users):
    """Test setting player inventory."""
    with use_test_database(temp_db_path):
        inventory = ["torch", "rope", "sword"]
        result = database.set_player_inventory("testplayer", inventory)
        assert result is True

        retrieved = database.get_player_inventory("testplayer")
        assert retrieved == inventory


@pytest.mark.unit
@pytest.mark.db
def test_get_player_inventory_nonexistent(test_db, temp_db_path):
    """Test getting inventory for non-existent player."""
    with use_test_database(temp_db_path):
        inventory = database.get_player_inventory("nonexistent")
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

        players = database.get_all_players_detailed()
        matching = [player for player in players if player["username"] == "testplayer"]
        assert matching
        assert matching[0]["last_login"] is not None


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
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE username = ?", ("testplayer",))
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
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE username = ?", ("testplayer",))
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
        result = database.remove_session("testplayer")
        assert result is True

        # Session should be gone
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE username = ?", ("testplayer",))
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

        active = database.get_active_players()
        assert len(active) == 2
        assert "testplayer" in active
        assert "testadmin" in active


@pytest.mark.unit
@pytest.mark.db
def test_get_players_in_room(test_db, temp_db_path, db_with_users):
    """Test getting players in a specific room."""
    with use_test_database(temp_db_path):
        # Create sessions for online players
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        # Move testadmin to forest
        database.set_player_room("testadmin", "forest")

        # Get players in spawn
        players_in_spawn = database.get_players_in_room("spawn")
        assert len(players_in_spawn) == 1
        assert "testplayer" in players_in_spawn

        # Get players in forest
        players_in_forest = database.get_players_in_room("forest")
        assert len(players_in_forest) == 1
        assert "testadmin" in players_in_forest


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
        active = database.get_active_players()
        assert "testplayer" not in active


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_keeps_active(test_db, temp_db_path, db_with_users):
    """Test that cleanup_expired_sessions keeps valid sessions."""
    with use_test_database(temp_db_path):
        # Create a session (will have current timestamp)
        database.create_session("testplayer", "session-123")

        removed = database.cleanup_expired_sessions()

        assert removed == 0

        # Session should still exist
        active = database.get_active_players()
        assert "testplayer" in active


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_mixed(test_db, temp_db_path, db_with_users):
    """Test cleanup with mix of expired and active sessions."""
    with use_test_database(temp_db_path):
        # Create sessions for multiple users
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        # Expire testplayer's session.
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET expires_at = datetime('now', '-10 minutes') " "WHERE username = ?",
            ("testplayer",),
        )
        conn.commit()
        conn.close()

        removed = database.cleanup_expired_sessions()

        assert removed == 1

        # Only testadmin should remain
        active = database.get_active_players()
        assert "testplayer" not in active
        assert "testadmin" in active


@pytest.mark.unit
@pytest.mark.db
def test_cleanup_expired_sessions_empty_db(test_db, temp_db_path):
    """Test cleanup on empty sessions table returns 0."""
    with use_test_database(temp_db_path):
        removed = database.cleanup_expired_sessions()
        assert removed == 0


@pytest.mark.unit
@pytest.mark.db
def test_session_schema_migration_from_legacy(temp_db_path):
    """Test legacy sessions schema is migrated with expiry populated."""
    from mud_server.config import config

    original_ttl = config.session.ttl_minutes
    config.session.ttl_minutes = 60

    try:
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                session_id TEXT UNIQUE NOT NULL,
                connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "INSERT INTO sessions (username, session_id) VALUES (?, ?)",
            ("legacy-user", "legacy-session"),
        )
        conn.commit()
        conn.close()

        with use_test_database(temp_db_path):
            database.init_database(skip_superuser=True)

            session = database.get_session_by_id("legacy-session")
            assert session is not None
            assert session["username"] == "legacy-user"
            assert session["expires_at"] is not None
    finally:
        config.session.ttl_minutes = original_ttl


@pytest.mark.unit
@pytest.mark.db
def test_clear_all_sessions(test_db, temp_db_path, db_with_users):
    """Test that clear_all_sessions removes all sessions."""
    with use_test_database(temp_db_path):
        # Create multiple sessions
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")
        database.create_session("testsuperuser", "session-3")

        # Verify sessions exist
        assert len(database.get_active_players()) == 3

        # Clear all sessions
        removed = database.clear_all_sessions()

        assert removed == 3

        # All sessions should be gone
        assert len(database.get_active_players()) == 0


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
        players = database.get_all_players()
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
        players = database.get_all_players_detailed()
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
def test_list_tables(test_db, temp_db_path, db_with_users):
    """Test listing database tables with metadata."""
    with use_test_database(temp_db_path):
        tables = database.list_tables()
        table_names = {table["name"] for table in tables}

        assert {"players", "sessions", "chat_messages"}.issubset(table_names)
        assert all("columns" in table for table in tables)
        assert all("row_count" in table for table in tables)


@pytest.mark.unit
@pytest.mark.db
@pytest.mark.admin
def test_get_table_rows(test_db, temp_db_path, db_with_users):
    """Test fetching columns and rows for a specific table."""
    with use_test_database(temp_db_path):
        columns, rows = database.get_table_rows("players", limit=10)

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
