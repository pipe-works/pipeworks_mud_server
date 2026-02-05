"""
Tests for authentication API client.

This module tests the AuthAPIClient class, verifying:
- Login with valid and invalid credentials
- Registration with various validation scenarios
- Logout behavior
- Error handling and response formats
"""

from unittest.mock import Mock, patch

from mud_server.admin_gradio.api.auth import AuthAPIClient
from tests.constants import TEST_PASSWORD


class TestAuthAPIClientLogin:
    """Tests for login functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_login(self, mock_request):
        """Test successful login returns session data."""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Login successful",
            "session_id": "abc123",
            "role": "player",
        }
        mock_request.return_value = mock_response

        # Make login request
        client = AuthAPIClient()
        result = client.login("alice", TEST_PASSWORD)

        # Verify request was made correctly
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["username"] == "alice"
        assert call_kwargs["json"]["password"] == TEST_PASSWORD
        assert call_kwargs["headers"]["X-Client-Type"] == "gradio"

        # Verify response format
        assert result["success"] is True
        assert result["message"] == "Login successful"
        assert result["data"]["session_id"] == "abc123"
        assert result["data"]["username"] == "alice"
        assert result["data"]["role"] == "player"
        assert result["error"] is None

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_login_admin_role(self, mock_request):
        """Test login as admin returns admin role."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Welcome admin",
            "session_id": "admin123",
            "role": "admin",
        }
        mock_request.return_value = mock_response

        client = AuthAPIClient()
        result = client.login("admin", "adminpass")

        assert result["success"] is True
        assert result["data"]["role"] == "admin"

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_login_invalid_credentials(self, mock_request):
        """Test login with invalid credentials."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Invalid credentials"}
        mock_request.return_value = mock_response

        client = AuthAPIClient()
        result = client.login("alice", "wrongpassword")

        assert result["success"] is False
        assert "Login failed" in result["message"]
        assert "Invalid credentials" in result["message"]
        assert result["data"] is None
        assert result["error"] == "Invalid credentials"

    def test_login_username_too_short(self):
        """Test login with username too short (validation error)."""
        client = AuthAPIClient()
        result = client.login("a", TEST_PASSWORD)

        assert result["success"] is False
        assert "Username must be at least 2 characters" in result["message"]
        assert result["data"] is None

    def test_login_empty_username(self):
        """Test login with empty username."""
        client = AuthAPIClient()
        result = client.login("", TEST_PASSWORD)

        assert result["success"] is False
        assert "Username must be at least 2 characters" in result["message"]

    def test_login_no_password(self):
        """Test login with no password."""
        client = AuthAPIClient()
        result = client.login("alice", "")

        assert result["success"] is False
        assert "Password is required" in result["message"]

    def test_login_username_with_whitespace(self):
        """Test login strips whitespace from username."""
        client = AuthAPIClient()

        with patch("mud_server.admin_gradio.api.base.requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": "Login successful",
                "session_id": "abc123",
                "role": "player",
            }
            mock_request.return_value = mock_response

            client.login("  alice  ", TEST_PASSWORD)

            # Verify username was stripped
            call_kwargs = mock_request.call_args.kwargs
            assert call_kwargs["json"]["username"] == "alice"
            assert call_kwargs["headers"]["X-Client-Type"] == "gradio"

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_login_connection_error(self, mock_request):
        """Test login with connection error."""
        import requests

        mock_request.side_effect = requests.exceptions.ConnectionError()

        client = AuthAPIClient()
        result = client.login("alice", TEST_PASSWORD)

        assert result["success"] is False
        assert "Cannot connect to server" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_login_default_role(self, mock_request):
        """Test login defaults to player role if not specified."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Login successful",
            "session_id": "abc123",
            # No role specified
        }
        mock_request.return_value = mock_response

        client = AuthAPIClient()
        result = client.login("alice", TEST_PASSWORD)

        # Should default to player
        assert result["data"]["role"] == "player"

    def test_logout_logs_warning_on_exception(self, caplog):
        """Test logout logs a warning if the request fails."""
        client = AuthAPIClient()

        with patch.object(client, "post", side_effect=RuntimeError("boom")):
            with caplog.at_level("WARNING"):
                result = client.logout("session-123")

        assert result["success"] is True
        assert any("Logout request failed" in record.message for record in caplog.records)


class TestAuthAPIClientRegister:
    """Tests for registration functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_registration(self, mock_request):
        """Test successful user registration."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Account created successfully",
        }
        mock_request.return_value = mock_response

        client = AuthAPIClient()
        result = client.register("newuser", TEST_PASSWORD, TEST_PASSWORD)

        # Verify request was made correctly
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["username"] == "newuser"
        assert call_kwargs["json"]["password"] == TEST_PASSWORD
        assert call_kwargs["json"]["password_confirm"] == TEST_PASSWORD

        # Verify response format
        assert result["success"] is True
        assert "Account created successfully" in result["message"]
        assert "You can now login" in result["message"]
        assert result["data"] is None
        assert result["error"] is None

    def test_register_username_too_short(self):
        """Test registration with username too short."""
        client = AuthAPIClient()
        result = client.register("a", TEST_PASSWORD, TEST_PASSWORD)

        assert result["success"] is False
        assert "Username must be at least 2 characters" in result["message"]

    def test_register_password_too_short(self):
        """Test registration with password too short."""
        client = AuthAPIClient()
        result = client.register("alice", "short", "short")

        assert result["success"] is False
        assert "Password must be at least 8 characters" in result["message"]

    def test_register_passwords_dont_match(self):
        """Test registration with mismatched passwords."""
        client = AuthAPIClient()
        result = client.register("alice", TEST_PASSWORD, "different")

        assert result["success"] is False
        assert "Passwords do not match" in result["message"]

    def test_register_empty_password(self):
        """Test registration with empty password."""
        client = AuthAPIClient()
        result = client.register("alice", "", "")

        assert result["success"] is False
        assert "Password is required" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_register_username_already_exists(self, mock_request):
        """Test registration with existing username."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Username already exists"}
        mock_request.return_value = mock_response

        client = AuthAPIClient()
        result = client.register("existing", TEST_PASSWORD, TEST_PASSWORD)

        assert result["success"] is False
        assert "Registration failed" in result["message"]
        assert "Username already exists" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_register_connection_error(self, mock_request):
        """Test registration with connection error."""
        import requests

        mock_request.side_effect = requests.exceptions.ConnectionError()

        client = AuthAPIClient()
        result = client.register("alice", TEST_PASSWORD, TEST_PASSWORD)

        assert result["success"] is False
        assert "Cannot connect to server" in result["message"]

    def test_register_strips_username_whitespace(self):
        """Test registration strips whitespace from username."""
        client = AuthAPIClient()

        with patch("mud_server.admin_gradio.api.base.requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"message": "Success"}
            mock_request.return_value = mock_response

            client.register("  alice  ", TEST_PASSWORD, TEST_PASSWORD)

            # Verify username was stripped
            call_kwargs = mock_request.call_args.kwargs
            assert call_kwargs["json"]["username"] == "alice"


class TestAuthAPIClientLogout:
    """Tests for logout functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_logout(self, mock_request):
        """Test successful logout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Logged out"}
        mock_request.return_value = mock_response

        client = AuthAPIClient()
        result = client.logout("abc123")

        # Verify request was made
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["session_id"] == "abc123"

        # Verify response
        assert result["success"] is True
        assert result["message"] == "You have been logged out."
        assert result["data"] is None
        assert result["error"] is None

    def test_logout_not_logged_in(self):
        """Test logout when not logged in (no session ID)."""
        client = AuthAPIClient()
        result = client.logout(None)

        assert result["success"] is False
        assert result["message"] == "Not logged in."
        assert result["error"] == "No active session"

    def test_logout_empty_session_id(self):
        """Test logout with empty session ID."""
        client = AuthAPIClient()
        result = client.logout("")

        assert result["success"] is False
        assert result["message"] == "Not logged in."

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_logout_server_error_still_succeeds(self, mock_request):
        """Test logout succeeds even if server returns error."""
        # Server returns error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Server error"}
        mock_request.return_value = mock_response

        client = AuthAPIClient()
        result = client.logout("abc123")

        # Logout should still succeed (client-side cleanup)
        assert result["success"] is True
        assert result["message"] == "You have been logged out."

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_logout_connection_error_still_succeeds(self, mock_request):
        """Test logout succeeds even with connection error."""
        import requests

        mock_request.side_effect = requests.exceptions.ConnectionError()

        client = AuthAPIClient()
        result = client.logout("abc123")

        # Logout should still succeed (client-side cleanup)
        assert result["success"] is True
        assert result["message"] == "You have been logged out."


class TestAuthAPIClientInit:
    """Tests for AuthAPIClient initialization."""

    def test_inherits_from_base_client(self):
        """Test that AuthAPIClient inherits from BaseAPIClient."""
        from mud_server.admin_gradio.api.base import BaseAPIClient

        client = AuthAPIClient()
        assert isinstance(client, BaseAPIClient)

    def test_custom_server_url(self):
        """Test initialization with custom server URL."""
        client = AuthAPIClient(server_url="http://custom:9000")
        assert client.server_url == "http://custom:9000"

    def test_default_server_url(self):
        """Test initialization with default server URL."""
        client = AuthAPIClient()
        assert client.server_url == "http://localhost:8000"
