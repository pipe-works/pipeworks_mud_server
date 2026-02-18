"""Focused tests for ``mud_server.db.worlds_repo``."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mud_server.config import WorldCharacterPolicy, config
from mud_server.db import connection as db_connection
from mud_server.db import database, worlds_repo
from mud_server.db.errors import DatabaseReadError


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


def test_list_worlds_for_user_resolves_role_from_user_repo(db_with_users):
    """World listing should resolve role when caller omits explicit role."""
    player_id = database.get_user_id("testplayer")
    assert player_id is not None

    rows = worlds_repo.list_worlds_for_user(
        player_id,
        include_invite_worlds=True,
    )

    assert rows
    assert any(row["id"] == database.DEFAULT_WORLD_ID for row in rows)


def test_get_world_admin_rows_via_repo(db_with_users):
    """World repo admin rows should report online state from in-world sessions."""
    player_id = database.get_user_id("testplayer")
    assert player_id is not None
    player_char = database.get_user_characters(player_id, world_id=database.DEFAULT_WORLD_ID)[0]
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


def test_world_access_decision_branches_via_repo(db_with_users, monkeypatch):
    """World access helper should return expected typed decisions across branches."""
    player_id = database.get_user_id("testplayer")
    assert player_id is not None

    def _policy(_world_id: str) -> WorldCharacterPolicy:
        return WorldCharacterPolicy(
            creation_mode="invite",
            naming_mode="generated",
            slot_limit_per_account=1,
        )

    monkeypatch.setattr(config, "resolve_world_character_policy", _policy)

    conn = database.get_connection()
    cursor = conn.cursor()

    # inactive branch
    monkeypatch.setattr(worlds_repo, "_count_user_characters_in_world", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(worlds_repo, "_user_has_world_permission", lambda *_args, **_kwargs: False)
    inactive_decision = worlds_repo._resolve_world_access_for_row(  # noqa: SLF001 - branch test
        cursor,
        user_id=player_id,
        role="player",
        world_row=("inactive_world", "Inactive", "", 0, "{}", None),
    )
    assert inactive_decision.reason == "world_inactive"
    assert inactive_decision.can_access is False

    # invite-required branch
    invite_decision = worlds_repo._resolve_world_access_for_row(  # noqa: SLF001 - branch test
        cursor,
        user_id=player_id,
        role="player",
        world_row=("invite_world", "Invite", "", 1, "{}", None),
    )
    assert invite_decision.reason == "invite_required"
    assert invite_decision.can_access is False

    # slot-limit branch
    monkeypatch.setattr(worlds_repo, "_count_user_characters_in_world", lambda *_args, **_kwargs: 1)
    slot_decision = worlds_repo._resolve_world_access_for_row(  # noqa: SLF001 - branch test
        cursor,
        user_id=player_id,
        role="player",
        world_row=("slot_world", "Slot", "", 1, "{}", None),
    )
    assert slot_decision.reason == "slot_limit_reached"
    assert slot_decision.can_access is True
    assert slot_decision.can_create is False

    # ok branch
    monkeypatch.setattr(worlds_repo, "_count_user_characters_in_world", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(worlds_repo, "_user_has_world_permission", lambda *_args, **_kwargs: True)
    ok_decision = worlds_repo._resolve_world_access_for_row(  # noqa: SLF001 - branch test
        cursor,
        user_id=player_id,
        role="player",
        world_row=("ok_world", "OK", "", 1, "{}", None),
    )
    assert ok_decision.reason == "ok"
    assert ok_decision.can_access is True
    assert ok_decision.can_create is True

    conn.close()


def test_get_world_access_decision_world_not_found_returns_typed_row(db_with_users, monkeypatch):
    """Missing worlds should return a typed `world_not_found` decision."""
    player_id = database.get_user_id("testplayer")
    assert player_id is not None

    monkeypatch.setattr(
        config,
        "resolve_world_character_policy",
        lambda _world_id: WorldCharacterPolicy(
            creation_mode="invite",
            naming_mode="generated",
            slot_limit_per_account=10,
        ),
    )

    decision = worlds_repo.get_world_access_decision(
        player_id,
        "missing_world_for_repo_test",
        role="player",
    )
    assert decision.reason == "world_not_found"
    assert decision.can_access is False
    assert decision.can_create is False


def test_worlds_repo_read_paths_raise_typed_errors_on_connection_failure():
    """World read helpers should map infrastructure failures to read errors."""
    with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
        with pytest.raises(DatabaseReadError):
            worlds_repo.get_world_by_id(database.DEFAULT_WORLD_ID)
        with pytest.raises(DatabaseReadError):
            worlds_repo.list_worlds()
        with pytest.raises(DatabaseReadError):
            worlds_repo.get_world_access_decision(1, database.DEFAULT_WORLD_ID, role="player")
        with pytest.raises(DatabaseReadError):
            worlds_repo.get_user_character_count_for_world(1, database.DEFAULT_WORLD_ID)
        with pytest.raises(DatabaseReadError):
            worlds_repo.get_world_admin_rows()
        with pytest.raises(DatabaseReadError):
            worlds_repo.list_worlds_for_user(1, role="player")
