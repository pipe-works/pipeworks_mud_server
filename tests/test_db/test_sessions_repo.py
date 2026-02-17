"""Focused tests for ``mud_server.db.sessions_repo``."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import connection as db_connection
from mud_server.db import database, sessions_repo
from mud_server.db.errors import (
    DatabaseOperationContext,
    DatabaseReadError,
    DatabaseWriteError,
)


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


def test_sessions_repo_handles_expected_false_contracts_without_db_errors(
    test_db, temp_db_path, db_with_users
):
    """Repository should return False for non-error domain outcomes."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None

        assert sessions_repo.create_session("missing-user", "session-x") is False
        assert (
            sessions_repo.create_session(user_id, "session-y", character_id=999999, world_id=None)
            is False
        )
        assert (
            sessions_repo.set_session_character("missing-session", 1, world_id="pipeworks_web")
            is False
        )
        assert sessions_repo.update_session_activity("missing-session") is False
        assert sessions_repo.remove_sessions_for_user(999999) is False
        assert sessions_repo.remove_session_by_id("missing-session") is False
        assert sessions_repo.remove_sessions_for_character_count(999999) == 0
        assert sessions_repo.remove_sessions_for_character(999999) is False


def test_sessions_repo_internal_error_helpers_re_raise_database_errors():
    """Internal helper guards should preserve pre-typed DatabaseError instances."""
    read_exc = DatabaseReadError(context=DatabaseOperationContext(operation="sessions.read"))
    with pytest.raises(DatabaseReadError) as read_info:
        sessions_repo._raise_read_error("sessions.read", read_exc)
    assert read_info.value is read_exc

    write_exc = DatabaseWriteError(context=DatabaseOperationContext(operation="sessions.write"))
    with pytest.raises(DatabaseWriteError) as write_info:
        sessions_repo._raise_write_error("sessions.write", write_exc)
    assert write_info.value is write_exc
