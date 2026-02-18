"""Compatibility-surface tests for chat helpers exported by ``db.database``."""

import pytest

from mud_server.config import use_test_database
from mud_server.db import database


@pytest.mark.unit
@pytest.mark.db
def test_add_chat_message(test_db, temp_db_path, db_with_users):
    """Test adding a chat message."""
    with use_test_database(temp_db_path):
        result = database.add_chat_message(
            "testplayer_char",
            "Hello world",
            "spawn",
            world_id=database.DEFAULT_WORLD_ID,
        )
        assert result is True


@pytest.mark.unit
@pytest.mark.db
def test_add_chat_message_with_recipient(test_db, temp_db_path, db_with_users):
    """Test adding a whisper message with recipient."""
    with use_test_database(temp_db_path):
        result = database.add_chat_message(
            "testplayer_char",
            "[WHISPER] Secret message",
            "spawn",
            recipient="testadmin_char",
            world_id=database.DEFAULT_WORLD_ID,
        )
        assert result is True


@pytest.mark.unit
@pytest.mark.db
def test_get_room_messages(test_db, temp_db_path, db_with_users):
    """Test retrieving room messages."""
    with use_test_database(temp_db_path):
        # Add some messages
        database.add_chat_message(
            "testplayer_char",
            "Message 1",
            "spawn",
            world_id=database.DEFAULT_WORLD_ID,
        )
        database.add_chat_message(
            "testadmin_char",
            "Message 2",
            "spawn",
            world_id=database.DEFAULT_WORLD_ID,
        )
        database.add_chat_message(
            "testplayer_char",
            "Message 3",
            "forest",
            world_id=database.DEFAULT_WORLD_ID,
        )

        # Get spawn messages
        messages = database.get_room_messages(
            "spawn",
            limit=10,
            world_id=database.DEFAULT_WORLD_ID,
        )
        assert len(messages) == 2
        assert messages[0]["message"] == "Message 1"
        assert messages[1]["message"] == "Message 2"


@pytest.mark.unit
@pytest.mark.db
def test_get_room_messages_world_isolation(test_db, temp_db_path, db_with_users):
    """Room messages should be isolated by world_id."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None

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

        assert database.create_character_for_user(
            user_id, "alt_player", world_id="daily_undertaking"
        )

        database.add_chat_message(
            "testplayer_char", "Default world", "spawn", world_id="pipeworks_web"
        )
        database.add_chat_message("alt_player", "Alt world", "spawn", world_id="daily_undertaking")

        default_messages = database.get_room_messages("spawn", world_id="pipeworks_web", limit=10)
        assert len(default_messages) == 1
        assert default_messages[0]["message"] == "Default world"

        alt_messages = database.get_room_messages("spawn", world_id="daily_undertaking", limit=10)
        assert len(alt_messages) == 1
        assert alt_messages[0]["message"] == "Alt world"


@pytest.mark.unit
@pytest.mark.db
def test_get_room_messages_with_whisper_filtering(test_db, temp_db_path, db_with_users):
    """Test that whispers are filtered per user."""
    with use_test_database(temp_db_path):
        database.add_chat_message(
            "testplayer_char",
            "Public message",
            "spawn",
            world_id=database.DEFAULT_WORLD_ID,
        )

        database.add_chat_message(
            "testplayer_char",
            "[WHISPER] Secret",
            "spawn",
            recipient="testadmin_char",
            world_id=database.DEFAULT_WORLD_ID,
        )

        messages = database.get_room_messages(
            "spawn",
            limit=10,
            username="testadmin_char",
            world_id=database.DEFAULT_WORLD_ID,
        )
        assert len(messages) == 2

        messages = database.get_room_messages(
            "spawn",
            limit=10,
            username="testsuperuser_char",
            world_id=database.DEFAULT_WORLD_ID,
        )
        assert len(messages) == 1
        assert messages[0]["message"] == "Public message"


@pytest.mark.unit
@pytest.mark.db
def test_add_chat_message_missing_sender_returns_false(test_db, temp_db_path):
    """Chat writes should return False when sender character does not exist."""
    with use_test_database(temp_db_path):
        assert (
            database.add_chat_message(
                "ghost",
                "boo",
                "spawn",
                world_id=database.DEFAULT_WORLD_ID,
            )
            is False
        )


@pytest.mark.unit
@pytest.mark.db
def test_get_room_messages_unknown_character_returns_empty(test_db, temp_db_path):
    """Whisper-filtered reads should return empty for unknown character identity."""
    with use_test_database(temp_db_path):
        assert (
            database.get_room_messages(
                "spawn",
                character_name="ghost",
                world_id=database.DEFAULT_WORLD_ID,
            )
            == []
        )
