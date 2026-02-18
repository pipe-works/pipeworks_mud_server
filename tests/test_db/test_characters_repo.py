"""Focused tests for ``mud_server.db.characters_repo``."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from mud_server.db import characters_repo, database
from mud_server.db import connection as db_connection
from mud_server.db.errors import (
    DatabaseOperationContext,
    DatabaseReadError,
    DatabaseWriteError,
)


def test_create_character_for_user_round_trip(test_db, temp_db_path):
    """Character repo should create and then read back a character row."""
    created_user = database.create_user_with_password("repo_user", "SecureTest#123")
    assert created_user is True
    user_id = database.get_user_id("repo_user")
    assert user_id is not None

    created_character = characters_repo.create_character_for_user(
        user_id,
        "repo_character",
        world_id="pipeworks_web",
    )
    assert created_character is True

    character = characters_repo.get_character_by_name("repo_character")
    assert character is not None
    assert character["user_id"] == user_id
    assert character["world_id"] == "pipeworks_web"
    assert characters_repo.get_character_room("repo_character", world_id="pipeworks_web") == "spawn"


def test_create_default_character_seeds_axis_and_snapshot_via_axis_repo(test_db):
    """Default-character helper should seed axis/snapshot rows through axis_repo."""
    created_user = database.create_user_with_password("default_repo_user", "SecureTest#123")
    assert created_user is True
    user_id = database.get_user_id("default_repo_user")
    assert user_id is not None

    conn = database.get_connection()
    cursor = conn.cursor()
    character_id = (
        characters_repo._create_default_character(  # noqa: SLF001 - intentional helper test
            cursor,
            user_id,
            "default_repo_user",
            world_id=database.DEFAULT_WORLD_ID,
        )
    )
    conn.commit()

    cursor.execute(
        """
        SELECT current_state_json
        FROM characters
        WHERE id = ?
        """,
        (character_id,),
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] is not None


def test_resolve_character_name_requires_character_identity(test_db, temp_db_path, db_with_users):
    """Resolution should require explicit character names (no username fallback)."""
    resolved = characters_repo.resolve_character_name(
        "testplayer", world_id=database.DEFAULT_WORLD_ID
    )
    assert resolved is None
    assert (
        characters_repo.resolve_character_name(
            "testplayer_char", world_id=database.DEFAULT_WORLD_ID
        )
        == "testplayer_char"
    )


def test_set_and_get_character_inventory(test_db, temp_db_path, db_with_users):
    """Inventory updates should be persisted through the repo module."""
    updated = characters_repo.set_character_inventory(
        "testplayer_char",
        ["torch", "rope"],
        world_id=database.DEFAULT_WORLD_ID,
    )
    assert updated is True
    assert characters_repo.get_character_inventory(
        "testplayer_char",
        world_id=database.DEFAULT_WORLD_ID,
    ) == ["torch", "rope"]


def test_tombstone_character_unlinks_owner_and_renames(test_db, temp_db_path):
    """Tombstoning should detach ownership and free up the original name."""
    assert database.create_user_with_password("stone_owner", "SecureTest#123") is True
    user_id = database.get_user_id("stone_owner")
    assert user_id is not None
    assert (
        characters_repo.create_character_for_user(user_id, "stone_name", world_id="pipeworks_web")
        is True
    )
    character = characters_repo.get_character_by_name("stone_name")
    assert character is not None

    tombstoned = characters_repo.tombstone_character(int(character["id"]))
    assert tombstoned is True

    updated = characters_repo.get_character_by_id(int(character["id"]))
    assert updated is not None
    assert updated["user_id"] is None
    assert str(updated["name"]).startswith("tombstone_")


def test_characters_repo_raises_typed_errors_on_connection_failure():
    """Connection failures should surface as typed character repository errors."""
    with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
        with pytest.raises(DatabaseWriteError):
            characters_repo.set_character_room("testplayer_char", "spawn", world_id="pipeworks_web")

        with pytest.raises(DatabaseReadError):
            characters_repo.get_character_room("testplayer_char", world_id="pipeworks_web")


def test_characters_repo_raises_typed_errors_for_all_key_paths():
    """Core read/write helpers should map connection errors to typed DB exceptions."""
    with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
        with pytest.raises(DatabaseReadError):
            characters_repo.resolve_character_name("testplayer_char", world_id="pipeworks_web")
        with pytest.raises(DatabaseWriteError):
            characters_repo.create_character_for_user(1, "broken", world_id="pipeworks_web")
        with pytest.raises(DatabaseReadError):
            characters_repo.character_exists("testplayer_char")
        with pytest.raises(DatabaseReadError):
            characters_repo.get_character_by_name("testplayer_char")
        with pytest.raises(DatabaseReadError):
            characters_repo.get_character_by_id(1)
        with pytest.raises(DatabaseReadError):
            characters_repo.get_character_name_by_id(1)
        with pytest.raises(DatabaseReadError):
            characters_repo.get_user_characters(1, world_id="pipeworks_web")
        with pytest.raises(DatabaseWriteError):
            characters_repo.tombstone_character(1)
        with pytest.raises(DatabaseWriteError):
            characters_repo.delete_character(1)
        with pytest.raises(DatabaseReadError):
            characters_repo.get_characters_in_room("spawn", world_id="pipeworks_web")
        with pytest.raises(DatabaseReadError):
            characters_repo.get_character_inventory("testplayer_char", world_id="pipeworks_web")
        with pytest.raises(DatabaseWriteError):
            characters_repo.set_character_inventory("testplayer_char", [], world_id="pipeworks_web")


def test_create_character_for_user_returns_false_on_integrity_error():
    """Integrity collisions should remain a domain-level False return contract."""
    with patch.object(
        db_connection, "get_connection", side_effect=sqlite3.IntegrityError("duplicate")
    ):
        assert (
            characters_repo.create_character_for_user(1, "dupe", world_id="pipeworks_web") is False
        )


def test_characters_repo_internal_error_helpers_re_raise_database_errors():
    """Internal helper guards should preserve pre-typed DatabaseError instances."""
    read_exc = DatabaseReadError(context=DatabaseOperationContext(operation="characters.read"))
    with pytest.raises(DatabaseReadError) as read_info:
        characters_repo._raise_read_error("characters.read", read_exc)
    assert read_info.value is read_exc

    write_exc = DatabaseWriteError(context=DatabaseOperationContext(operation="characters.write"))
    with pytest.raises(DatabaseWriteError) as write_info:
        characters_repo._raise_write_error("characters.write", write_exc)
    assert write_info.value is write_exc
