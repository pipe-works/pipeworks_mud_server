"""
Tests for UI state builders.

This module tests UI state building functions to ensure:
- Correct tuple structures are returned
- UI visibility is set correctly based on login state and role
- Session state updates are applied correctly
"""

from mud_server.admin_gradio.ui.state import (
    build_logged_in_state,
    build_logged_out_state,
    build_login_failed_state,
    clear_session_state,
    is_admin_role,
    update_session_state,
)


class TestBuildLoggedInState:
    """Tests for build_logged_in_state function."""

    def test_player_login_state(self):
        """Test UI state for player login (no admin access)."""
        session_state = {"username": "alice", "role": "player"}
        result = build_logged_in_state(session_state, "Login successful", has_admin_access=False)

        # Verify tuple structure
        assert len(result) == 11
        assert result[0] == session_state  # session state
        assert result[1] == "Login successful"  # message
        assert result[2] == ""  # clear username
        assert result[3] == ""  # clear password

        # Verify tab visibility (result[4] through result[10])
        # login, register, game, settings, db, ollama, help
        assert result[4]["visible"] is True  # login tab
        assert result[5]["visible"] is False  # register tab
        assert result[6]["visible"] is True  # game tab
        assert result[7]["visible"] is True  # settings tab
        assert result[8]["visible"] is False  # database tab (no admin)
        assert result[9]["visible"] is False  # ollama tab (no admin)
        assert result[10]["visible"] is True  # help tab

    def test_admin_login_state(self):
        """Test UI state for admin login (with admin access)."""
        session_state = {"username": "admin", "role": "admin"}
        result = build_logged_in_state(session_state, "Welcome admin", has_admin_access=True)

        # Verify admin tabs are visible
        assert result[8]["visible"] is True  # database tab (admin access)
        assert result[9]["visible"] is True  # ollama tab (admin access)

    def test_superuser_login_state(self):
        """Test UI state for superuser login."""
        session_state = {"username": "root", "role": "superuser"}
        result = build_logged_in_state(session_state, "Welcome superuser", has_admin_access=True)

        # Verify all tabs visible for superuser
        assert result[6]["visible"] is True  # game tab
        assert result[7]["visible"] is True  # settings tab
        assert result[8]["visible"] is True  # database tab
        assert result[9]["visible"] is True  # ollama tab
        assert result[10]["visible"] is True  # help tab


class TestBuildLoggedOutState:
    """Tests for build_logged_out_state function."""

    def test_logout_state(self):
        """Test UI state for logged out user."""
        session_state = {}
        result = build_logged_out_state(session_state, "You have been logged out.")

        # Verify tuple structure
        assert len(result) == 10
        assert result[0] == session_state
        assert result[1] == "You have been logged out."
        assert result[2] == ""  # blank field

        # Verify only login/register tabs visible
        assert result[3]["visible"] is True  # login tab
        assert result[4]["visible"] is True  # register tab
        assert result[5]["visible"] is False  # game tab
        assert result[6]["visible"] is False  # settings tab
        assert result[7]["visible"] is False  # database tab
        assert result[8]["visible"] is False  # ollama tab
        assert result[9]["visible"] is False  # help tab

    def test_not_logged_in_state(self):
        """Test UI state for user who was never logged in."""
        session_state = {}
        result = build_logged_out_state(session_state, "Not logged in.")

        # Verify same state as logout
        assert result[3]["visible"] is True  # login tab
        assert result[4]["visible"] is True  # register tab
        assert result[5]["visible"] is False  # game tab


class TestBuildLoginFailedState:
    """Tests for build_login_failed_state function."""

    def test_invalid_credentials_state(self):
        """Test UI state for failed login with invalid credentials."""
        session_state = {}
        result = build_login_failed_state(session_state, "Login failed: Invalid credentials")

        # Verify tuple structure
        assert len(result) == 11
        assert result[0] == session_state
        assert result[1] == "Login failed: Invalid credentials"
        assert result[2] == ""  # preserve username
        assert result[3] == ""  # clear password

        # Verify only login/register tabs visible
        assert result[4]["visible"] is True  # login tab
        assert result[5]["visible"] is True  # register tab
        assert result[6]["visible"] is False  # game tab
        assert result[7]["visible"] is False  # settings tab
        assert result[8]["visible"] is False  # database tab
        assert result[9]["visible"] is False  # ollama tab
        assert result[10]["visible"] is False  # help tab

    def test_validation_error_state(self):
        """Test UI state for failed login with validation error."""
        session_state = {}
        result = build_login_failed_state(
            session_state,
            "Username must be at least 2 characters.",
        )

        # Verify error message passed through
        assert result[1] == "Username must be at least 2 characters."
        # Password should be cleared
        assert result[3] == ""

    def test_connection_error_state(self):
        """Test UI state for failed login with connection error."""
        session_state = {}
        result = build_login_failed_state(
            session_state,
            "Cannot connect to server at http://localhost:8000",
        )

        # Verify connection error displayed
        assert "Cannot connect to server" in result[1]


class TestIsAdminRole:
    """Tests for is_admin_role function."""

    def test_admin_role_is_admin(self):
        """Test that 'admin' role is recognized as admin."""
        assert is_admin_role("admin") is True

    def test_superuser_role_is_admin(self):
        """Test that 'superuser' role is recognized as admin."""
        assert is_admin_role("superuser") is True

    def test_player_role_not_admin(self):
        """Test that 'player' role is not admin."""
        assert is_admin_role("player") is False

    def test_worldbuilder_role_not_admin(self):
        """Test that 'worldbuilder' role is not admin."""
        assert is_admin_role("worldbuilder") is False

    def test_empty_role_not_admin(self):
        """Test that empty role is not admin."""
        assert is_admin_role("") is False

    def test_unknown_role_not_admin(self):
        """Test that unknown role is not admin."""
        assert is_admin_role("unknown") is False


class TestUpdateSessionState:
    """Tests for update_session_state function."""

    def test_update_empty_session_state(self):
        """Test updating empty session state."""
        session_state = {}
        result = update_session_state(
            session_state,
            session_id="abc123",
            username="alice",
            role="player",
        )

        assert result["session_id"] == "abc123"
        assert result["username"] == "alice"
        assert result["role"] == "player"
        assert result["logged_in"] is True

    def test_update_existing_session_state(self):
        """Test updating existing session state."""
        session_state = {
            "session_id": "old123",
            "username": "olduser",
            "role": "player",
            "logged_in": False,
        }
        result = update_session_state(
            session_state,
            session_id="new456",
            username="newuser",
            role="admin",
        )

        # Verify old values are overwritten
        assert result["session_id"] == "new456"
        assert result["username"] == "newuser"
        assert result["role"] == "admin"
        assert result["logged_in"] is True

    def test_update_with_explicit_logged_in_false(self):
        """Test updating session state with logged_in=False."""
        session_state = {}
        result = update_session_state(
            session_state,
            session_id="abc123",
            username="alice",
            role="player",
            logged_in=False,
        )

        assert result["logged_in"] is False

    def test_update_preserves_other_fields(self):
        """Test that updating session state preserves other fields."""
        session_state = {"custom_field": "custom_value"}
        result = update_session_state(
            session_state,
            session_id="abc123",
            username="alice",
            role="player",
        )

        # Verify custom field is preserved
        assert result["custom_field"] == "custom_value"
        assert result["session_id"] == "abc123"


class TestClearSessionState:
    """Tests for clear_session_state function."""

    def test_clear_logged_in_session(self):
        """Test clearing a logged in session."""
        session_state = {
            "session_id": "abc123",
            "username": "alice",
            "role": "player",
            "logged_in": True,
        }
        result = clear_session_state(session_state)

        assert result["session_id"] is None
        assert result["username"] is None
        assert result["role"] is None
        assert result["logged_in"] is False

    def test_clear_already_cleared_session(self):
        """Test clearing a session that's already cleared."""
        session_state = {
            "session_id": None,
            "username": None,
            "role": None,
            "logged_in": False,
        }
        result = clear_session_state(session_state)

        # Should be idempotent
        assert result["session_id"] is None
        assert result["username"] is None
        assert result["role"] is None
        assert result["logged_in"] is False

    def test_clear_preserves_other_fields(self):
        """Test that clearing session preserves other fields."""
        session_state = {
            "session_id": "abc123",
            "username": "alice",
            "role": "player",
            "logged_in": True,
            "custom_field": "custom_value",
        }
        result = clear_session_state(session_state)

        # Verify custom field is preserved
        assert result["custom_field"] == "custom_value"
        # Verify session fields are cleared
        assert result["session_id"] is None
        assert result["logged_in"] is False

    def test_clear_empty_session(self):
        """Test clearing an empty session."""
        session_state = {}
        result = clear_session_state(session_state)

        # Should set all fields to None/False
        assert result["session_id"] is None
        assert result["username"] is None
        assert result["role"] is None
        assert result["logged_in"] is False
