"""
Unit tests for authentication module (mud_server/api/auth.py).

Tests cover:
- Session storage and retrieval
- Session validation
- Permission-based session validation
- Session activity tracking

All tests use isolated session dictionaries and mocked database.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from mud_server.api.auth import (
    active_sessions,
    clear_all_sessions,
    get_active_session_count,
    get_username_and_role_from_session,
    get_username_from_session,
    remove_session,
    validate_session,
    validate_session_with_permission,
)
from mud_server.api.permissions import Permission

# ============================================================================
# SESSION RETRIEVAL TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_from_session_existing(mock_session_data):
    """Test retrieving username from existing session."""
    active_sessions.update(mock_session_data)

    username = get_username_from_session("session-player")
    assert username == "testplayer"


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_from_session_nonexistent():
    """Test retrieving username from non-existent session."""
    username = get_username_from_session("invalid-session")
    assert username is None


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_and_role_from_session_existing(mock_session_data):
    """Test retrieving username and role from existing session."""
    active_sessions.update(mock_session_data)

    session_data = get_username_and_role_from_session("session-admin")
    assert session_data == ("testadmin", "admin")


@pytest.mark.unit
@pytest.mark.auth
def test_get_username_and_role_from_session_nonexistent():
    """Test retrieving from non-existent session."""
    session_data = get_username_and_role_from_session("invalid-session")
    assert session_data is None


# ============================================================================
# SESSION VALIDATION TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_success(mock_session_data):
    """Test validating a valid session."""
    active_sessions.update(mock_session_data)

    with patch("mud_server.api.auth.database.update_session_activity", return_value=True):
        username, role = validate_session("session-player")

        assert username == "testplayer"
        assert role == "player"


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_invalid():
    """Test validating an invalid session raises 401."""
    with pytest.raises(HTTPException) as exc_info:
        validate_session("invalid-session")

    assert exc_info.value.status_code == 401
    assert "Invalid or expired session" in str(exc_info.value.detail)


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_updates_activity(mock_session_data):
    """Test that session validation updates activity timestamp."""
    active_sessions.update(mock_session_data)

    with patch("mud_server.api.auth.database.update_session_activity") as mock_update:
        mock_update.return_value = True

        validate_session("session-player")

        # Verify update_session_activity was called with username
        mock_update.assert_called_once_with("testplayer")


# ============================================================================
# PERMISSION-BASED VALIDATION TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_with_permission_success(mock_session_data):
    """Test validating session with sufficient permission."""
    active_sessions.update(mock_session_data)

    with patch("mud_server.api.auth.database.update_session_activity", return_value=True):
        username, role = validate_session_with_permission("session-admin", Permission.VIEW_LOGS)

        assert username == "testadmin"
        assert role == "admin"


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_with_permission_insufficient(mock_session_data):
    """Test validating session with insufficient permission raises 403."""
    active_sessions.update(mock_session_data)

    with patch("mud_server.api.auth.database.update_session_activity", return_value=True):
        with pytest.raises(HTTPException) as exc_info:
            validate_session_with_permission("session-player", Permission.MANAGE_USERS)

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in str(exc_info.value.detail)


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_with_permission_invalid_session():
    """Test that invalid session raises 401 before checking permissions."""
    with pytest.raises(HTTPException) as exc_info:
        validate_session_with_permission("invalid-session", Permission.VIEW_LOGS)

    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.auth
def test_validate_session_with_permission_superuser_has_all(mock_session_data):
    """Test that superuser has all permissions."""
    active_sessions.update(mock_session_data)

    with patch("mud_server.api.auth.database.update_session_activity", return_value=True):
        # Superuser should have any permission
        username, role = validate_session_with_permission(
            "session-superuser", Permission.MANAGE_USERS
        )

        assert username == "testsuperuser"
        assert role == "superuser"


# ============================================================================
# SESSION LIFECYCLE TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_clear_all_sessions_clears_memory():
    """Test that clear_all_sessions clears in-memory sessions."""
    # Add sessions directly to the dict
    active_sessions["session-1"] = ("user1", "player")
    active_sessions["session-2"] = ("user2", "admin")

    assert len(active_sessions) == 2

    with patch("mud_server.api.auth.database.clear_all_sessions", return_value=2):
        result = clear_all_sessions()

    assert result == 2
    assert len(active_sessions) == 0


@pytest.mark.unit
@pytest.mark.auth
def test_clear_all_sessions_calls_database():
    """Test that clear_all_sessions calls database function."""
    with patch("mud_server.api.auth.database.clear_all_sessions") as mock_db_clear:
        mock_db_clear.return_value = 5

        result = clear_all_sessions()

        mock_db_clear.assert_called_once()
        assert result == 5


@pytest.mark.unit
@pytest.mark.auth
def test_remove_session_existing():
    """Test removing an existing session."""
    # Add a session
    active_sessions["session-123"] = ("testuser", "player")

    with patch("mud_server.api.auth.database.remove_session") as mock_db_remove:
        mock_db_remove.return_value = True

        result = remove_session("session-123")

        assert result is True
        assert "session-123" not in active_sessions
        mock_db_remove.assert_called_once_with("testuser")


@pytest.mark.unit
@pytest.mark.auth
def test_remove_session_nonexistent():
    """Test removing a non-existent session returns False."""
    result = remove_session("nonexistent-session")

    assert result is False


@pytest.mark.unit
@pytest.mark.auth
def test_remove_session_clears_from_memory():
    """Test that remove_session removes from in-memory dict."""
    active_sessions["session-abc"] = ("myuser", "admin")
    active_sessions["session-xyz"] = ("otheruser", "player")

    with patch("mud_server.api.auth.database.remove_session", return_value=True):
        remove_session("session-abc")

    assert "session-abc" not in active_sessions
    assert "session-xyz" in active_sessions  # Other session should remain


@pytest.mark.unit
@pytest.mark.auth
def test_get_active_session_count_empty():
    """Test get_active_session_count with no sessions."""
    assert get_active_session_count() == 0


@pytest.mark.unit
@pytest.mark.auth
def test_get_active_session_count_with_sessions():
    """Test get_active_session_count with multiple sessions."""
    active_sessions["session-1"] = ("user1", "player")
    active_sessions["session-2"] = ("user2", "admin")
    active_sessions["session-3"] = ("user3", "superuser")

    assert get_active_session_count() == 3


@pytest.mark.unit
@pytest.mark.auth
def test_get_active_session_count_after_remove():
    """Test get_active_session_count after removing a session."""
    active_sessions["session-1"] = ("user1", "player")
    active_sessions["session-2"] = ("user2", "admin")

    assert get_active_session_count() == 2

    with patch("mud_server.api.auth.database.remove_session", return_value=True):
        remove_session("session-1")

    assert get_active_session_count() == 1


# ============================================================================
# ACTIVE_SESSIONS CLEANUP TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_active_sessions_cleared_between_tests():
    """Test that active_sessions is cleared between tests."""
    # This test verifies the reset_active_sessions fixture works
    assert len(active_sessions) == 0

    # Add a session
    active_sessions["test"] = ("user", "role")

    # It will be cleared by the autouse fixture after this test
