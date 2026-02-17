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
    """Non-admin users see worlds they can access via grant/open/owned-character rules."""
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
    assert [world["id"] for world in worlds] == ["daily_undertaking", "pipeworks_web"]
    assert all(world["can_access"] is True for world in worlds)


@pytest.mark.unit
@pytest.mark.db
def test_list_worlds_for_user_include_invite_locked_preview(db_with_users):
    """Invite-locked worlds should still be visible when preview mode is enabled."""
    testplayer_id = database.get_user_id("testplayer")
    assert testplayer_id is not None

    conn = database.get_connection()
    cursor = conn.cursor()
    _seed_world(cursor, "invite_only_world", is_active=1)
    conn.commit()
    conn.close()

    worlds = database.list_worlds_for_user(
        testplayer_id,
        role="player",
        include_invite_worlds=True,
    )
    by_id = {row["id"]: row for row in worlds}
    assert "invite_only_world" in by_id
    assert by_id["invite_only_world"]["can_access"] is False
    assert by_id["invite_only_world"]["is_locked"] is True
    assert by_id["invite_only_world"]["access_mode"] == "invite"


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


@pytest.mark.unit
@pytest.mark.db
def test_get_world_admin_rows_reports_online_state_and_active_characters(db_with_users):
    """World admin rows should include live online state and kickable character rows."""
    admin_id = database.get_user_id("testadmin")
    assert admin_id is not None

    conn = database.get_connection()
    cursor = conn.cursor()
    _seed_world(cursor, "daily_undertaking", is_active=1)
    _seed_world(cursor, "offline_world", is_active=1)
    conn.commit()
    conn.close()

    testplayer_id = database.get_user_id("testplayer")
    assert testplayer_id is not None
    testplayer_characters = database.get_user_characters(
        testplayer_id, world_id=database.DEFAULT_WORLD_ID
    )
    assert testplayer_characters
    assert database.create_session("testplayer", "player-session")
    # World online state tracks in-world sessions only; bind the character.
    assert database.set_session_character(
        "player-session",
        int(testplayer_characters[0]["id"]),
        world_id=database.DEFAULT_WORLD_ID,
    )

    assert database.create_character_for_user(
        admin_id, "testadmin_daily", world_id="daily_undertaking"
    )
    daily_character = database.get_character_by_name("testadmin_daily")
    assert daily_character is not None
    assert database.create_session(
        admin_id,
        "admin-daily-session",
        character_id=int(daily_character["id"]),
        world_id="daily_undertaking",
    )

    rows = database.get_world_admin_rows()
    by_world = {row["world_id"]: row for row in rows}

    pipeworks = by_world["pipeworks_web"]
    assert pipeworks["is_online"] is True
    assert pipeworks["active_session_count"] >= 1
    assert pipeworks["active_character_count"] >= 1
    assert any(entry["session_id"] == "player-session" for entry in pipeworks["active_characters"])

    daily = by_world["daily_undertaking"]
    assert daily["is_online"] is True
    assert daily["active_session_count"] == 1
    assert daily["active_character_count"] == 1
    assert daily["active_characters"][0]["character_name"] == "testadmin_daily"

    offline = by_world["offline_world"]
    assert offline["is_online"] is False
    assert offline["active_session_count"] == 0
    assert offline["active_character_count"] == 0
    assert offline["active_characters"] == []
