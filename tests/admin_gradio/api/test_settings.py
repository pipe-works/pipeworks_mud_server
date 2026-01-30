"""
Tests for settings API client.

This module tests the SettingsAPIClient class, verifying:
- Password change with validation
- Server stop functionality
- Permission checking
- Error handling
"""

from unittest.mock import Mock, patch

from mud_server.admin_gradio.api.settings import SettingsAPIClient


class TestSettingsAPIClientChangePassword:
    """Tests for change_password functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_password_change(self, mock_request):
        """Test successful password change."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Password changed successfully",
        }
        mock_request.return_value = mock_response

        client = SettingsAPIClient()
        result = client.change_password(
            session_id="abc123",
            old_password="old password",
            new_password="newpassword123",
            confirm_password="newpassword123",
        )

        # Verify request
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["session_id"] == "abc123"
        assert call_kwargs["json"]["old_password"] == "old password"
        assert call_kwargs["json"]["new_password"] == "newpassword123"

        # Verify response
        assert result["success"] is True
        assert "Password changed successfully" in result["message"]
        assert result["error"] is None

    def test_change_password_not_logged_in(self):
        """Test password change fails when not logged in."""
        client = SettingsAPIClient()
        result = client.change_password(
            session_id=None,
            old_password="old",
            new_password="newpassword",
            confirm_password="newpassword",
        )

        assert result["success"] is False
        assert "not logged in" in result["message"]

    def test_change_password_no_old_password(self):
        """Test password change fails without old password."""
        client = SettingsAPIClient()
        result = client.change_password(
            session_id="abc123",
            old_password="",
            new_password="newpassword",
            confirm_password="newpassword",
        )

        assert result["success"] is False
        assert "Current password is required" in result["message"]

    def test_change_password_new_too_short(self):
        """Test password change fails when new password too short."""
        client = SettingsAPIClient()
        result = client.change_password(
            session_id="abc123",
            old_password="oldpassword",
            new_password="short",
            confirm_password="short",
        )

        assert result["success"] is False
        assert "at least 8 characters" in result["message"]

    def test_change_password_no_match(self):
        """Test password change fails when new passwords don't match."""
        client = SettingsAPIClient()
        result = client.change_password(
            session_id="abc123",
            old_password="oldpassword",
            new_password="newpassword123",
            confirm_password="different123",
        )

        assert result["success"] is False
        assert "do not match" in result["message"]

    def test_change_password_same_as_old(self):
        """Test password change fails when new password same as old."""
        client = SettingsAPIClient()
        result = client.change_password(
            session_id="abc123",
            old_password="samepassword",
            new_password="samepassword",
            confirm_password="samepassword",
        )

        assert result["success"] is False
        assert "must be different" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_change_password_wrong_old_password(self, mock_request):
        """Test password change with incorrect old password."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Incorrect old password"}
        mock_request.return_value = mock_response

        client = SettingsAPIClient()
        result = client.change_password(
            session_id="abc123",
            old_password="wrongold",
            new_password="newpassword123",
            confirm_password="newpassword123",
        )

        assert result["success"] is False
        assert "Incorrect old password" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_change_password_server_error(self, mock_request):
        """Test password change handles server errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Server error"}
        mock_request.return_value = mock_response

        client = SettingsAPIClient()
        result = client.change_password(
            session_id="abc123",
            old_password="oldpass",
            new_password="newpassword123",
            confirm_password="newpassword123",
        )

        assert result["success"] is False
        assert result["error"] is not None


class TestSettingsAPIClientStopServer:
    """Tests for stop_server functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_server_stop_admin(self, mock_request):
        """Test successful server stop by admin."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Server shutting down",
        }
        mock_request.return_value = mock_response

        client = SettingsAPIClient()
        result = client.stop_server(session_id="admin123", role="admin")

        # Verify request
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["session_id"] == "admin123"
        assert "/admin/server/stop" in call_kwargs["url"]

        # Verify response
        assert result["success"] is True
        assert "Server shutting down" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_server_stop_superuser(self, mock_request):
        """Test successful server stop by superuser."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Stopping"}
        mock_request.return_value = mock_response

        client = SettingsAPIClient()
        result = client.stop_server(session_id="super123", role="superuser")

        assert result["success"] is True

    def test_stop_server_not_logged_in(self):
        """Test server stop fails when not logged in."""
        client = SettingsAPIClient()
        result = client.stop_server(session_id=None, role="player")

        assert result["success"] is False
        assert "not logged in" in result["message"]

    def test_stop_server_player_role(self):
        """Test server stop fails for player role."""
        client = SettingsAPIClient()
        result = client.stop_server(session_id="player123", role="player")

        assert result["success"] is False
        assert "Admin or Superuser role required" in result["message"]

    def test_stop_server_worldbuilder_role(self):
        """Test server stop fails for worldbuilder role."""
        client = SettingsAPIClient()
        result = client.stop_server(session_id="builder123", role="worldbuilder")

        assert result["success"] is False
        assert "Admin or Superuser role required" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_stop_server_permission_denied(self, mock_request):
        """Test server stop with 403 permission denied."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Forbidden"}
        mock_request.return_value = mock_response

        client = SettingsAPIClient()
        result = client.stop_server(session_id="admin123", role="admin")

        assert result["success"] is False
        assert "Insufficient permissions" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_stop_server_connection_error(self, mock_request):
        """Test server stop handles connection error (server already stopped)."""
        import requests

        mock_request.side_effect = requests.exceptions.ConnectionError()

        client = SettingsAPIClient()
        result = client.stop_server(session_id="admin123", role="admin")

        # Connection error after stop command is considered success
        assert result["success"] is True
        assert "Server stopped or cannot connect" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_stop_server_other_error(self, mock_request):
        """Test server stop handles other errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal error"}
        mock_request.return_value = mock_response

        client = SettingsAPIClient()
        result = client.stop_server(session_id="admin123", role="admin")

        assert result["success"] is False
        assert result["error"] is not None


class TestSettingsAPIClientInit:
    """Tests for SettingsAPIClient initialization."""

    def test_inherits_from_base_client(self):
        """Test that SettingsAPIClient inherits from BaseAPIClient."""
        from mud_server.admin_gradio.api.base import BaseAPIClient

        client = SettingsAPIClient()
        assert isinstance(client, BaseAPIClient)

    def test_custom_server_url(self):
        """Test initialization with custom server URL."""
        client = SettingsAPIClient(server_url="http://settings:9000")
        assert client.server_url == "http://settings:9000"
