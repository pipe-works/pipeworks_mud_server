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
    get_username_and_role_from_session,
    get_username_from_session,
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
