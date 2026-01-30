"""
Tests for API server port discovery functionality.

This module tests the automatic port discovery features in the API server:
- is_port_available(): Check if a TCP port is free
- find_available_port(): Find an available port in a range
- start_server(): Server startup with port configuration

These tests use socket mocking to simulate various port availability scenarios
without actually binding to ports, which would be flaky in CI environments.
"""

import socket
from unittest.mock import MagicMock, patch

import pytest

from mud_server.api.server import (
    DEFAULT_PORT,
    PORT_RANGE_END,
    PORT_RANGE_START,
    find_available_port,
    is_port_available,
)


# ============================================================================
# is_port_available() Tests
# ============================================================================


class TestIsPortAvailable:
    """Tests for the is_port_available function."""

    def test_returns_true_when_port_is_free(self):
        """Port should be reported available when bind succeeds."""
        with patch("socket.socket") as mock_socket_class:
            # Configure mock socket that binds successfully
            mock_socket = MagicMock()
            mock_socket.__enter__ = MagicMock(return_value=mock_socket)
            mock_socket.__exit__ = MagicMock(return_value=False)
            mock_socket.bind = MagicMock()  # No exception = success
            mock_socket_class.return_value = mock_socket

            result = is_port_available(8000)

            assert result is True
            mock_socket.bind.assert_called_once_with(("0.0.0.0", 8000))

    def test_returns_false_when_port_in_use(self):
        """Port should be reported unavailable when bind raises OSError."""
        with patch("socket.socket") as mock_socket_class:
            # Configure mock socket that fails to bind
            mock_socket = MagicMock()
            mock_socket.__enter__ = MagicMock(return_value=mock_socket)
            mock_socket.__exit__ = MagicMock(return_value=False)
            mock_socket.bind = MagicMock(side_effect=OSError("Address already in use"))
            mock_socket_class.return_value = mock_socket

            result = is_port_available(8000)

            assert result is False

    def test_uses_custom_host(self):
        """Should check availability on the specified host interface."""
        with patch("socket.socket") as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket.__enter__ = MagicMock(return_value=mock_socket)
            mock_socket.__exit__ = MagicMock(return_value=False)
            mock_socket.bind = MagicMock()
            mock_socket_class.return_value = mock_socket

            is_port_available(8080, host="127.0.0.1")

            mock_socket.bind.assert_called_once_with(("127.0.0.1", 8080))

    def test_uses_tcp_socket(self):
        """Should create a TCP (SOCK_STREAM) socket for checking."""
        with patch("socket.socket") as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket.__enter__ = MagicMock(return_value=mock_socket)
            mock_socket.__exit__ = MagicMock(return_value=False)
            mock_socket.bind = MagicMock()
            mock_socket_class.return_value = mock_socket

            is_port_available(8000)

            mock_socket_class.assert_called_once_with(
                socket.AF_INET, socket.SOCK_STREAM
            )


# ============================================================================
# find_available_port() Tests
# ============================================================================


class TestFindAvailablePort:
    """Tests for the find_available_port function."""

    def test_returns_preferred_port_when_available(self):
        """Should return the preferred port if it's available."""
        with patch(
            "mud_server.api.server.is_port_available", return_value=True
        ) as mock_check:
            result = find_available_port(preferred_port=8000)

            assert result == 8000
            # Should only check the preferred port
            mock_check.assert_called_once_with(8000, "0.0.0.0")

    def test_finds_next_available_when_preferred_in_use(self):
        """Should scan and find next available port when preferred is in use."""

        def port_availability(port, host="0.0.0.0"):
            # 8000 is in use, 8001 is available
            return port != 8000

        with patch(
            "mud_server.api.server.is_port_available", side_effect=port_availability
        ):
            result = find_available_port(preferred_port=8000)

            assert result == 8001

    def test_skips_preferred_port_during_scan(self):
        """Should not re-check preferred port during range scan."""

        def port_availability(port, host="0.0.0.0"):
            # All ports except 8005 are in use
            return port == 8005

        with patch(
            "mud_server.api.server.is_port_available", side_effect=port_availability
        ) as mock_check:
            result = find_available_port(preferred_port=8000)

            assert result == 8005
            # Verify 8000 was only checked once (not again during scan)
            calls_for_8000 = [c for c in mock_check.call_args_list if c[0][0] == 8000]
            assert len(calls_for_8000) == 1

    def test_returns_none_when_no_ports_available(self):
        """Should return None when all ports in range are in use."""
        with patch("mud_server.api.server.is_port_available", return_value=False):
            result = find_available_port()

            assert result is None

    def test_uses_custom_range(self):
        """Should respect custom port range parameters."""

        def port_availability(port, host="0.0.0.0"):
            # Only port 9005 is available
            return port == 9005

        with patch(
            "mud_server.api.server.is_port_available", side_effect=port_availability
        ):
            result = find_available_port(
                preferred_port=9000, range_start=9000, range_end=9010
            )

            assert result == 9005

    def test_uses_custom_host(self):
        """Should pass custom host to availability checks."""
        with patch(
            "mud_server.api.server.is_port_available", return_value=True
        ) as mock_check:
            find_available_port(host="127.0.0.1")

            mock_check.assert_called_with(DEFAULT_PORT, "127.0.0.1")

    def test_default_range_constants(self):
        """Should use correct default range values."""
        assert DEFAULT_PORT == 8000
        assert PORT_RANGE_START == 8000
        assert PORT_RANGE_END == 8099


# ============================================================================
# Integration-style tests (test actual socket behavior)
# ============================================================================


class TestPortDiscoveryIntegration:
    """Integration tests that use actual socket operations.

    These tests verify the actual socket behavior but may be flaky in
    CI environments where ports might be randomly in use. They're marked
    as integration tests and can be skipped if needed.
    """

    @pytest.mark.integration
    def test_detects_actually_available_port(self):
        """Verify is_port_available works with real sockets on a high port."""
        # Use a high port that's unlikely to be in use
        # Note: This could still be flaky if something uses this port
        result = is_port_available(59999)
        # We can't assert True because it might actually be in use
        # Just verify it returns a boolean
        assert isinstance(result, bool)

    @pytest.mark.integration
    def test_find_available_finds_something(self):
        """Verify find_available_port can find a real available port."""
        # Use a high port range unlikely to be fully occupied
        result = find_available_port(
            preferred_port=59900, range_start=59900, range_end=59999
        )
        # Should find at least one available port in a 100-port range
        assert result is not None
        assert 59900 <= result <= 59999
