"""Focused tests for ``mud_server.db.users_repo``."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import connection as db_connection
from mud_server.db import users_repo
from mud_server.db.errors import DatabaseReadError, DatabaseWriteError


def test_users_repo_read_paths_raise_typed_errors_on_connection_failure():
    """User read helpers should map infra failures to typed read errors."""
    with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
        with pytest.raises(DatabaseReadError):
            users_repo.user_exists("player")
        with pytest.raises(DatabaseReadError):
            users_repo.get_user_id("player")
        with pytest.raises(DatabaseReadError):
            users_repo.get_username_by_id(1)
        with pytest.raises(DatabaseReadError):
            users_repo.get_user_role("player")
        with pytest.raises(DatabaseReadError):
            users_repo.get_user_account_origin("player")
        with pytest.raises(DatabaseReadError):
            users_repo.verify_password_for_user("player", "password")
        with pytest.raises(DatabaseReadError):
            users_repo.is_user_active("player")


def test_users_repo_write_paths_raise_typed_errors_on_connection_failure():
    """User write helpers should map infra failures to typed write errors."""
    with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
        with pytest.raises(DatabaseWriteError):
            users_repo.create_user_with_password("player", "SecureTest#123")
        with pytest.raises(DatabaseWriteError):
            users_repo.set_user_role("player", "admin")
        with pytest.raises(DatabaseWriteError):
            users_repo.deactivate_user("player")
        with pytest.raises(DatabaseWriteError):
            users_repo.activate_user("player")
        with pytest.raises(DatabaseWriteError):
            users_repo.change_password_for_user("player", "SecureTest#123")
        with pytest.raises(DatabaseWriteError):
            users_repo.tombstone_user(1)
        with pytest.raises(DatabaseWriteError):
            users_repo.unlink_characters_for_user(1)
        with pytest.raises(DatabaseWriteError):
            users_repo.cleanup_expired_guest_accounts()


def test_create_user_with_password_returns_false_on_integrity_error():
    """Uniqueness collisions should remain a domain-level False contract."""
    with patch.object(
        db_connection, "get_connection", side_effect=sqlite3.IntegrityError("duplicate")
    ):
        assert users_repo.create_user_with_password("duplicate_user", "SecureTest#123") is False


def test_delete_user_contracts_for_missing_and_write_failure(test_db, temp_db_path):
    """Delete-user should return False for missing users and raise on infra errors."""
    with use_test_database(temp_db_path):
        assert users_repo.delete_user("missing-user") is False

    with patch.object(users_repo, "get_user_id", return_value=1):
        with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
            with pytest.raises(DatabaseWriteError):
                users_repo.delete_user("existing-user")
