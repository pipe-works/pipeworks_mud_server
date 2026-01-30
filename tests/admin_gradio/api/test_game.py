"""
Tests for game API client.

This module tests the GameAPIClient class, verifying:
- Command sending and execution
- Chat message retrieval
- Status information formatting
- Display refresh functionality
- Error handling and validation
"""

from unittest.mock import Mock, patch

from mud_server.admin_gradio.api.game import GameAPIClient


class TestGameAPIClientSendCommand:
    """Tests for send_command functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_command(self, mock_request):
        """Test successful command execution."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "You moved north.",
        }
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.send_command("north", session_id="abc123")

        # Verify request
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["session_id"] == "abc123"
        assert call_kwargs["json"]["command"] == "north"

        # Verify response
        assert result["success"] is True
        assert result["message"] == "You moved north."
        assert result["data"] is None
        assert result["error"] is None

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_look_command(self, mock_request):
        """Test look command returns room description."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "You are in the spawn room. Exits: north, south.",
        }
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.send_command("look", session_id="abc123")

        assert result["success"] is True
        assert "spawn room" in result["message"]

    def test_command_not_logged_in(self):
        """Test command fails when not logged in."""
        client = GameAPIClient()
        result = client.send_command("look", session_id=None)

        assert result["success"] is False
        assert result["message"] == "You are not logged in."

    def test_command_empty(self):
        """Test command fails with empty command."""
        client = GameAPIClient()
        result = client.send_command("", session_id="abc123")

        assert result["success"] is False
        assert "Enter a command" in result["message"]

    def test_command_whitespace_only(self):
        """Test command fails with whitespace only."""
        client = GameAPIClient()
        result = client.send_command("   ", session_id="abc123")

        assert result["success"] is False
        assert "Enter a command" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_command_session_expired(self, mock_request):
        """Test command handles session expiration."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Invalid session"}
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.send_command("look", session_id="expired123")

        assert result["success"] is False
        assert "Session expired" in result["message"]
        assert result["error"] == "Session expired"

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_command_server_error(self, mock_request):
        """Test command handles server errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.send_command("look", session_id="abc123")

        assert result["success"] is False
        assert "Error:" in result["message"]


class TestGameAPIClientGetChat:
    """Tests for get_chat functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_get_chat(self, mock_request):
        """Test successful chat retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "chat": "[alice]: Hello!\n[bob]: Hi there!",
        }
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.get_chat(session_id="abc123")

        # Verify request
        mock_request.assert_called_once()
        assert "/chat/abc123" in mock_request.call_args.kwargs["url"]

        # Verify response
        assert result["success"] is True
        assert "[alice]" in result["message"]
        assert "[bob]" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_chat_empty(self, mock_request):
        """Test chat retrieval when no messages."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"chat": ""}
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.get_chat(session_id="abc123")

        assert result["success"] is True
        assert result["message"] == ""

    def test_get_chat_not_logged_in(self):
        """Test chat retrieval fails when not logged in."""
        client = GameAPIClient()
        result = client.get_chat(session_id=None)

        assert result["success"] is False
        assert "not logged in" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_chat_error(self, mock_request):
        """Test chat retrieval handles errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.get_chat(session_id="abc123")

        assert result["success"] is False
        assert "Failed to retrieve chat" in result["message"]


class TestGameAPIClientGetStatus:
    """Tests for get_status functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_get_status(self, mock_request):
        """Test successful status retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "current_room": "spawn",
            "active_players": ["alice", "bob"],
            "inventory": "Inventory: sword, shield",
        }
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.get_status(
            session_id="abc123",
            username="alice",
            role="player",
        )

        # Verify request
        mock_request.assert_called_once()
        assert "/status/abc123" in mock_request.call_args.kwargs["url"]

        # Verify response format
        assert result["success"] is True
        assert "Player Status" in result["message"]
        assert "Username: alice" in result["message"]
        assert "Role: Player" in result["message"]
        assert "Current Room: spawn" in result["message"]
        assert "Active Players: alice, bob" in result["message"]
        assert "Inventory: sword, shield" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_status_admin_role(self, mock_request):
        """Test status display for admin role."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "current_room": "admin_room",
            "active_players": [],
            "inventory": "Empty",
        }
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.get_status(
            session_id="admin123",
            username="admin",
            role="admin",
        )

        assert "Role: Admin" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_status_no_active_players(self, mock_request):
        """Test status when no other players are active."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "current_room": "spawn",
            "active_players": [],
            "inventory": "Empty",
        }
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.get_status(
            session_id="abc123",
            username="alice",
            role="player",
        )

        assert "Active Players: None" in result["message"]

    def test_get_status_not_logged_in(self):
        """Test status fails when not logged in."""
        client = GameAPIClient()
        result = client.get_status(
            session_id=None,
            username="alice",
            role="player",
        )

        assert result["success"] is False
        assert "not logged in" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_status_error(self, mock_request):
        """Test status handles errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client = GameAPIClient()
        result = client.get_status(
            session_id="abc123",
            username="alice",
            role="player",
        )

        assert result["success"] is False
        assert "Failed to retrieve status" in result["message"]


class TestGameAPIClientRefreshDisplay:
    """Tests for refresh_display functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_refresh(self, mock_request):
        """Test successful display refresh."""

        # Mock both look command and chat retrieval
        def mock_response_func(*args, **kwargs):
            response = Mock()
            response.status_code = 200

            if "/command" in kwargs["url"]:
                response.json.return_value = {"message": "You are in the spawn room."}
            elif "/chat/" in kwargs["url"]:
                response.json.return_value = {"chat": "[alice]: Hello!"}

            return response

        mock_request.side_effect = mock_response_func

        client = GameAPIClient()
        result = client.refresh_display(session_id="abc123")

        # Verify both requests were made
        assert mock_request.call_count == 2

        # Verify response structure
        assert result["success"] is True
        assert "room" in result["data"]
        assert "chat" in result["data"]
        assert "spawn room" in result["data"]["room"]
        assert "[alice]" in result["data"]["chat"]

    def test_refresh_not_logged_in(self):
        """Test refresh fails when not logged in."""
        client = GameAPIClient()
        result = client.refresh_display(session_id=None)

        assert result["success"] is False
        assert result["data"]["room"] == "Not logged in."
        assert result["data"]["chat"] == ""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_refresh_room_error(self, mock_request):
        """Test refresh handles room retrieval error."""

        def mock_response_func(*args, **kwargs):
            response = Mock()

            if "/command" in kwargs["url"]:
                response.status_code = 500
                response.json.return_value = {}
            elif "/chat/" in kwargs["url"]:
                response.status_code = 200
                response.json.return_value = {"chat": "Chat works"}

            return response

        mock_request.side_effect = mock_response_func

        client = GameAPIClient()
        result = client.refresh_display(session_id="abc123")

        # Should still succeed but with error message in room
        assert result["success"] is True
        assert "Failed to load room" in result["data"]["room"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_refresh_chat_error(self, mock_request):
        """Test refresh handles chat retrieval error."""

        def mock_response_func(*args, **kwargs):
            response = Mock()

            if "/command" in kwargs["url"]:
                response.status_code = 200
                response.json.return_value = {"message": "Room info"}
            elif "/chat/" in kwargs["url"]:
                response.status_code = 500
                response.json.return_value = {}

            return response

        mock_request.side_effect = mock_response_func

        client = GameAPIClient()
        result = client.refresh_display(session_id="abc123")

        # Should still succeed but with empty chat
        assert result["success"] is True
        assert result["data"]["room"] == "Room info"
        assert result["data"]["chat"] == ""


class TestGameAPIClientInit:
    """Tests for GameAPIClient initialization."""

    def test_inherits_from_base_client(self):
        """Test that GameAPIClient inherits from BaseAPIClient."""
        from mud_server.admin_gradio.api.base import BaseAPIClient

        client = GameAPIClient()
        assert isinstance(client, BaseAPIClient)

    def test_custom_server_url(self):
        """Test initialization with custom server URL."""
        client = GameAPIClient(server_url="http://game-server:9000")
        assert client.server_url == "http://game-server:9000"
