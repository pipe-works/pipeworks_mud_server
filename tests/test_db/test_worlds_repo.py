"""Focused tests for ``mud_server.db.worlds_repo``."""

from __future__ import annotations

from mud_server.db import database, worlds_repo


def _seed_world(cursor, world_id: str, *, is_active: int = 1) -> None:
    """Insert or replace a world row for repository-level tests."""
    cursor.execute(
        """
        INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
        VALUES (?, ?, '', ?, '{}')
        """,
        (world_id, world_id, is_active),
    )


def test_list_worlds_for_user_via_repo(db_with_users):
    """World repo should expose the same access decoration contract as the facade."""
    player_id = database.get_user_id("testplayer")
    assert player_id is not None

    conn = database.get_connection()
    cursor = conn.cursor()
    _seed_world(cursor, "invite_only_world", is_active=1)
    conn.commit()
    conn.close()

    rows = worlds_repo.list_worlds_for_user(
        player_id,
        role="player",
        include_invite_worlds=True,
    )
    by_id = {row["id"]: row for row in rows}
    assert "invite_only_world" in by_id
    assert by_id["invite_only_world"]["can_access"] is False
    assert by_id["invite_only_world"]["is_locked"] is True


def test_get_world_admin_rows_via_repo(db_with_users):
    """World repo admin rows should report online state from in-world sessions."""
    player_id = database.get_user_id("testplayer")
    assert player_id is not None
    player_char = database.get_user_characters(player_id)[0]
    assert database.create_session(
        player_id,
        "repo-world-session",
        character_id=int(player_char["id"]),
        world_id="pipeworks_web",
    )

    rows = worlds_repo.get_world_admin_rows()
    by_id = {row["world_id"]: row for row in rows}
    pipeworks = by_id["pipeworks_web"]
    assert pipeworks["is_online"] is True
    assert any(
        entry["session_id"] == "repo-world-session" for entry in pipeworks["active_characters"]
    )
