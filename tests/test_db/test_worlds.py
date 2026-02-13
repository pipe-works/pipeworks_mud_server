"""
Tests for world catalog and permission queries.
"""

import pytest

from mud_server.db import database


def _seed_world(cursor, world_id: str, *, is_active: int = 1) -> None:
    cursor.execute(
        """
        INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
        VALUES (?, ?, '', ?, '{}')
        """,
        (world_id, world_id, is_active),
    )


@pytest.mark.unit
@pytest.mark.db
def test_list_worlds_filters_active(test_db):
    """list_worlds should filter inactive worlds by default."""
    conn = database.get_connection()
    cursor = conn.cursor()
    _seed_world(cursor, "daily_undertaking", is_active=1)
    _seed_world(cursor, "pipeworks_web", is_active=0)
    conn.commit()
    conn.close()

    active = database.list_worlds()
    assert [world["id"] for world in active] == ["daily_undertaking"]

    all_worlds = database.list_worlds(include_inactive=True)
    assert {world["id"] for world in all_worlds} == {"daily_undertaking", "pipeworks_web"}


@pytest.mark.unit
@pytest.mark.db
def test_list_worlds_for_user_permissions(db_with_users):
    """Non-admin users only see worlds granted in world_permissions."""
    testplayer_id = database.get_user_id("testplayer")
    assert testplayer_id is not None

    conn = database.get_connection()
    cursor = conn.cursor()
    _seed_world(cursor, "daily_undertaking", is_active=1)
    _seed_world(cursor, "pipeworks_web", is_active=1)
    cursor.execute(
        """
        INSERT INTO world_permissions (user_id, world_id, can_access)
        VALUES (?, ?, 1)
        """,
        (testplayer_id, "daily_undertaking"),
    )
    conn.commit()
    conn.close()

    worlds = database.list_worlds_for_user(testplayer_id, role="player")
    assert [world["id"] for world in worlds] == ["daily_undertaking"]


@pytest.mark.unit
@pytest.mark.db
def test_list_worlds_for_admin_roles(db_with_users):
    """Admins and superusers should see all worlds without explicit grants."""
    admin_id = database.get_user_id("testadmin")
    superuser_id = database.get_user_id("testsuperuser")
    assert admin_id is not None
    assert superuser_id is not None

    conn = database.get_connection()
    cursor = conn.cursor()
    _seed_world(cursor, "daily_undertaking", is_active=1)
    _seed_world(cursor, "pipeworks_web", is_active=1)
    conn.commit()
    conn.close()

    admin_worlds = database.list_worlds_for_user(admin_id, role="admin")
    super_worlds = database.list_worlds_for_user(superuser_id, role="superuser")

    assert {world["id"] for world in admin_worlds} == {"daily_undertaking", "pipeworks_web"}
    assert {world["id"] for world in super_worlds} == {"daily_undertaking", "pipeworks_web"}
