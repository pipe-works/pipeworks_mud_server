"""
Tests for configuration module.

This module tests the Config class and its methods for parsing
configuration from command-line arguments and environment variables.
"""

import os
from unittest.mock import patch

import pytest

from mud_server.admin_tui.config import (
    DEFAULT_SERVER_URL,
    DEFAULT_TIMEOUT,
    ENV_SERVER_URL,
    ENV_TIMEOUT,
    Config,
)

# =============================================================================
# CONFIG INITIALIZATION TESTS
# =============================================================================


class TestConfigInitialization:
    """Tests for Config dataclass initialization."""

    def test_valid_config_creation(self):
        """Test creating a valid Config instance."""
        config = Config(server_url="http://localhost:8000", timeout=30.0)

        assert config.server_url == "http://localhost:8000"
        assert config.timeout == 30.0

    def test_config_is_frozen(self):
        """Test that Config is immutable (frozen dataclass)."""
        config = Config(server_url="http://localhost:8000", timeout=30.0)

        with pytest.raises(AttributeError):
            config.server_url = "http://other:8000"  # type: ignore[misc]

    def test_empty_server_url_raises_error(self):
        """Test that empty server_url raises ValueError."""
        with pytest.raises(ValueError, match="server_url cannot be empty"):
            Config(server_url="", timeout=30.0)

    def test_zero_timeout_raises_error(self):
        """Test that zero timeout raises ValueError."""
        with pytest.raises(ValueError, match="timeout must be a positive number"):
            Config(server_url="http://localhost:8000", timeout=0)

    def test_negative_timeout_raises_error(self):
        """Test that negative timeout raises ValueError."""
        with pytest.raises(ValueError, match="timeout must be a positive number"):
            Config(server_url="http://localhost:8000", timeout=-5.0)


# =============================================================================
# CONFIG FROM ARGS TESTS
# =============================================================================


class TestConfigFromArgs:
    """Tests for Config.from_args() class method."""

    def test_default_values(self):
        """Test that defaults are used when no args provided."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_args([])

            assert config.server_url == DEFAULT_SERVER_URL
            assert config.timeout == DEFAULT_TIMEOUT

    def test_server_url_from_cli(self):
        """Test server URL from command-line argument."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_args(["--server", "http://example.com:8000"])

            assert config.server_url == "http://example.com:8000"

    def test_server_url_short_flag(self):
        """Test server URL with short -s flag."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_args(["-s", "http://example.com:8000"])

            assert config.server_url == "http://example.com:8000"

    def test_timeout_from_cli(self):
        """Test timeout from command-line argument."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_args(["--timeout", "60.0"])

            assert config.timeout == 60.0

    def test_timeout_short_flag(self):
        """Test timeout with short -t flag."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_args(["-t", "45.5"])

            assert config.timeout == 45.5

    def test_server_url_from_env_var(self):
        """Test server URL from environment variable."""
        with patch.dict(os.environ, {ENV_SERVER_URL: "http://env-server:8000"}, clear=True):
            config = Config.from_args([])

            assert config.server_url == "http://env-server:8000"

    def test_timeout_from_env_var(self):
        """Test timeout from environment variable."""
        with patch.dict(os.environ, {ENV_TIMEOUT: "120.0"}, clear=True):
            config = Config.from_args([])

            assert config.timeout == 120.0

    def test_cli_overrides_env_var(self):
        """Test that CLI args take precedence over environment variables."""
        with patch.dict(
            os.environ,
            {ENV_SERVER_URL: "http://env-server:8000", ENV_TIMEOUT: "120.0"},
            clear=True,
        ):
            config = Config.from_args(["--server", "http://cli-server:9000", "--timeout", "15.0"])

            assert config.server_url == "http://cli-server:9000"
            assert config.timeout == 15.0

    def test_trailing_slash_removed(self):
        """Test that trailing slash is removed from server URL."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_args(["--server", "http://example.com:8000/"])

            assert config.server_url == "http://example.com:8000"

    def test_multiple_trailing_slashes_removed(self):
        """Test that multiple trailing slashes are removed."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_args(["--server", "http://example.com:8000///"])

            assert config.server_url == "http://example.com:8000"


# =============================================================================
# EDGE CASES
# =============================================================================


class TestConfigEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_small_timeout(self):
        """Test that very small (but positive) timeout is valid."""
        config = Config(server_url="http://localhost:8000", timeout=0.001)
        assert config.timeout == 0.001

    def test_very_large_timeout(self):
        """Test that very large timeout is valid."""
        config = Config(server_url="http://localhost:8000", timeout=3600.0)
        assert config.timeout == 3600.0

    def test_ipv4_server_url(self):
        """Test IPv4 address in server URL."""
        config = Config(server_url="http://192.168.1.1:8000", timeout=30.0)
        assert config.server_url == "http://192.168.1.1:8000"

    def test_localhost_variations(self):
        """Test various localhost representations."""
        urls = [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://0.0.0.0:8000",
        ]
        for url in urls:
            config = Config(server_url=url, timeout=30.0)
            assert config.server_url == url

    def test_https_url(self):
        """Test HTTPS URL is accepted."""
        config = Config(server_url="https://secure.example.com:8000", timeout=30.0)
        assert config.server_url == "https://secure.example.com:8000"
