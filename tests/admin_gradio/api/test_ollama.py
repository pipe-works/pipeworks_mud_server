"""
Tests for Ollama API client.

This module tests the OllamaAPIClient class, verifying:
- Ollama command execution
- Context clearing
- Permission checking
- Timeout handling
- Error handling
"""

from unittest.mock import Mock, patch

from mud_server.admin_gradio.api.ollama import OllamaAPIClient


class TestOllamaAPIClientExecuteCommand:
    """Tests for execute_command functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_command_execution(self, mock_request):
        """Test successful Ollama command execution."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": "model1\nmodel2\nmodel3",
        }
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="admin123",
            role="admin",
            server_url="http://localhost:11434",
            command="list",
        )

        # Verify request
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["server_url"] == "http://localhost:11434"
        assert call_kwargs["json"]["command"] == "list"
        assert call_kwargs["timeout"] == 300  # 5 minute timeout

        # Verify response
        assert result["success"] is True
        assert "model1" in result["message"]
        assert result["error"] is None

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_execute_ps_command(self, mock_request):
        """Test executing 'ps' command."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": "No models running",
        }
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="admin123",
            role="superuser",
            server_url="http://ollama:11434",
            command="ps",
        )

        assert result["success"] is True
        assert "No models running" in result["message"]

    def test_execute_command_not_logged_in(self):
        """Test command execution fails when not logged in."""
        client = OllamaAPIClient()
        result = client.execute_command(
            session_id=None,
            role="player",
            server_url="http://localhost:11434",
            command="list",
        )

        assert result["success"] is False
        assert "not logged in" in result["message"]

    def test_execute_command_no_permission(self):
        """Test command execution fails for non-admin."""
        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="player123",
            role="player",
            server_url="http://localhost:11434",
            command="list",
        )

        assert result["success"] is False
        assert "Admin or Superuser role required" in result["message"]

    def test_execute_command_worldbuilder_no_permission(self):
        """Test command execution fails for worldbuilder."""
        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="builder123",
            role="worldbuilder",
            server_url="http://localhost:11434",
            command="list",
        )

        assert result["success"] is False
        assert "Admin or Superuser role required" in result["message"]

    def test_execute_command_no_server_url(self):
        """Test command execution fails without server URL."""
        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="admin123",
            role="admin",
            server_url="",
            command="list",
        )

        assert result["success"] is False
        assert "server url is required" in result["message"].lower()

    def test_execute_command_no_command(self):
        """Test command execution fails without command."""
        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="admin123",
            role="admin",
            server_url="http://localhost:11434",
            command="",
        )

        assert result["success"] is False
        assert "Command is required" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_execute_command_strips_whitespace(self, mock_request):
        """Test that server URL and command are stripped."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"output": "OK"}
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        client.execute_command(
            session_id="admin123",
            role="admin",
            server_url="  http://localhost:11434  ",
            command="  list  ",
        )

        # Verify whitespace was stripped
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["server_url"] == "http://localhost:11434"
        assert call_kwargs["json"]["command"] == "list"

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_execute_command_permission_denied(self, mock_request):
        """Test command execution with 403 response."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Forbidden"}
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="admin123",
            role="admin",
            server_url="http://localhost:11434",
            command="list",
        )

        assert result["success"] is False
        assert "Insufficient permissions" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_execute_command_timeout(self, mock_request):
        """Test command execution handles timeout."""
        import requests

        mock_request.side_effect = requests.exceptions.Timeout()

        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="admin123",
            role="admin",
            server_url="http://localhost:11434",
            command="pull llama2",
        )

        assert result["success"] is False
        assert "timed out" in result["message"]
        assert "may still be running" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_execute_command_server_error(self, mock_request):
        """Test command execution handles server errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal error"}
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="admin123",
            role="admin",
            server_url="http://localhost:11434",
            command="list",
        )

        assert result["success"] is False
        assert result["error"] is not None

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_execute_command_no_output(self, mock_request):
        """Test command execution with no output."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.execute_command(
            session_id="admin123",
            role="admin",
            server_url="http://localhost:11434",
            command="list",
        )

        assert result["success"] is True
        assert "No output returned" in result["message"]


class TestOllamaAPIClientClearContext:
    """Tests for clear_context functionality."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_clear_context(self, mock_request):
        """Test successful context clearing."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Context cleared successfully",
        }
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.clear_context(session_id="admin123", role="admin")

        # Verify request
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["session_id"] == "admin123"
        assert call_kwargs["timeout"] == 10

        # Verify response
        assert result["success"] is True
        assert "Context cleared" in result["message"]
        assert result["error"] is None

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_clear_context_superuser(self, mock_request):
        """Test context clearing as superuser."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Done"}
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.clear_context(session_id="super123", role="superuser")

        assert result["success"] is True

    def test_clear_context_not_logged_in(self):
        """Test context clearing fails when not logged in."""
        client = OllamaAPIClient()
        result = client.clear_context(session_id=None, role="player")

        assert result["success"] is False
        assert "not logged in" in result["message"]

    def test_clear_context_no_permission(self):
        """Test context clearing fails for player role."""
        client = OllamaAPIClient()
        result = client.clear_context(session_id="player123", role="player")

        assert result["success"] is False
        assert "Admin or Superuser role required" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_clear_context_permission_denied(self, mock_request):
        """Test context clearing with 403 response."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Forbidden"}
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.clear_context(session_id="admin123", role="admin")

        assert result["success"] is False
        assert "Insufficient permissions" in result["message"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_clear_context_server_error(self, mock_request):
        """Test context clearing handles server errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Server error"}
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.clear_context(session_id="admin123", role="admin")

        assert result["success"] is False
        assert result["error"] is not None

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_clear_context_default_message(self, mock_request):
        """Test context clearing with no message in response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client = OllamaAPIClient()
        result = client.clear_context(session_id="admin123", role="admin")

        assert result["success"] is True
        assert "Context cleared" in result["message"]


class TestOllamaAPIClientInit:
    """Tests for OllamaAPIClient initialization."""

    def test_inherits_from_base_client(self):
        """Test that OllamaAPIClient inherits from BaseAPIClient."""
        from mud_server.admin_gradio.api.base import BaseAPIClient

        client = OllamaAPIClient()
        assert isinstance(client, BaseAPIClient)

    def test_custom_server_url(self):
        """Test initialization with custom server URL."""
        client = OllamaAPIClient(server_url="http://ollama-server:9000")
        assert client.server_url == "http://ollama-server:9000"
