"""Unit tests for OllamaRenderer."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from mud_server.translation.renderer import OllamaRenderer

ENDPOINT = "http://localhost:11434/api/chat"
MODEL = "gemma2:2b"


@pytest.fixture
def renderer():
    return OllamaRenderer(
        api_endpoint=ENDPOINT,
        model=MODEL,
        timeout_seconds=10.0,
    )


def _mock_ollama_response(content: str) -> MagicMock:
    """Build a mock requests.Response for a successful Ollama reply."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"message": {"content": content}}
    return mock_resp


class TestRenderSuccess:
    def test_returns_content_string(self, renderer):
        with patch("requests.post", return_value=_mock_ollama_response("Got any bread?")) as mock:
            result = renderer.render("system prompt", "I want bread")
        assert result == "Got any bread?"
        mock.assert_called_once()

    def test_passes_correct_model(self, renderer):
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            renderer.render("prompt", "msg")
        payload = mock.call_args[1]["json"]
        assert payload["model"] == MODEL

    def test_stream_is_false(self, renderer):
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            renderer.render("prompt", "msg")
        payload = mock.call_args[1]["json"]
        assert payload["stream"] is False

    def test_messages_contain_system_and_user(self, renderer):
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            renderer.render("my system prompt", "my user message")
        messages = mock.call_args[1]["json"]["messages"]
        assert messages[0] == {"role": "system", "content": "my system prompt"}
        assert messages[1] == {"role": "user", "content": "my user message"}

    def test_empty_content_returns_none(self, renderer):
        with patch("requests.post", return_value=_mock_ollama_response("")):
            result = renderer.render("prompt", "msg")
        assert result is None

    def test_whitespace_only_content_returns_none(self, renderer):
        with patch("requests.post", return_value=_mock_ollama_response("   \n  ")):
            result = renderer.render("prompt", "msg")
        assert result is None


class TestRenderNetworkFailures:
    def test_timeout_returns_none(self, renderer):
        with patch("requests.post", side_effect=requests.exceptions.Timeout):
            result = renderer.render("prompt", "msg")
        assert result is None

    def test_connection_error_returns_none(self, renderer):
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError):
            result = renderer.render("prompt", "msg")
        assert result is None

    def test_generic_request_exception_returns_none(self, renderer):
        with patch("requests.post", side_effect=requests.exceptions.RequestException("boom")):
            result = renderer.render("prompt", "msg")
        assert result is None

    def test_http_error_returns_none(self, renderer):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        with patch("requests.post", return_value=mock_resp):
            result = renderer.render("prompt", "msg")
        assert result is None


class TestDeterministicMode:
    def test_set_deterministic_clamps_temperature(self, renderer):
        renderer.set_deterministic(42)
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            renderer.render("prompt", "msg")
        options = mock.call_args[1]["json"]["options"]
        assert options["temperature"] == 0.0

    def test_set_deterministic_includes_seed(self, renderer):
        renderer.set_deterministic(99999)
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            renderer.render("prompt", "msg")
        options = mock.call_args[1]["json"]["options"]
        assert options["seed"] == 99999

    def test_no_seed_without_set_deterministic(self, renderer):
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            renderer.render("prompt", "msg")
        options = mock.call_args[1]["json"]["options"]
        assert "seed" not in options

    def test_default_temperature_used_without_deterministic(self, renderer):
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            renderer.render("prompt", "msg")
        options = mock.call_args[1]["json"]["options"]
        # Default temperature is 0.7 (from renderer.py constant)
        assert options["temperature"] == 0.7


class TestKeepAlive:
    def test_default_keep_alive_is_5m(self, renderer):
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            renderer.render("prompt", "msg")
        payload = mock.call_args[1]["json"]
        assert payload["keep_alive"] == "5m"

    def test_custom_keep_alive_forwarded(self):
        r = OllamaRenderer(
            api_endpoint=ENDPOINT,
            model=MODEL,
            timeout_seconds=10.0,
            keep_alive="10m",
        )
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            r.render("prompt", "msg")
        payload = mock.call_args[1]["json"]
        assert payload["keep_alive"] == "10m"

    def test_keep_alive_zero_to_unload(self):
        r = OllamaRenderer(
            api_endpoint=ENDPOINT,
            model=MODEL,
            timeout_seconds=10.0,
            keep_alive="0",
        )
        with patch("requests.post", return_value=_mock_ollama_response("ok")) as mock:
            r.render("prompt", "msg")
        payload = mock.call_args[1]["json"]
        assert payload["keep_alive"] == "0"
