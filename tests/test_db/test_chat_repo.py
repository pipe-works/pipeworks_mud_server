"""Focused tests for ``mud_server.db.chat_repo``."""

from __future__ import annotations

from mud_server.db import chat_repo, database


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
        "testplayer", "Default world hello", "spawn", world_id="pipeworks_web"
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
    assert chat_repo.add_chat_message("testplayer", "Public message", "spawn")
    assert chat_repo.add_chat_message(
        "testplayer", "Secret message", "spawn", recipient="testadmin"
    )

    admin_rows = chat_repo.get_room_messages("spawn", limit=10, username="testadmin")
    super_rows = chat_repo.get_room_messages("spawn", limit=10, username="testsuperuser")

    assert "Secret message" in [row["message"] for row in admin_rows]
    assert "Secret message" not in [row["message"] for row in super_rows]


def test_add_chat_message_missing_sender_returns_false(test_db, temp_db_path):
    """Unknown sender identities should not create chat rows."""
    assert chat_repo.add_chat_message("missing_sender", "boo", "spawn") is False


def test_get_room_messages_unknown_character_returns_empty(test_db, temp_db_path, db_with_users):
    """Unknown viewer character/username should produce an empty room feed."""
    assert chat_repo.get_room_messages("spawn", character_name="ghost") == []
