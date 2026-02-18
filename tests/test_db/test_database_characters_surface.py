"""Compatibility-surface tests for character helpers exposed via ``db.database``.

These tests keep contract coverage for character-facing wrappers while
decomposing the historical monolithic DB compatibility test module.
"""

from typing import Any, cast
from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import connection as db_connection
from mud_server.db import database
from mud_server.db.errors import DatabaseWriteError
from tests.constants import TEST_PASSWORD


@pytest.mark.unit
@pytest.mark.db
def test_create_character_for_user_success(test_db, temp_db_path):
    """Creating a character should succeed and seed default room state."""
    with use_test_database(temp_db_path):
        database.create_user_with_password("charuser", TEST_PASSWORD)
        user_id = database.get_user_id("charuser")
        assert user_id is not None

        result = database.create_character_for_user(
            user_id, "charuser_alt", world_id=database.DEFAULT_WORLD_ID
        )
        assert result is True
        assert database.get_character_by_name("charuser_alt") is not None
        assert (
            database.get_character_room("charuser_alt", world_id=database.DEFAULT_WORLD_ID)
            == "spawn"
        )


@pytest.mark.unit
@pytest.mark.db
def test_create_character_for_user_requires_explicit_world_id():
    """Character creation should fail fast when world scope is omitted."""
    create_character_for_user = cast(Any, database.create_character_for_user)
    with pytest.raises(TypeError, match="missing 1 required keyword-only argument: 'world_id'"):
        create_character_for_user(1, "missing_world")


@pytest.mark.unit
@pytest.mark.db
def test_get_character_by_name_missing_returns_none(test_db, temp_db_path):
    """Character lookup by name should return ``None`` for unknown names."""
    with use_test_database(temp_db_path):
        assert database.get_character_by_name("nope") is None


@pytest.mark.unit
@pytest.mark.db
def test_get_character_by_id_missing_returns_none(test_db, temp_db_path):
    """Character lookup by id should return ``None`` for unknown ids."""
    with use_test_database(temp_db_path):
        assert database.get_character_by_id(9999) is None


@pytest.mark.unit
@pytest.mark.db
def test_get_user_characters_requires_explicit_world_id():
    """Character listing should fail fast when world scope is omitted."""
    get_user_characters = cast(Any, database.get_user_characters)
    with pytest.raises(TypeError, match="missing 1 required keyword-only argument: 'world_id'"):
        get_user_characters(1)


@pytest.mark.unit
@pytest.mark.db
def test_tombstone_character_success_detaches_owner_and_renames(test_db, temp_db_path):
    """Tombstoning should detach ownership while preserving row history."""
    with use_test_database(temp_db_path):
        database.create_user_with_password("stone_user", TEST_PASSWORD)
        user_id = database.get_user_id("stone_user")
        assert user_id is not None
        assert (
            database.create_character_for_user(user_id, "Stone Name", world_id="pipeworks_web")
            is True
        )

        character = database.get_character_by_name("Stone Name")
        assert character is not None
        character_id = int(character["id"])

        assert database.tombstone_character(character_id) is True

        tombstoned = database.get_character_by_id(character_id)
        assert tombstoned is not None
        assert tombstoned["user_id"] is None
        assert tombstoned["name"].startswith(f"tombstone_{character_id}_")

        # Original name becomes available after tombstoning.
        assert (
            database.create_character_for_user(user_id, "Stone Name", world_id="pipeworks_web")
            is True
        )


@pytest.mark.unit
@pytest.mark.db
def test_tombstone_character_missing_returns_false(test_db, temp_db_path):
    """Tombstone helper should return False for unknown ids."""
    with use_test_database(temp_db_path):
        assert database.tombstone_character(123456) is False


@pytest.mark.unit
@pytest.mark.db
def test_delete_character_success_and_missing(test_db, temp_db_path):
    """Delete helper should remove existing rows and report missing rows."""
    with use_test_database(temp_db_path):
        database.create_user_with_password("delete_user", TEST_PASSWORD)
        user_id = database.get_user_id("delete_user")
        assert user_id is not None
        assert (
            database.create_character_for_user(user_id, "Delete Me", world_id="pipeworks_web")
            is True
        )

        character = database.get_character_by_name("Delete Me")
        assert character is not None
        character_id = int(character["id"])

        assert database.delete_character(character_id) is True
        assert database.get_character_by_id(character_id) is None
        assert database.delete_character(character_id) is False


@pytest.mark.unit
@pytest.mark.db
def test_unlink_characters_for_user(test_db, temp_db_path):
    """Unlink helper should clear ``user_id`` ownership for all account characters."""
    with use_test_database(temp_db_path):
        database.create_user_with_password("unlinker", TEST_PASSWORD)
        user_id = database.get_user_id("unlinker")
        assert user_id is not None
        assert database.create_character_for_user(
            user_id, "unlinker_char", world_id=database.DEFAULT_WORLD_ID
        )

        database.unlink_characters_for_user(user_id)

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM characters WHERE name = ?", ("unlinker_char",))
        user_id_row = cursor.fetchone()
        conn.close()

        assert user_id_row[0] is None


@pytest.mark.unit
@pytest.mark.db
def test_set_character_room_missing_character_returns_false(test_db, temp_db_path):
    """Room updates should return False for unknown characters."""
    with use_test_database(temp_db_path):
        assert (
            database.set_character_room("missing", "spawn", world_id=database.DEFAULT_WORLD_ID)
            is False
        )


@pytest.mark.unit
@pytest.mark.db
def test_get_player_locations_shim(test_db, temp_db_path, db_with_users):
    """Compatibility shim should return structured character location rows."""
    with use_test_database(temp_db_path):
        locations = database.get_character_locations()
        assert isinstance(locations, list)


@pytest.mark.unit
@pytest.mark.db
def test_world_scoped_character_slot_limit_enforced(temp_db_path):
    """Per-world slot limits should cap each world independently per account."""
    from mud_server.config import config

    original_default_slot_limit = config.character_creation.default_world_slot_limit
    original_world_overrides = dict(config.character_creation.world_policy_overrides)
    config.character_creation.default_world_slot_limit = 1
    config.character_creation.world_policy_overrides = {}
    try:
        with use_test_database(temp_db_path):
            database.init_database(skip_superuser=True)
            database.create_user_with_password("limit_user", TEST_PASSWORD)
            user_id = database.get_user_id("limit_user")
            assert user_id is not None

            # Seed a secondary world so we can prove limits are world-scoped.
            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
                VALUES (?, ?, '', 1, '{}')
                """,
                ("daily_undertaking", "daily_undertaking"),
            )
            conn.commit()
            conn.close()

            assert (
                database.create_character_for_user(
                    user_id, "pipeworks_slot_1", world_id=database.DEFAULT_WORLD_ID
                )
                is True
            )
            assert (
                database.create_character_for_user(
                    user_id, "pipeworks_slot_2", world_id=database.DEFAULT_WORLD_ID
                )
                is False
            )

            assert (
                database.create_character_for_user(
                    user_id,
                    "daily_slot_1",
                    world_id="daily_undertaking",
                )
                is True
            )
            assert (
                database.create_character_for_user(
                    user_id,
                    "daily_slot_2",
                    world_id="daily_undertaking",
                )
                is False
            )
    finally:
        config.character_creation.default_world_slot_limit = original_default_slot_limit
        config.character_creation.world_policy_overrides = original_world_overrides


@pytest.mark.unit
@pytest.mark.db
def test_get_character_locations(test_db, temp_db_path, db_with_users):
    """Character location queries should return the room for each character row."""
    with use_test_database(temp_db_path):
        database.set_character_room("testplayer_char", "forest", world_id=database.DEFAULT_WORLD_ID)

        locations = database.get_character_locations()
        by_username = {loc["character_name"]: loc for loc in locations}

        assert "testplayer_char" in by_username
        assert by_username["testplayer_char"]["room_id"] == "forest"


@pytest.mark.unit
@pytest.mark.db
def test_get_player_room_default(test_db, temp_db_path, db_with_users):
    """Default room lookup should resolve to ``spawn`` for seeded characters."""
    with use_test_database(temp_db_path):
        assert (
            database.get_character_room("testplayer_char", world_id=database.DEFAULT_WORLD_ID)
            == "spawn"
        )


@pytest.mark.unit
@pytest.mark.db
def test_set_player_room(test_db, temp_db_path, db_with_users):
    """Room updates should persist for existing characters."""
    with use_test_database(temp_db_path):
        result = database.set_character_room(
            "testplayer_char", "forest", world_id=database.DEFAULT_WORLD_ID
        )
        assert result is True
        assert (
            database.get_character_room("testplayer_char", world_id=database.DEFAULT_WORLD_ID)
            == "forest"
        )


@pytest.mark.unit
@pytest.mark.db
def test_get_player_room_nonexistent(test_db, temp_db_path):
    """Room lookup should return ``None`` for unknown character names."""
    with use_test_database(temp_db_path):
        assert (
            database.get_character_room("nonexistent", world_id=database.DEFAULT_WORLD_ID) is None
        )


@pytest.mark.unit
@pytest.mark.db
def test_get_player_inventory_default(test_db, temp_db_path, db_with_users):
    """Seeded characters should start with empty inventory."""
    with use_test_database(temp_db_path):
        inventory = database.get_character_inventory(
            "testplayer_char", world_id=database.DEFAULT_WORLD_ID
        )
        assert inventory == []


@pytest.mark.unit
@pytest.mark.db
def test_set_player_inventory(test_db, temp_db_path, db_with_users):
    """Inventory updates should round-trip through persistence."""
    with use_test_database(temp_db_path):
        inventory = ["torch", "rope", "sword"]
        result = database.set_character_inventory(
            "testplayer_char", inventory, world_id=database.DEFAULT_WORLD_ID
        )
        assert result is True

        retrieved = database.get_character_inventory(
            "testplayer_char", world_id=database.DEFAULT_WORLD_ID
        )
        assert retrieved == inventory


@pytest.mark.unit
@pytest.mark.db
def test_get_player_inventory_nonexistent(test_db, temp_db_path):
    """Inventory lookup should return an empty list for unknown characters."""
    with use_test_database(temp_db_path):
        inventory = database.get_character_inventory(
            "nonexistent", world_id=database.DEFAULT_WORLD_ID
        )
        assert inventory == []


class _FakeCursor:
    """Minimal fake cursor for character write-failure compatibility tests."""

    def __init__(self, *, lastrowid=None, fetchone=None):
        self.lastrowid = lastrowid
        self._fetchone = fetchone
        self.rowcount = 0

    def execute(self, _sql, _params=None):  # noqa: D401 - minimal fake
        return None

    def fetchone(self):
        return self._fetchone


class _FakeConnection:
    """Minimal fake connection wrapper exposing a controlled fake cursor."""

    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def execute(self, sql, params=None):
        """Mirror sqlite3.Connection.execute for compatibility fakes."""
        return self._cursor.execute(sql, params)

    def commit(self):
        return None

    def close(self):
        return None


@pytest.mark.unit
@pytest.mark.db
def test_create_character_for_user_missing_lastrowid_raises():
    """Character creation should map low-level write failures to typed DB errors."""
    fake_cursor = _FakeCursor(lastrowid=None)
    fake_conn = _FakeConnection(fake_cursor)

    with patch.object(db_connection, "get_connection", return_value=fake_conn):
        with pytest.raises(DatabaseWriteError):
            database.create_character_for_user(1, "badchar", world_id=database.DEFAULT_WORLD_ID)


@pytest.mark.unit
@pytest.mark.db
def test_create_default_character_missing_lastrowid_raises():
    """Default character helper should reject missing insert metadata."""
    fake_cursor = _FakeCursor(lastrowid=None)

    with pytest.raises(ValueError):
        database._create_default_character(
            fake_cursor,
            1,
            "badchar",
            world_id=database.DEFAULT_WORLD_ID,
        )
