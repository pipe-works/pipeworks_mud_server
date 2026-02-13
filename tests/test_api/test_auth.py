"""
Unit tests for authentication module (mud_server/api/auth.py).

Tests cover:
- Session lookup and validation against the database
- Expiration enforcement and sliding expiry updates
- Permission-based validation
- Session lifecycle helpers
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from mud_server.api.auth import (
    clear_all_sessions,
    get_active_session_count,
    get_username_and_role_from_session,
    get_username_from_session,
    remove_session,
    validate_session,
    validate_session_for_game,
    validate_session_with_permission,
)
from mud_server.api.permissions import Permission
from mud_server.config import config, use_test_database
from mud_server.db import database


@pytest.fixture
def session_config_defaults():
    """Ensure session config is reset after each test."""
    original_ttl = config.session.ttl_minutes
    original_sliding = config.session.sliding_expiration
    original_multi = config.session.allow_multiple_sessions

    yield

    config.session.ttl_minutes = original_ttl
    config.session.sliding_expiration = original_sliding
    config.session.allow_multiple_sessions = original_multi


@pytest.fixture
def db_with_session(test_db, db_with_users):
    """Create a valid session for testplayer and return its session_id."""
    session_id = "session-player"
    database.create_session("testplayer", session_id)
    return session_id


# =========================================================================
# SESSION LOOKUP TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_from_session_existing(test_db, db_with_users, db_with_session):
    username = get_username_from_session(db_with_session)
    assert username == "testplayer"


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_from_session_nonexistent(test_db, db_with_users):
    assert get_username_from_session("invalid-session") is None


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_and_role_from_session_existing(test_db, db_with_users, db_with_session):
    session_data = get_username_and_role_from_session(db_with_session)
    assert session_data == ("testplayer", "player")


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_and_role_from_session_nonexistent(test_db, db_with_users):
    assert get_username_and_role_from_session("invalid-session") is None


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_and_role_from_session_missing_user():
    with (
        patch("mud_server.api.auth._get_valid_session", return_value={"user_id": 999}),
        patch.object(database, "get_username_by_id", return_value=None),
    ):
        assert get_username_and_role_from_session("session") is None


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_and_role_from_session_missing_role():
    with (
        patch("mud_server.api.auth._get_valid_session", return_value={"user_id": 123}),
        patch.object(database, "get_username_by_id", return_value="testplayer"),
        patch.object(database, "get_user_role", return_value=None),
    ):
        assert get_username_and_role_from_session("session") is None


# =========================================================================
# SESSION VALIDATION TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_success(test_db, db_with_users, db_with_session):
    _user_id, username, role = validate_session(db_with_session)
    assert username == "testplayer"
    assert role == "player"


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_invalid(test_db, db_with_users):
    with pytest.raises(HTTPException) as exc_info:
        validate_session("invalid-session")

    assert exc_info.value.status_code == 401
    assert "Invalid or expired session" in str(exc_info.value.detail)


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_expired(test_db, db_with_users, session_config_defaults):
    session_id = "expired-session"
    database.create_session("testplayer", session_id)

    # Force expiry into the past.
    conn = database.get_connection()
    cursor = conn.cursor()
    expired_ts = (datetime.now(UTC) - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
        (expired_ts, session_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException):
        validate_session(session_id)

    # Session should be removed after expiration check.
    assert database.get_session_by_id(session_id) is None


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_expired_on_bad_timestamp(test_db, db_with_users):
    session_id = "bad-expiry-session"
    database.create_session("testplayer", session_id)

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
        ("not-a-timestamp", session_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException):
        validate_session(session_id)

    assert database.get_session_by_id(session_id) is None


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_updates_activity_and_extends_expiry(
    test_db, db_with_users, session_config_defaults
):
    config.session.ttl_minutes = 480
    config.session.sliding_expiration = True

    session_id = "sliding-session"
    database.create_session("testplayer", session_id)

    before = database.get_session_by_id(session_id)
    assert before is not None

    validate_session(session_id)

    after = database.get_session_by_id(session_id)
    assert after is not None
    assert after["expires_at"] >= before["expires_at"]


# =========================================================================
# PERMISSION-BASED VALIDATION TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_with_permission_success(test_db, db_with_users):
    session_id = "admin-session"
    database.create_session("testadmin", session_id)

    _user_id, username, role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
    assert username == "testadmin"
    assert role == "admin"


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_with_permission_insufficient(test_db, db_with_users):
    session_id = "player-session"
    database.create_session("testplayer", session_id)

    with pytest.raises(HTTPException) as exc_info:
        validate_session_with_permission(session_id, Permission.MANAGE_USERS)

    assert exc_info.value.status_code == 403
    assert "Insufficient permissions" in str(exc_info.value.detail)


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_with_permission_invalid_session(test_db, db_with_users):
    with pytest.raises(HTTPException) as exc_info:
        validate_session_with_permission("invalid-session", Permission.VIEW_LOGS)

    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_with_permission_superuser_has_all(test_db, db_with_users):
    session_id = "superuser-session"
    database.create_session("testsuperuser", session_id)

    _user_id, username, role = validate_session_with_permission(session_id, Permission.MANAGE_USERS)
    assert username == "testsuperuser"
    assert role == "superuser"


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_and_role_returns_none_for_missing_role(test_db):
    session_id = "orphaned-session"
    database.create_session("missing-user", session_id)

    assert get_username_and_role_from_session(session_id) is None


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_rejects_missing_role(test_db):
    session_id = "missing-role-session"
    database.create_session("missing-user", session_id)

    with pytest.raises(HTTPException) as exc_info:
        validate_session(session_id)

    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_rejects_missing_user():
    with (
        patch("mud_server.api.auth._get_valid_session", return_value={"user_id": 999}),
        patch.object(database, "get_username_by_id", return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            validate_session("session")

    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_rejects_missing_role_lookup():
    with (
        patch("mud_server.api.auth._get_valid_session", return_value={"user_id": 123}),
        patch.object(database, "get_username_by_id", return_value="testplayer"),
        patch.object(database, "get_user_role", return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            validate_session("session")

    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_for_game_auto_selects_single_character(test_db, db_with_users):
    session_id = "game-session"
    database.create_session("testplayer", session_id)
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET character_id = NULL WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

    with patch.object(
        database, "set_session_character", wraps=database.set_session_character
    ) as spy:
        (
            user_id,
            username,
            role,
            character_id,
            character_name,
            world_id,
        ) = validate_session_for_game(session_id)

        assert spy.called is True

    assert username == "testplayer"
    assert role == "player"
    assert character_id is not None
    assert character_name == "testplayer_char"
    assert world_id is not None
    session = database.get_session_by_id(session_id)
    assert session is not None
    assert session["character_id"] == character_id


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_for_game_requires_selection_when_multiple(test_db, db_with_users):
    user_id = database.get_user_id("testplayer")
    assert user_id is not None
    database.create_character_for_user(user_id, "altplayer")

    session_id = "multi-char-session"
    database.create_session("testplayer", session_id)

    with pytest.raises(HTTPException) as exc_info:
        validate_session_for_game(session_id)

    assert exc_info.value.status_code == 409


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_for_game_missing_character_row(test_db, db_with_users):
    session_id = "missing-character-session"
    database.create_session("testplayer", session_id)

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET character_id = ? WHERE session_id = ?",
        (9999, session_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException) as exc_info:
        validate_session_for_game(session_id)

    assert exc_info.value.status_code == 409


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_for_game_missing_user(test_db, temp_db_path):
    with use_test_database(temp_db_path):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (user_id, character_id, session_id, created_at, last_activity)
            VALUES (?, NULL, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (999, "orphan-session"),
        )
        conn.commit()
        conn.close()

        with pytest.raises(HTTPException) as exc_info:
            validate_session_for_game("orphan-session")

    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_for_game_missing_role(test_db, temp_db_path, db_with_users):
    with use_test_database(temp_db_path):
        session_id = "missing-role-session"
        database.create_session("testplayer", session_id)

        with patch.object(database, "get_user_role", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                validate_session_for_game(session_id)

    assert exc_info.value.status_code == 401


# =========================================================================
# SESSION LIFECYCLE TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_clear_all_sessions_clears_database(test_db, db_with_users):
    database.create_session("testplayer", "session-1")
    database.create_session("testadmin", "session-2")

    assert get_active_session_count() == 2

    result = clear_all_sessions()
    assert result == 2
    assert get_active_session_count() == 0


@pytest.mark.unit
@pytest.mark.auth
def test_remove_session_existing(test_db, db_with_users):
    session_id = "session-123"
    database.create_session("testplayer", session_id)

    assert remove_session(session_id) is True
    assert database.get_session_by_id(session_id) is None


@pytest.mark.unit
@pytest.mark.auth
def test_remove_session_nonexistent(test_db, db_with_users):
    assert remove_session("nonexistent-session") is False


@pytest.mark.unit
@pytest.mark.auth
def test_get_active_session_count_excludes_expired(test_db, db_with_users):
    active_id = "active-session"
    expired_id = "expired-session"
    database.create_session("testplayer", active_id)
    database.create_session("testadmin", expired_id)

    # Expire one session.
    conn = database.get_connection()
    cursor = conn.cursor()
    expired_ts = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
        (expired_ts, expired_id),
    )
    conn.commit()
    conn.close()

    assert get_active_session_count() == 1


@pytest.mark.unit
@pytest.mark.auth
def test_get_active_session_count_respects_activity_window(test_db, db_with_users):
    """Sessions with stale last_activity should not count as active."""
    from mud_server.config import config

    session_id = "stale-session"
    database.create_session("testplayer", session_id)

    original_window = config.session.active_window_minutes
    config.session.active_window_minutes = 1
    try:
        # Make last_activity older than the active window.
        conn = database.get_connection()
        cursor = conn.cursor()
        stale_ts = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (stale_ts, session_id),
        )
        conn.commit()
        conn.close()

        assert get_active_session_count() == 0
    finally:
        config.session.active_window_minutes = original_window
