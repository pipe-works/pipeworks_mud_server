"""Focused tests for ``mud_server.db.admin_repo``."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mud_server.db import admin_repo, database
from mud_server.db import connection as db_connection
from mud_server.db.errors import DatabaseReadError


def test_list_tables_returns_core_tables(test_db):
    """Admin repo should expose discoverable table metadata."""
    tables = admin_repo.list_tables()
    table_names = {row["name"] for row in tables}
    assert "users" in table_names
    assert "characters" in table_names
    assert "sessions" in table_names


def test_get_table_rows_invalid_table_raises(test_db):
    """Unknown table names should fail fast with a value error."""
    with pytest.raises(ValueError):
        admin_repo.get_table_rows("does_not_exist")


def test_get_all_users_detailed_reports_online_worlds(test_db, db_with_users):
    """Detailed users query should report online account and in-world flags."""
    testplayer_id = database.get_user_id("testplayer")
    assert testplayer_id is not None
    testplayer_character = database.get_user_characters(
        testplayer_id, world_id=database.DEFAULT_WORLD_ID
    )[0]

    assert database.create_session(
        testplayer_id,
        "admin-repo-detailed-session",
        character_id=int(testplayer_character["id"]),
        world_id="pipeworks_web",
    )

    users = admin_repo.get_all_users_detailed()
    by_username = {row["username"]: row for row in users}
    player_row = by_username["testplayer"]

    assert player_row["is_online_account"] is True
    assert player_row["is_online_in_world"] is True
    assert "pipeworks_web" in player_row["online_world_ids"]


def test_get_active_connections_world_filter(test_db, db_with_users):
    """Active connections should support world-scoped filtering."""
    testplayer_id = database.get_user_id("testplayer")
    assert testplayer_id is not None
    testplayer_character = database.get_user_characters(
        testplayer_id, world_id=database.DEFAULT_WORLD_ID
    )[0]

    assert database.create_character_for_user(
        testplayer_id,
        "admin_repo_alt_world",
        world_id="daily_undertaking",
    )
    alt_character = database.get_character_by_name("admin_repo_alt_world")
    assert alt_character is not None

    assert database.create_session(
        testplayer_id,
        "admin-repo-pipeworks-session",
        character_id=int(testplayer_character["id"]),
        world_id="pipeworks_web",
    )
    assert database.create_session(
        testplayer_id,
        "admin-repo-daily-session",
        character_id=int(alt_character["id"]),
        world_id="daily_undertaking",
    )

    pipeworks_rows = admin_repo.get_active_connections(world_id="pipeworks_web")
    daily_rows = admin_repo.get_active_connections(world_id="daily_undertaking")

    assert any(row["session_id"] == "admin-repo-pipeworks-session" for row in pipeworks_rows)
    assert all(row["world_id"] == "pipeworks_web" for row in pipeworks_rows)

    assert any(row["session_id"] == "admin-repo-daily-session" for row in daily_rows)
    assert all(row["world_id"] == "daily_undertaking" for row in daily_rows)


def test_admin_repo_read_paths_raise_typed_errors_on_connection_failure():
    """Admin read helpers should map infrastructure failures to read errors."""
    with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
        with pytest.raises(DatabaseReadError):
            admin_repo.get_table_names()
        with pytest.raises(DatabaseReadError):
            admin_repo.list_tables()
        with pytest.raises(DatabaseReadError):
            admin_repo.get_schema_map()
        with pytest.raises(DatabaseReadError):
            admin_repo.get_table_rows("users")
        with pytest.raises(DatabaseReadError):
            admin_repo.get_all_users_detailed()
        with pytest.raises(DatabaseReadError):
            admin_repo.get_all_users()
        with pytest.raises(DatabaseReadError):
            admin_repo.get_character_locations()
        with pytest.raises(DatabaseReadError):
            admin_repo.get_all_sessions()
        with pytest.raises(DatabaseReadError):
            admin_repo.get_active_connections()
        with pytest.raises(DatabaseReadError):
            admin_repo.get_all_chat_messages()
