"""Focused tests for ``mud_server.db.chat_repo``."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mud_server.db import chat_repo, database
from mud_server.db import connection as db_connection
from mud_server.db.connection import connection_scope
from mud_server.db.errors import DatabaseReadError, DatabaseWriteError


def _age_all_messages(hours: int) -> None:
    """Set all chat_messages timestamps to be older than the specified hours."""
    with connection_scope(write=True) as conn:
        conn.execute(
            "UPDATE chat_messages SET timestamp = datetime('now', ? || ' hours')",
            (f"-{hours}",),
        )


def test_add_chat_message_and_query_by_world(test_db, temp_db_path, db_with_users):
    """Room history queries should remain scoped to the requested world."""
    player_id = database.get_user_id("testplayer")
    assert player_id is not None
    assert database.create_character_for_user(
        player_id,
        "alt_world_talker",
        world_id="daily_undertaking",
    )

    assert chat_repo.add_chat_message(
        "testplayer_char", "Default world hello", "spawn", world_id="pipeworks_web"
    )
    assert chat_repo.add_chat_message(
        "alt_world_talker",
        "Alt world hello",
        "spawn",
        world_id="daily_undertaking",
    )

    default_rows = chat_repo.get_room_messages("spawn", world_id="pipeworks_web", limit=10)
    alt_rows = chat_repo.get_room_messages("spawn", world_id="daily_undertaking", limit=10)

    assert [row["message"] for row in default_rows] == ["Default world hello"]
    assert [row["message"] for row in alt_rows] == ["Alt world hello"]


def test_get_room_messages_whisper_visibility(test_db, temp_db_path, db_with_users):
    """Whispers should only be visible to sender and recipient in room history."""
    assert chat_repo.add_chat_message(
        "testplayer_char",
        "Public message",
        "spawn",
        world_id="pipeworks_web",
    )
    assert chat_repo.add_chat_message(
        "testplayer_char",
        "Secret message",
        "spawn",
        recipient="testadmin_char",
        world_id="pipeworks_web",
    )

    admin_rows = chat_repo.get_room_messages(
        "spawn",
        limit=10,
        username="testadmin_char",
        world_id="pipeworks_web",
    )
    super_rows = chat_repo.get_room_messages(
        "spawn",
        limit=10,
        username="testsuperuser_char",
        world_id="pipeworks_web",
    )

    assert "Secret message" in [row["message"] for row in admin_rows]
    assert "Secret message" not in [row["message"] for row in super_rows]


def test_add_chat_message_missing_sender_returns_false(test_db, temp_db_path):
    """Unknown sender identities should not create chat rows."""
    assert (
        chat_repo.add_chat_message("missing_sender", "boo", "spawn", world_id="pipeworks_web")
        is False
    )


def test_get_room_messages_unknown_character_returns_empty(test_db, temp_db_path, db_with_users):
    """Unknown viewer character/username should produce an empty room feed."""
    assert (
        chat_repo.get_room_messages("spawn", character_name="ghost", world_id="pipeworks_web") == []
    )


def test_chat_repo_raises_typed_errors_on_connection_failure():
    """Connection failures should surface as typed chat repository errors."""
    with patch.object(db_connection, "get_connection", side_effect=Exception("db boom")):
        with pytest.raises(DatabaseWriteError):
            chat_repo.add_chat_message(
                "testplayer_char", "hello", "spawn", world_id="pipeworks_web"
            )

        with pytest.raises(DatabaseReadError):
            chat_repo.get_room_messages("spawn", world_id="pipeworks_web")


# ============================================================================
# PRUNE TESTS
# ============================================================================


def test_prune_chat_messages_by_age(test_db, temp_db_path, db_with_users):
    """prune_chat_messages should delete rows older than threshold, leave newer rows."""
    assert chat_repo.add_chat_message(
        "testplayer_char", "old message", "spawn", world_id="pipeworks_web"
    )
    assert chat_repo.add_chat_message(
        "testadmin_char", "fresh message", "spawn", world_id="pipeworks_web"
    )

    # Age only the old message by manipulating its timestamp directly.
    with connection_scope(write=True) as conn:
        conn.execute(
            "UPDATE chat_messages SET timestamp = datetime('now', '-100 hours') "
            "WHERE message = 'old message'"
        )

    deleted = chat_repo.prune_chat_messages(1)

    assert deleted == 1
    rows = chat_repo.get_room_messages("spawn", world_id="pipeworks_web")
    messages = [r["message"] for r in rows]
    assert "fresh message" in messages
    assert "old message" not in messages


def test_prune_chat_messages_world_scoped(test_db, temp_db_path, db_with_users):
    """World-scoped prune should not touch messages in other worlds."""
    player_id = database.get_user_id("testplayer")
    assert player_id is not None
    database.create_character_for_user(player_id, "alt_char", world_id="daily_undertaking")

    assert chat_repo.add_chat_message(
        "testplayer_char", "web message", "spawn", world_id="pipeworks_web"
    )
    assert chat_repo.add_chat_message(
        "alt_char", "alt message", "spawn", world_id="daily_undertaking"
    )

    # Age both messages.
    _age_all_messages(100)

    # Prune only the web world.
    deleted = chat_repo.prune_chat_messages(1, world_id="pipeworks_web")

    assert deleted == 1
    alt_rows = chat_repo.get_room_messages("spawn", world_id="daily_undertaking")
    assert any(r["message"] == "alt message" for r in alt_rows)


def test_prune_chat_messages_room_scoped(test_db, temp_db_path, db_with_users):
    """Room-scoped prune should not touch messages in other rooms of the same world."""
    assert chat_repo.add_chat_message(
        "testplayer_char", "spawn msg", "spawn", world_id="pipeworks_web"
    )
    assert chat_repo.add_chat_message(
        "testadmin_char", "forest msg", "forest", world_id="pipeworks_web"
    )

    # Age both messages.
    _age_all_messages(100)

    # Prune only spawn room.
    deleted = chat_repo.prune_chat_messages(1, world_id="pipeworks_web", room="spawn")

    assert deleted == 1
    forest_rows = chat_repo.get_room_messages("forest", world_id="pipeworks_web")
    assert any(r["message"] == "forest msg" for r in forest_rows)


def test_prune_chat_messages_requires_world_for_room(test_db, temp_db_path):
    """Providing room without world_id must raise ValueError immediately."""
    with pytest.raises(ValueError, match="world_id"):
        chat_repo.prune_chat_messages(1, room="spawn")


def test_prune_chat_messages_invalid_age(test_db, temp_db_path):
    """max_age_hours < 1 must raise ValueError."""
    with pytest.raises(ValueError, match="max_age_hours"):
        chat_repo.prune_chat_messages(0)


def test_prune_chat_messages_no_old_messages(test_db, temp_db_path, db_with_users):
    """Pruning when no messages are old enough should return 0 deleted."""
    assert chat_repo.add_chat_message(
        "testplayer_char", "brand new", "spawn", world_id="pipeworks_web"
    )

    deleted = chat_repo.prune_chat_messages(1)

    assert deleted == 0
