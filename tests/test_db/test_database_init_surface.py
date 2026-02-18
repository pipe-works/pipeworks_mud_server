"""Compatibility-surface tests for DB initialization helpers via ``db.database``."""

from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD


@pytest.mark.unit
@pytest.mark.db
def test_init_database_creates_tables(temp_db_path):
    """Test that init_database creates all required tables."""
    with use_test_database(temp_db_path):
        database.init_database()

        conn = database.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event'")
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='event_entity_axis_delta'"
        )
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='event_metadata'"
        )
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='characters'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='axis'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='axis_value'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_type'")
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='character_axis_score'"
        )
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='character_locations'"
        )
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='worlds'")
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='world_permissions'"
        )
        assert cursor.fetchone() is not None

        conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_init_database_creates_superuser_from_env_vars(temp_db_path):
    """Test that init_database creates superuser from environment variables."""
    with use_test_database(temp_db_path):
        with patch.dict(
            "os.environ", {"MUD_ADMIN_USER": "envadmin", "MUD_ADMIN_PASSWORD": "securepass123"}
        ):
            database.init_database()

            assert database.user_exists("envadmin")
            assert database.get_user_role("envadmin") == "superuser"
            assert database.verify_password_for_user("envadmin", "securepass123")
            assert database.get_character_by_name("envadmin_char") is None


@pytest.mark.unit
@pytest.mark.db
def test_init_database_no_superuser_without_env_vars(temp_db_path):
    """Test that init_database does NOT create superuser without environment variables."""
    with use_test_database(temp_db_path):
        with patch.dict("os.environ", {}, clear=True):
            database.init_database()

            assert not database.user_exists("admin")

            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            assert cursor.fetchone() is not None
            conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_init_database_skips_short_password(temp_db_path, capsys):
    """Test that init_database skips superuser creation if password is too short."""
    with use_test_database(temp_db_path):
        with patch.dict("os.environ", {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": "short"}):
            database.init_database()

            assert not database.user_exists("admin")

            captured = capsys.readouterr()
            assert "must be at least 8 characters" in captured.out


class _FakeCursor:
    """Minimal fake cursor used by bootstrap regression coverage."""

    def __init__(self, *, lastrowid=None, fetchone=None):
        self.lastrowid = lastrowid
        self._fetchone = fetchone
        self.rowcount = 0

    def execute(self, _sql, _params=None):  # noqa: D401 - minimal fake
        return None

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return []


class _FakeConnection:
    """Minimal fake connection wrapper for bootstrap regression test."""

    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def execute(self, sql, params=None):
        """Mirror sqlite3.Connection.execute for schema bootstrap fakes."""
        return self._cursor.execute(sql, params)

    def commit(self):
        return None

    def close(self):
        return None


@pytest.mark.unit
@pytest.mark.db
def test_init_database_superuser_bootstrap_does_not_require_character_lastrowid(monkeypatch):
    """Superuser bootstrap should not depend on character-row creation metadata."""

    class _InitCursor(_FakeCursor):
        def __init__(self):
            super().__init__(lastrowid=None, fetchone=(0,))

        def execute(self, _sql, _params=None):
            return None

    fake_conn = _FakeConnection(_InitCursor())

    with (
        patch.dict("os.environ", {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": TEST_PASSWORD}),
        patch("mud_server.db.connection.sqlite3.connect", return_value=fake_conn),
    ):
        database.init_database(skip_superuser=False)
