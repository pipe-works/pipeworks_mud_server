"""
Tests for CLI port configuration and server process management.

This module tests the command-line interface for server startup:
- Port and host argument parsing
- Module-level process functions (_run_api_server, _run_ui_client)
- cmd_run command behavior

The tests use mocking to avoid actually starting servers, which would
block the test runner and create port conflicts.
"""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from mud_server.cli import _run_api_server, _run_ui_client, cmd_run, main

# ============================================================================
# Module-level Process Function Tests
# ============================================================================


class TestRunApiServer:
    """Tests for the _run_api_server module-level function."""

    def test_calls_start_server_with_host_and_port(self):
        """Should pass host and port to start_server."""
        with patch("mud_server.api.server.start_server") as mock_start:
            _run_api_server(host="127.0.0.1", port=9000)

            mock_start.assert_called_once_with(host="127.0.0.1", port=9000)

    def test_calls_start_server_with_none_values(self):
        """Should handle None values for host and port."""
        with patch("mud_server.api.server.start_server") as mock_start:
            _run_api_server(host=None, port=None)

            mock_start.assert_called_once_with(host=None, port=None)


class TestRunUiClient:
    """Tests for the _run_ui_client module-level function."""

    def test_calls_launch_client_with_host_and_port(self):
        """Should pass host and port to launch_client."""
        with patch("mud_server.admin_gradio.app.launch_client") as mock_launch:
            _run_ui_client(host="127.0.0.1", port=8080)

            mock_launch.assert_called_once_with(host="127.0.0.1", port=8080)

    def test_calls_launch_client_with_none_values(self):
        """Should handle None values for host and port."""
        with patch("mud_server.admin_gradio.app.launch_client") as mock_launch:
            _run_ui_client(host=None, port=None)

            mock_launch.assert_called_once_with(host=None, port=None)


# ============================================================================
# cmd_run Tests
# ============================================================================


class TestCmdRun:
    """Tests for the cmd_run CLI command handler."""

    @pytest.fixture
    def mock_args(self):
        """Create a mock argparse.Namespace with default values."""
        args = argparse.Namespace()
        args.port = None
        args.ui_port = None
        args.host = None
        args.api_only = False
        return args

    @pytest.fixture
    def mock_db_exists(self, tmp_path):
        """Create a database file that exists for testing."""
        from mud_server.config import config

        db_file = tmp_path / "test.db"
        db_file.touch()  # Create the file so .exists() returns True
        original_path = config.database.path
        config.database.path = str(db_file)
        yield db_file
        config.database.path = original_path

    def test_initializes_database_if_not_exists(self, mock_args, tmp_path):
        """Should initialize database when it doesn't exist."""
        from mud_server.config import config

        db_file = tmp_path / "nonexistent.db"  # Don't create it
        original_path = config.database.path
        config.database.path = str(db_file)

        try:
            with (
                patch("mud_server.db.database.init_database") as mock_init_db,
                patch("mud_server.api.server.find_available_port", return_value=8000),
                patch("mud_server.api.server.start_server"),
            ):
                mock_args.api_only = True  # Avoid multiprocessing complexity

                cmd_run(mock_args)

                mock_init_db.assert_called_once()
        finally:
            config.database.path = original_path

    def test_skips_db_init_if_exists(self, mock_args, mock_db_exists):
        """Should not initialize database when it already exists."""
        with (
            patch("mud_server.db.database.init_database") as mock_init_db,
            patch("mud_server.api.server.find_available_port", return_value=8000),
            patch("mud_server.api.server.start_server"),
        ):
            mock_args.api_only = True

            cmd_run(mock_args)

            mock_init_db.assert_not_called()

    def test_api_only_mode_runs_api_directly(self, mock_args, mock_db_exists):
        """Should run API server directly when --api-only is set."""
        with (
            patch("mud_server.api.server.start_server") as mock_start,
            patch("mud_server.api.server.find_available_port", return_value=9000),
            patch("multiprocessing.Process") as mock_process,
        ):
            mock_args.api_only = True
            mock_args.port = 9000
            mock_args.host = "127.0.0.1"

            result = cmd_run(mock_args)

            # Should call with auto_discover=False since port was pre-discovered
            mock_start.assert_called_once_with(host="127.0.0.1", port=9000, auto_discover=False)
            # Should not use multiprocessing in api_only mode
            mock_process.assert_not_called()
            assert result == 0

    def test_full_mode_starts_both_processes(self, mock_args, mock_db_exists):
        """Should start both API and UI as separate processes."""
        with (
            patch("mud_server.api.server.find_available_port", return_value=9000),
            patch("multiprocessing.Process") as mock_process_class,
        ):
            # Create mock processes
            mock_api_proc = MagicMock()
            mock_ui_proc = MagicMock()
            mock_process_class.side_effect = [mock_api_proc, mock_ui_proc]

            mock_args.port = 9000
            mock_args.ui_port = 8080
            mock_args.host = "0.0.0.0"

            result = cmd_run(mock_args)

            # Verify both processes were created
            assert mock_process_class.call_count == 2

            # Verify API process configuration - uses _run_api_server_on_port now
            api_call = mock_process_class.call_args_list[0]
            assert api_call.kwargs["target"].__name__ == "_run_api_server_on_port"
            assert api_call.kwargs["args"] == ("0.0.0.0", 9000)
            assert api_call.kwargs["name"] == "mud-api-server"

            # Verify UI process configuration
            ui_call = mock_process_class.call_args_list[1]
            assert ui_call.kwargs["target"].__name__ == "_run_ui_client"
            assert ui_call.kwargs["args"] == ("0.0.0.0", 8080)
            assert ui_call.kwargs["name"] == "mud-ui-client"

            # Verify processes were started and joined
            mock_api_proc.start.assert_called_once()
            mock_ui_proc.start.assert_called_once()
            mock_api_proc.join.assert_called_once()
            mock_ui_proc.join.assert_called_once()

            assert result == 0

    def test_handles_keyboard_interrupt(self, mock_args, mock_db_exists, capsys):
        """Should handle Ctrl+C gracefully and return 0."""
        with (
            patch("mud_server.api.server.find_available_port", return_value=8000),
            patch("mud_server.api.server.start_server") as mock_start,
        ):
            mock_start.side_effect = KeyboardInterrupt()
            mock_args.api_only = True

            result = cmd_run(mock_args)

            assert result == 0
            captured = capsys.readouterr()
            assert "Server stopped" in captured.out

    def test_handles_exception_with_error_return(self, mock_args, mock_db_exists, capsys):
        """Should handle exceptions and return 1."""
        with (
            patch("mud_server.api.server.find_available_port", return_value=8000),
            patch("mud_server.api.server.start_server") as mock_start,
        ):
            mock_start.side_effect = RuntimeError("Test error")
            mock_args.api_only = True

            result = cmd_run(mock_args)

            assert result == 1
            captured = capsys.readouterr()
            assert "Error starting server" in captured.err


# ============================================================================
# CLI Argument Parsing Tests
# ============================================================================


class TestCliArgumentParsing:
    """Tests for CLI argument parsing."""

    def test_run_command_with_port_argument(self):
        """Should parse --port argument correctly."""
        with patch("mud_server.cli.cmd_run") as mock_cmd:
            mock_cmd.return_value = 0

            # Simulate: mud-server run --port 9000
            with patch("sys.argv", ["mud-server", "run", "--port", "9000"]):
                main()

            args = mock_cmd.call_args[0][0]
            assert args.port == 9000

    def test_run_command_with_short_port_argument(self):
        """Should parse -p argument correctly."""
        with patch("mud_server.cli.cmd_run") as mock_cmd:
            mock_cmd.return_value = 0

            # Simulate: mud-server run -p 9000
            with patch("sys.argv", ["mud-server", "run", "-p", "9000"]):
                main()

            args = mock_cmd.call_args[0][0]
            assert args.port == 9000

    def test_run_command_with_ui_port_argument(self):
        """Should parse --ui-port argument correctly."""
        with patch("mud_server.cli.cmd_run") as mock_cmd:
            mock_cmd.return_value = 0

            # Simulate: mud-server run --ui-port 8080
            with patch("sys.argv", ["mud-server", "run", "--ui-port", "8080"]):
                main()

            args = mock_cmd.call_args[0][0]
            assert args.ui_port == 8080

    def test_run_command_with_host_argument(self):
        """Should parse --host argument correctly."""
        with patch("mud_server.cli.cmd_run") as mock_cmd:
            mock_cmd.return_value = 0

            # Simulate: mud-server run --host 127.0.0.1
            with patch("sys.argv", ["mud-server", "run", "--host", "127.0.0.1"]):
                main()

            args = mock_cmd.call_args[0][0]
            assert args.host == "127.0.0.1"

    def test_run_command_with_api_only_flag(self):
        """Should parse --api-only flag correctly."""
        with patch("mud_server.cli.cmd_run") as mock_cmd:
            mock_cmd.return_value = 0

            # Simulate: mud-server run --api-only
            with patch("sys.argv", ["mud-server", "run", "--api-only"]):
                main()

            args = mock_cmd.call_args[0][0]
            assert args.api_only is True

    def test_run_command_with_all_arguments(self):
        """Should parse all arguments correctly when combined."""
        with patch("mud_server.cli.cmd_run") as mock_cmd:
            mock_cmd.return_value = 0

            # Simulate: mud-server run --port 9000 --ui-port 8080 --host 127.0.0.1 --api-only
            with patch(
                "sys.argv",
                [
                    "mud-server",
                    "run",
                    "--port",
                    "9000",
                    "--ui-port",
                    "8080",
                    "--host",
                    "127.0.0.1",
                    "--api-only",
                ],
            ):
                main()

            args = mock_cmd.call_args[0][0]
            assert args.port == 9000
            assert args.ui_port == 8080
            assert args.host == "127.0.0.1"
            assert args.api_only is True

    def test_run_command_defaults_to_none(self):
        """Should default port/host arguments to None when not provided."""
        with patch("mud_server.cli.cmd_run") as mock_cmd:
            mock_cmd.return_value = 0

            # Simulate: mud-server run (no arguments)
            with patch("sys.argv", ["mud-server", "run"]):
                main()

            args = mock_cmd.call_args[0][0]
            assert args.port is None
            assert args.ui_port is None
            assert args.host is None
            assert args.api_only is False
