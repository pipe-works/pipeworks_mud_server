"""
Unit tests for CLI module (mud_server/cli.py).

Tests cover:
- Command parsing
- init-db command
- create-superuser command (with env vars and interactive)
- Environment variable handling
"""

import argparse
from unittest.mock import patch

import pytest

from mud_server import cli
from tests.constants import TEST_PASSWORD

# ============================================================================
# ENVIRONMENT VARIABLE TESTS
# ============================================================================


@pytest.mark.unit
def test_get_superuser_credentials_from_env_both_set():
    """Test getting credentials when both env vars are set."""
    with patch.dict("os.environ", {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": "secret123"}):
        result = cli.get_superuser_credentials_from_env()
        assert result == ("admin", "secret123")


@pytest.mark.unit
def test_get_superuser_credentials_from_env_user_missing():
    """Test getting credentials when MUD_ADMIN_USER is missing."""
    with patch.dict("os.environ", {"MUD_ADMIN_PASSWORD": "secret123"}, clear=True):
        result = cli.get_superuser_credentials_from_env()
        assert result is None


@pytest.mark.unit
def test_get_superuser_credentials_from_env_password_missing():
    """Test getting credentials when MUD_ADMIN_PASSWORD is missing."""
    with patch.dict("os.environ", {"MUD_ADMIN_USER": "admin"}, clear=True):
        result = cli.get_superuser_credentials_from_env()
        assert result is None


@pytest.mark.unit
def test_get_superuser_credentials_from_env_neither_set():
    """Test getting credentials when neither env var is set."""
    with patch.dict("os.environ", {}, clear=True):
        result = cli.get_superuser_credentials_from_env()
        assert result is None


# ============================================================================
# INIT-DB COMMAND TESTS
# ============================================================================


@pytest.mark.unit
def test_cmd_init_db_success():
    """Test init-db command succeeds."""
    with patch("mud_server.db.database.init_database") as mock_init:
        args = argparse.Namespace()
        result = cli.cmd_init_db(args)

        assert result == 0
        mock_init.assert_called_once()


@pytest.mark.unit
def test_cmd_init_db_error():
    """Test init-db command handles errors."""
    with patch("mud_server.db.database.init_database", side_effect=Exception("DB error")):
        args = argparse.Namespace()
        result = cli.cmd_init_db(args)

        assert result == 1


# ============================================================================
# CREATE-SUPERUSER COMMAND TESTS
# ============================================================================


@pytest.mark.unit
def test_cmd_create_superuser_from_env_vars():
    """Test create-superuser uses environment variables."""
    with patch("mud_server.db.database.init_database"):
        with patch("mud_server.db.database.user_exists", return_value=False):
            with patch("mud_server.db.database.create_user_with_password", return_value=True):
                # Password must meet STANDARD policy: 12+ chars, no sequences (123, abc)
                with patch.dict(
                    "os.environ",
                    {"MUD_ADMIN_USER": "envadmin", "MUD_ADMIN_PASSWORD": TEST_PASSWORD},
                ):
                    args = argparse.Namespace()
                    result = cli.cmd_create_superuser(args)

                    assert result == 0


@pytest.mark.unit
def test_cmd_create_superuser_user_exists():
    """Test create-superuser fails if user already exists."""
    with patch("mud_server.db.database.init_database"):
        with patch("mud_server.db.database.user_exists", return_value=True):
            # Use valid password to ensure we test the "user exists" failure path
            with patch.dict(
                "os.environ",
                {"MUD_ADMIN_USER": "existing", "MUD_ADMIN_PASSWORD": TEST_PASSWORD},
            ):
                args = argparse.Namespace()
                result = cli.cmd_create_superuser(args)

                assert result == 1


@pytest.mark.unit
def test_cmd_create_superuser_short_password():
    """Test create-superuser fails with short password."""
    with patch("mud_server.db.database.init_database"):
        with patch("mud_server.db.database.player_exists", return_value=False):
            with patch.dict(
                "os.environ", {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": "short"}
            ):
                args = argparse.Namespace()
                result = cli.cmd_create_superuser(args)

                assert result == 1


@pytest.mark.unit
def test_cmd_create_superuser_no_env_not_interactive():
    """Test create-superuser fails when no env vars and not interactive."""
    with patch("mud_server.db.database.init_database"):
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdin.isatty", return_value=False):
                args = argparse.Namespace()
                result = cli.cmd_create_superuser(args)

                assert result == 1


@pytest.mark.unit
def test_cmd_create_superuser_interactive(monkeypatch):
    """Test create-superuser prompts interactively when no env vars."""
    with patch("mud_server.db.database.init_database"):
        with patch("mud_server.db.database.player_exists", return_value=False):
            with patch("mud_server.db.database.create_player_with_password", return_value=True):
                with patch.dict("os.environ", {}, clear=True):
                    with patch("sys.stdin.isatty", return_value=True):
                        # Mock the prompt function with a valid password
                        with patch(
                            "mud_server.cli.prompt_for_credentials",
                            return_value=("interactiveuser", TEST_PASSWORD),
                        ):
                            args = argparse.Namespace()
                            result = cli.cmd_create_superuser(args)

                            assert result == 0


# ============================================================================
# MAIN ENTRY POINT TESTS
# ============================================================================


@pytest.mark.unit
def test_main_no_command(capsys):
    """Test main with no command shows help."""
    with patch("sys.argv", ["mud-server"]):
        result = cli.main()
        assert result == 0


@pytest.mark.unit
def test_main_init_db():
    """Test main routes to init-db command."""
    with patch("sys.argv", ["mud-server", "init-db"]):
        with patch("mud_server.db.database.init_database"):
            result = cli.main()
            assert result == 0


@pytest.mark.unit
def test_main_create_superuser():
    """Test main routes to create-superuser command."""
    with patch("sys.argv", ["mud-server", "create-superuser"]):
        with patch("mud_server.db.database.init_database"):
            with patch("mud_server.db.database.player_exists", return_value=False):
                with patch("mud_server.db.database.create_player_with_password", return_value=True):
                    with patch.dict(
                        "os.environ",
                        {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": TEST_PASSWORD},
                    ):
                        result = cli.main()
                        assert result == 0
