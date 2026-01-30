"""
Tests for base API client.

This module tests the BaseAPIClient class, verifying:
- Request execution (GET, POST)
- Error handling (connection errors, timeouts, exceptions)
- Response parsing and formatting
- Server URL configuration
"""

from unittest.mock import Mock, patch

import requests

from mud_server.admin_gradio.api.base import BaseAPIClient


class TestBaseAPIClientInit:
    """Tests for BaseAPIClient initialization."""

    def test_default_server_url(self):
        """Test that default server URL is used when not provided."""
        client = BaseAPIClient()
        assert client.server_url == "http://localhost:8000"

    def test_custom_server_url(self):
        """Test that custom server URL can be provided."""
        client = BaseAPIClient(server_url="http://example.com:9000")
        assert client.server_url == "http://example.com:9000"

    def test_env_var_server_url(self, monkeypatch):
        """Test that MUD_SERVER_URL environment variable is respected."""
        monkeypatch.setenv("MUD_SERVER_URL", "http://env-server:7000")
        client = BaseAPIClient()
        assert client.server_url == "http://env-server:7000"

    def test_explicit_url_overrides_env(self, monkeypatch):
        """Test that explicit URL parameter overrides environment variable."""
        monkeypatch.setenv("MUD_SERVER_URL", "http://env-server:7000")
        client = BaseAPIClient(server_url="http://explicit:8000")
        assert client.server_url == "http://explicit:8000"


class TestBaseAPIClientPost:
    """Tests for POST request handling."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_post_request(self, mock_request):
        """Test successful POST request returns expected format."""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Success", "data": {"key": "value"}}
        mock_request.return_value = mock_response

        # Make request
        client = BaseAPIClient()
        result = client.post("/test", json={"input": "data"})

        # Verify request was made correctly
        mock_request.assert_called_once_with(
            method="POST",
            url="http://localhost:8000/test",
            json={"input": "data"},
            params=None,
            timeout=30,
        )

        # Verify response format
        assert result["success"] is True
        assert result["data"] == {"message": "Success", "data": {"key": "value"}}
        assert result["error"] is None
        assert result["status_code"] == 200

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_post_with_custom_timeout(self, mock_request):
        """Test POST request with custom timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        client.post("/test", timeout=60)

        # Verify timeout was passed
        assert mock_request.call_args.kwargs["timeout"] == 60

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_post_request_failure_with_detail(self, mock_request):
        """Test POST request failure with error detail in response."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid input"}
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        result = client.post("/test", json={"bad": "data"})

        assert result["success"] is False
        assert result["data"] is None
        assert result["error"] == "Invalid input"
        assert result["status_code"] == 400

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_post_request_failure_without_detail(self, mock_request):
        """Test POST request failure without error detail."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        result = client.post("/test")

        assert result["success"] is False
        assert result["error"] == "Request failed with status 500"
        assert result["status_code"] == 500

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_post_connection_error(self, mock_request):
        """Test POST request with connection error."""
        mock_request.side_effect = requests.exceptions.ConnectionError()

        client = BaseAPIClient()
        result = client.post("/test")

        assert result["success"] is False
        assert "Cannot connect to server" in result["error"]
        assert result["status_code"] == 0

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_post_timeout_error(self, mock_request):
        """Test POST request with timeout."""
        mock_request.side_effect = requests.exceptions.Timeout()

        client = BaseAPIClient()
        result = client.post("/test", timeout=5)

        assert result["success"] is False
        assert "timed out after 5 seconds" in result["error"]
        assert result["status_code"] == 0

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_post_unexpected_exception(self, mock_request):
        """Test POST request with unexpected exception."""
        mock_request.side_effect = ValueError("Unexpected error")

        client = BaseAPIClient()
        result = client.post("/test")

        assert result["success"] is False
        assert "Unexpected error" in result["error"]
        assert result["status_code"] == 0

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_post_invalid_json_response(self, mock_request):
        """Test POST request with invalid JSON in response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        result = client.post("/test")

        # Should handle invalid JSON gracefully
        assert result["success"] is True
        assert result["data"] == {}


class TestBaseAPIClientGet:
    """Tests for GET request handling."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_successful_get_request(self, mock_request):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": [1, 2, 3]}
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        result = client.get("/items")

        mock_request.assert_called_once_with(
            method="GET",
            url="http://localhost:8000/items",
            json=None,
            params=None,
            timeout=30,
        )

        assert result["success"] is True
        assert result["data"] == {"items": [1, 2, 3]}

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_with_query_params(self, mock_request):
        """Test GET request with query parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        client.get("/search", params={"q": "test", "limit": 10})

        # Verify params were passed
        assert mock_request.call_args.kwargs["params"] == {"q": "test", "limit": 10}

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_connection_error(self, mock_request):
        """Test GET request with connection error."""
        mock_request.side_effect = requests.exceptions.ConnectionError()

        client = BaseAPIClient(server_url="http://unreachable:9999")
        result = client.get("/test")

        assert result["success"] is False
        assert "Cannot connect to server at http://unreachable:9999" in result["error"]

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_401_unauthorized(self, mock_request):
        """Test GET request with 401 unauthorized."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Session expired"}
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        result = client.get("/protected")

        assert result["success"] is False
        assert result["error"] == "Session expired"
        assert result["status_code"] == 401

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_get_403_forbidden(self, mock_request):
        """Test GET request with 403 forbidden."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Insufficient permissions"}
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        result = client.get("/admin")

        assert result["success"] is False
        assert result["error"] == "Insufficient permissions"
        assert result["status_code"] == 403


class TestBaseAPIClientMakeRequest:
    """Tests for internal _make_request method."""

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_method_normalization(self, mock_request):
        """Test that HTTP method is normalized to uppercase."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        client._make_request("post", "/test")

        # Verify method was uppercased
        assert mock_request.call_args.kwargs["method"] == "POST"

    @patch("mud_server.admin_gradio.api.base.requests.request")
    def test_both_json_and_params(self, mock_request):
        """Test request with both JSON body and query params."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client = BaseAPIClient()
        client._make_request(
            "POST",
            "/test",
            json={"body": "data"},
            params={"query": "param"},
        )

        # Verify both were passed
        assert mock_request.call_args.kwargs["json"] == {"body": "data"}
        assert mock_request.call_args.kwargs["params"] == {"query": "param"}
