"""Focused tests for ``mud_server.db.sessions_repo``."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mud_server.db import connection as db_connection
from mud_server.db import sessions_repo
from mud_server.db.errors import DatabaseReadError, DatabaseWriteError


def test_sessions_repo_write_paths_raise_typed_errors_on_connection_failure():
    """Session mutation helpers should raise typed write errors on DB failures."""
    with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
        with pytest.raises(DatabaseWriteError):
            sessions_repo.create_session(1, "session-x")

        with pytest.raises(DatabaseWriteError):
            sessions_repo.set_session_character("session-x", 1, world_id="pipeworks_web")

        with pytest.raises(DatabaseWriteError):
            sessions_repo.remove_session_by_id("session-x")


def test_sessions_repo_read_paths_raise_typed_errors_on_connection_failure():
    """Session query helpers should raise typed read errors on DB failures."""
    with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
        with pytest.raises(DatabaseReadError):
            sessions_repo.get_session_by_id("session-x")

        with pytest.raises(DatabaseReadError):
            sessions_repo.get_active_characters(world_id="pipeworks_web")
