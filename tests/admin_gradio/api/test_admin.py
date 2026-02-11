"""
Tests for admin API client.

This module tests the AdminAPIClient class, verifying:
- Database viewing (players, sessions, chat)
- User management operations
- Permission checking
- Error handling
"""

from unittest.mock import Mock, patch

from mud_server.admin_gradio.api.admin import AdminAPIClient


class TestAdminAPIClientGetDatabasePlayers:
    """Tests for get_database_players functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_get_players(self, mock_request):
        """Test successful player database retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "players": [
                {
                    "id": 1,
                    "username": "alice",
                    "role": "player",
                    "account_origin": "visitor",
                    "is_active": True,
                    "current_room": "spawn",
                    "inventory": "[]",
                    "created_at": "2024-01-01",
                    "last_login": "2024-01-02",
                    "password_hash": "hash123",
                },
                {
                    "id": 2,
                    "username": "bob",
                    "role": "admin",
                    "is_active": False,
                    "current_room": "north",
                    "inventory": "[sword]",
                    "created_at": "2024-01-03",
                    "last_login": "2024-01-04",
                    "password_hash": "hash456",
                },
            ]
        }
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.get_database_players(session_id="admin123", role="admin")

        # Verify request
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["params"]["session_id"] == "admin123"

        # Verify response format
        assert result["success"] is True
        assert "USERS TABLE (2 records)" in result["message"]
        assert "alice" in result["message"]
        assert "bob" in result["message"]
        assert "ACTIVE" in result["message"]
        assert "BANNED" in result["message"]
        assert "Origin: visitor" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_players_empty(self, mock_request):
        """Test player retrieval with no players."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"players": []}
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.get_database_players(session_id="admin123", role="admin")

        assert result["success"] is True
        assert "No players found" in result["message"]

    def test_get_players_not_logged_in(self):
        """Test player retrieval fails when not logged in."""
        client = AdminAPIClient()
        result = client.get_database_players(session_id=None, role="player")

        assert result["success"] is False
        assert "not logged in" in result["message"]

    def test_get_players_insufficient_permissions(self):
        """Test player retrieval fails for non-admin."""
        client = AdminAPIClient()
        result = client.get_database_players(session_id="player123", role="player")

        assert result["success"] is False
        assert "Admin or Superuser role required" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_players_permission_denied(self, mock_request):
        """Test player retrieval with 403 response."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Forbidden"}
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.get_database_players(session_id="admin123", role="admin")

        assert result["success"] is False
        assert "Insufficient permissions" in result["message"]


class TestAdminAPIClientGetDatabaseSessions:
    """Tests for get_database_sessions functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_get_sessions(self, mock_request):
        """Test successful sessions retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sessions": [
                {
                    "id": 1,
                    "username": "alice",
                    "session_id": "abc123",
                    "created_at": "2024-01-01 10:00",
                    "last_activity": "2024-01-01 10:30",
                    "expires_at": "2024-01-01 18:00",
                },
                {
                    "id": 2,
                    "username": "bob",
                    "session_id": "def456",
                    "created_at": "2024-01-01 11:00",
                    "last_activity": "2024-01-01 11:15",
                    "expires_at": "2024-01-01 19:00",
                },
            ]
        }
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.get_database_sessions(session_id="admin123", role="superuser")

        # Verify response
        assert result["success"] is True
        assert "SESSIONS TABLE (2 records)" in result["message"]
        assert "alice" in result["message"]
        assert "abc123" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_sessions_empty(self, mock_request):
        """Test sessions retrieval with no sessions."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sessions": []}
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.get_database_sessions(session_id="admin123", role="admin")

        assert result["success"] is True
        assert "No active sessions" in result["message"]

    def test_get_sessions_no_permission(self):
        """Test sessions retrieval fails for worldbuilder."""
        client = AdminAPIClient()
        result = client.get_database_sessions(session_id="builder123", role="worldbuilder")

        assert result["success"] is False
        assert "Admin or Superuser role required" in result["message"]


class TestAdminAPIClientGetDatabaseChat:
    """Tests for get_database_chat functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_get_chat(self, mock_request):
        """Test successful chat messages retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messages": [
                {
                    "id": 1,
                    "room": "spawn",
                    "timestamp": "2024-01-01 10:00",
                    "username": "alice",
                    "message": "Hello!",
                },
                {
                    "id": 2,
                    "room": "north",
                    "timestamp": "2024-01-01 10:05",
                    "username": "bob",
                    "message": "Hi there!",
                },
            ]
        }
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.get_database_chat(session_id="admin123", role="admin", limit=50)

        # Verify request
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["params"]["limit"] == 50

        # Verify response
        assert result["success"] is True
        assert "CHAT MESSAGES (2 recent messages)" in result["message"]
        assert "alice" in result["message"]
        assert "Hello!" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_chat_custom_limit(self, mock_request):
        """Test chat retrieval with custom limit."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": []}
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        client.get_database_chat(session_id="admin123", role="admin", limit=100)

        # Verify limit was passed
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["params"]["limit"] == 100

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_chat_empty(self, mock_request):
        """Test chat retrieval with no messages."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": []}
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.get_database_chat(session_id="admin123", role="admin")

        assert result["success"] is True
        assert "No chat messages" in result["message"]

    def test_get_chat_no_permission(self):
        """Test chat retrieval fails for player role."""
        client = AdminAPIClient()
        result = client.get_database_chat(session_id="player123", role="player")

        assert result["success"] is False
        assert "Admin or Superuser role required" in result["message"]


class TestAdminAPIClientManageUser:
    """Tests for manage_user functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_change_role(self, mock_request):
        """Test successful role change."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Role changed to worldbuilder",
        }
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.manage_user(
            session_id="admin123",
            role="admin",
            target_username="alice",
            action="change_role",
            new_role="worldbuilder",
        )

        # Verify request
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["target_username"] == "alice"
        assert call_kwargs["json"]["action"] == "change_role"
        assert call_kwargs["json"]["new_role"] == "worldbuilder"

        # Verify response
        assert result["success"] is True
        assert "Role changed" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_ban_user(self, mock_request):
        """Test successful user ban."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "User banned"}
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.manage_user(
            session_id="admin123",
            role="superuser",
            target_username="baduser",
            action="ban",
        )

        # Verify request
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["action"] == "ban"

        assert result["success"] is True
        assert "User banned" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_unban_user(self, mock_request):
        """Test successful user unban."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "User unbanned"}
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.manage_user(
            session_id="admin123",
            role="admin",
            target_username="gooduser",
            action="unban",
        )

        assert result["success"] is True
        assert "User unbanned" in result["message"]

    def test_manage_user_not_logged_in(self):
        """Test user management fails when not logged in."""
        client = AdminAPIClient()
        result = client.manage_user(
            session_id=None,
            role="player",
            target_username="alice",
            action="ban",
        )

        assert result["success"] is False
        assert "not logged in" in result["message"]

    def test_manage_user_no_permission(self):
        """Test user management fails for non-admin."""
        client = AdminAPIClient()
        result = client.manage_user(
            session_id="player123",
            role="player",
            target_username="alice",
            action="ban",
        )

        assert result["success"] is False
        assert "Admin or Superuser role required" in result["message"]

    def test_manage_user_no_target_username(self):
        """Test user management fails without target username."""
        client = AdminAPIClient()
        result = client.manage_user(
            session_id="admin123",
            role="admin",
            target_username="",
            action="ban",
        )

        assert result["success"] is False
        assert "Target username is required" in result["message"]

    def test_manage_user_no_action(self):
        """Test user management fails without action."""
        client = AdminAPIClient()
        result = client.manage_user(
            session_id="admin123",
            role="admin",
            target_username="alice",
            action="",
        )

        assert result["success"] is False
        assert "Action is required" in result["message"]

    def test_manage_user_change_role_no_new_role(self):
        """Test change_role action fails without new_role."""
        client = AdminAPIClient()
        result = client.manage_user(
            session_id="admin123",
            role="admin",
            target_username="alice",
            action="change_role",
            new_role="",
        )

        assert result["success"] is False
        assert "New role is required" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_manage_user_strips_whitespace(self, mock_request):
        """Test that username and role are stripped."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Success"}
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        client.manage_user(
            session_id="admin123",
            role="admin",
            target_username="  alice  ",
            action="change_role",
            new_role="  WorldBuilder  ",
        )

        # Verify whitespace was stripped and role lowercased
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["target_username"] == "alice"
        assert call_kwargs["json"]["new_role"] == "worldbuilder"

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_manage_user_server_error(self, mock_request):
        """Test user management handles server errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Server error"}
        mock_request.return_value = mock_response

        client = AdminAPIClient()
        result = client.manage_user(
            session_id="admin123",
            role="admin",
            target_username="alice",
            action="ban",
        )

        assert result["success"] is False
        assert result["error"] is not None


class TestAdminAPIClientInit:
    """Tests for AdminAPIClient initialization."""

    def test_inherits_from_base_client(self):
        """Test that AdminAPIClient inherits from BaseAPIClient."""
        from mud_server.admin_gradio.api.base import BaseAPIClient

        client = AdminAPIClient()
        assert isinstance(client, BaseAPIClient)

    def test_custom_server_url(self):
        """Test initialization with custom server URL."""
        client = AdminAPIClient(server_url="http://admin-server:9000")
        assert client.server_url == "http://admin-server:9000"
