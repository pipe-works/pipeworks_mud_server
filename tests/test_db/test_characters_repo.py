"""Focused tests for ``mud_server.db.characters_repo``."""

from __future__ import annotations

from mud_server.db import characters_repo, database


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
