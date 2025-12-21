"""
Unit tests for GameEngine class (mud_server/core/engine.py).

Tests cover:
- Player login and logout
- Movement between rooms
- Inventory management (pickup, drop, view)
- Chat commands (say, yell, whisper)
- Room observation (look)
- Active player queries

All tests use mocked database and world for isolation.
"""

import pytest
from unittest.mock import patch, Mock
from mud_server.core.engine import GameEngine
from mud_server.db import database


# ============================================================================
# LOGIN/LOGOUT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_login_success(mock_engine, test_db, temp_db_path, db_with_users):
    """Test successful player login."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        success, message, role = mock_engine.login("testplayer", "password123", "session-123")

        assert success is True
        assert "Welcome" in message
        assert "testplayer" in message
        assert role == "player"


@pytest.mark.unit
@pytest.mark.game
def test_login_wrong_password(mock_engine, test_db, temp_db_path, db_with_users):
    """Test login with incorrect password."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        success, message, role = mock_engine.login("testplayer", "wrongpassword", "session-123")

        assert success is False
        assert "Invalid username or password" in message
        assert role is None


@pytest.mark.unit
@pytest.mark.game
def test_login_nonexistent_user(mock_engine, test_db, temp_db_path):
    """Test login with non-existent username."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        success, message, role = mock_engine.login("nonexistent", "password", "session-123")

        assert success is False
        assert "Invalid username or password" in message
        assert role is None


@pytest.mark.unit
@pytest.mark.game
def test_login_inactive_account(mock_engine, test_db, temp_db_path, db_with_users):
    """Test login with deactivated account."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.deactivate_player("testplayer")
        success, message, role = mock_engine.login("testplayer", "password123", "session-123")

        assert success is False
        assert "deactivated" in message.lower()
        assert role is None


@pytest.mark.unit
@pytest.mark.game
def test_logout(mock_engine, test_db, temp_db_path, db_with_users):
    """Test player logout."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        # Create session
        database.create_session("testplayer", "session-123")

        # Logout
        result = mock_engine.logout("testplayer")
        assert result is True

        # Session should be removed
        active_players = database.get_active_players()
        assert "testplayer" not in active_players


# ============================================================================
# MOVEMENT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_move_valid_direction(mock_engine, test_db, temp_db_path, db_with_users):
    """Test moving in a valid direction."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        # Set player in spawn
        database.set_player_room("testplayer", "spawn")

        # Move north to forest
        success, message = mock_engine.move("testplayer", "north")

        assert success is True
        assert "move" in message.lower()
        assert "Test Forest" in message  # Destination room name

        # Verify room changed
        assert database.get_player_room("testplayer") == "forest"


@pytest.mark.unit
@pytest.mark.game
def test_move_invalid_direction(mock_engine, test_db, temp_db_path, db_with_users):
    """Test moving in an invalid direction."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "spawn")

        success, message = mock_engine.move("testplayer", "west")

        assert success is False
        assert "cannot move" in message.lower()

        # Room should not change
        assert database.get_player_room("testplayer") == "spawn"


@pytest.mark.unit
@pytest.mark.game
def test_move_from_invalid_room(mock_engine, test_db, temp_db_path, db_with_users):
    """Test movement when player is not in a valid room."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        # Set invalid room
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE players SET current_room = NULL WHERE username = ?",
            ("testplayer",)
        )
        conn.commit()
        conn.close()

        success, message = mock_engine.move("testplayer", "north")

        assert success is False
        assert "not in a valid room" in message.lower()


# ============================================================================
# CHAT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_chat_success(mock_engine, test_db, temp_db_path, db_with_users):
    """Test sending a chat message."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "spawn")

        success, message = mock_engine.chat("testplayer", "Hello everyone!")

        assert success is True
        assert "You say:" in message
        assert "Hello everyone!" in message

        # Verify message was saved
        messages = database.get_room_messages("spawn", limit=10)
        assert len(messages) == 1
        assert messages[0]["message"] == "Hello everyone!"


@pytest.mark.unit
@pytest.mark.game
def test_yell_sends_to_adjacent_rooms(mock_engine, test_db, temp_db_path, db_with_users):
    """Test yelling sends message to current and adjacent rooms."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "spawn")

        success, message = mock_engine.yell("testplayer", "Can anyone hear me?")

        assert success is True
        assert "You yell:" in message

        # Check message in spawn (current room)
        spawn_messages = database.get_room_messages("spawn", limit=10)
        assert any("[YELL]" in msg["message"] for msg in spawn_messages)

        # Check message in forest (adjacent room to north)
        forest_messages = database.get_room_messages("forest", limit=10)
        assert any("[YELL]" in msg["message"] for msg in forest_messages)

        # Check message in desert (adjacent room to south)
        desert_messages = database.get_room_messages("desert", limit=10)
        assert any("[YELL]" in msg["message"] for msg in desert_messages)


@pytest.mark.unit
@pytest.mark.game
def test_whisper_success(mock_engine, test_db, temp_db_path, db_with_users):
    """Test whispering to another player in same room."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        # Both players in spawn
        database.set_player_room("testplayer", "spawn")
        database.set_player_room("testadmin", "spawn")

        # Create sessions (both online)
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        success, message = mock_engine.whisper("testplayer", "testadmin", "Secret message")

        assert success is True
        assert "You whisper to testadmin:" in message
        assert "Secret message" in message


@pytest.mark.unit
@pytest.mark.game
def test_whisper_target_not_online(mock_engine, test_db, temp_db_path, db_with_users):
    """Test whispering to offline player."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "spawn")

        # testadmin exists but is not online (no session)
        success, message = mock_engine.whisper("testplayer", "testadmin", "Hello")

        assert success is False
        assert "not online" in message.lower()


@pytest.mark.unit
@pytest.mark.game
def test_whisper_target_different_room(mock_engine, test_db, temp_db_path, db_with_users):
    """Test whispering to player in different room."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        # Players in different rooms
        database.set_player_room("testplayer", "spawn")
        database.set_player_room("testadmin", "forest")

        # Both online
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        success, message = mock_engine.whisper("testplayer", "testadmin", "Hello")

        assert success is False
        assert "not in this room" in message.lower()


@pytest.mark.unit
@pytest.mark.game
def test_whisper_nonexistent_target(mock_engine, test_db, temp_db_path, db_with_users):
    """Test whispering to non-existent player."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "spawn")

        success, message = mock_engine.whisper("testplayer", "nonexistent", "Hello")

        assert success is False
        assert "does not exist" in message.lower()


# ============================================================================
# INVENTORY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_pickup_item_success(mock_engine, test_db, temp_db_path, db_with_users):
    """Test picking up an item from room."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "spawn")

        success, message = mock_engine.pickup_item("testplayer", "torch")

        assert success is True
        assert "picked up" in message.lower()
        assert "Torch" in message

        # Verify item in inventory
        inventory = database.get_player_inventory("testplayer")
        assert "torch" in inventory


@pytest.mark.unit
@pytest.mark.game
def test_pickup_item_not_in_room(mock_engine, test_db, temp_db_path, db_with_users):
    """Test picking up item not in current room."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "forest")  # No items in forest

        success, message = mock_engine.pickup_item("testplayer", "torch")

        assert success is False
        assert "no" in message.lower()
        assert "torch" in message.lower()


@pytest.mark.unit
@pytest.mark.game
def test_pickup_item_case_insensitive(mock_engine, test_db, temp_db_path, db_with_users):
    """Test that item pickup is case-insensitive."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "spawn")

        success, message = mock_engine.pickup_item("testplayer", "TORCH")

        assert success is True
        assert "torch" in database.get_player_inventory("testplayer")


@pytest.mark.unit
@pytest.mark.game
def test_drop_item_success(mock_engine, test_db, temp_db_path, db_with_users):
    """Test dropping an item from inventory."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        # Add item to inventory
        database.set_player_inventory("testplayer", ["torch", "rope"])

        success, message = mock_engine.drop_item("testplayer", "torch")

        assert success is True
        assert "dropped" in message.lower()
        assert "Torch" in message

        # Verify item removed from inventory
        inventory = database.get_player_inventory("testplayer")
        assert "torch" not in inventory
        assert "rope" in inventory  # Other items remain


@pytest.mark.unit
@pytest.mark.game
def test_drop_item_not_in_inventory(mock_engine, test_db, temp_db_path, db_with_users):
    """Test dropping item not in inventory."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        success, message = mock_engine.drop_item("testplayer", "sword")

        assert success is False
        assert "don't have" in message.lower()
        assert "sword" in message.lower()


@pytest.mark.unit
@pytest.mark.game
def test_get_inventory_empty(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting empty inventory."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        inventory_text = mock_engine.get_inventory("testplayer")

        assert "empty" in inventory_text.lower()


@pytest.mark.unit
@pytest.mark.game
def test_get_inventory_with_items(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting inventory with items."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_inventory("testplayer", ["torch", "rope"])

        inventory_text = mock_engine.get_inventory("testplayer")

        assert "Your inventory:" in inventory_text
        assert "Torch" in inventory_text
        assert "Rope" in inventory_text


# ============================================================================
# ROOM OBSERVATION TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_look_in_room(mock_engine, test_db, temp_db_path, db_with_users):
    """Test looking around in a room."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        with patch('mud_server.core.world.database.get_players_in_room', return_value=[]):
            database.set_player_room("testplayer", "spawn")

            description = mock_engine.look("testplayer")

            assert "Test Spawn" in description
            assert "A test spawn room" in description


@pytest.mark.unit
@pytest.mark.game
def test_look_invalid_room(mock_engine, test_db, temp_db_path, db_with_users):
    """Test looking when not in a valid room."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        # Set invalid room
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE players SET current_room = NULL WHERE username = ?",
            ("testplayer",)
        )
        conn.commit()
        conn.close()

        description = mock_engine.look("testplayer")

        assert "not in a valid room" in description.lower()


# ============================================================================
# ACTIVE PLAYERS TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_get_active_players(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting list of active players."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        # Create sessions
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        active = mock_engine.get_active_players()

        assert len(active) == 2
        assert "testplayer" in active
        assert "testadmin" in active


@pytest.mark.unit
@pytest.mark.game
def test_get_active_players_empty(mock_engine, test_db, temp_db_path):
    """Test getting active players when none are online."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        active = mock_engine.get_active_players()
        assert len(active) == 0


# ============================================================================
# GET ROOM CHAT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_get_room_chat_with_messages(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting room chat history."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "spawn")

        # Add some messages
        database.add_chat_message("testplayer", "Hello!", "spawn")
        database.add_chat_message("testadmin", "Hi there!", "spawn")

        chat_text = mock_engine.get_room_chat("testplayer", limit=10)

        assert "[Recent messages]:" in chat_text
        assert "testplayer: Hello!" in chat_text
        assert "testadmin: Hi there!" in chat_text


@pytest.mark.unit
@pytest.mark.game
def test_get_room_chat_empty(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting chat when room has no messages."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        database.set_player_room("testplayer", "spawn")

        chat_text = mock_engine.get_room_chat("testplayer", limit=10)

        assert "No messages in this room yet" in chat_text


@pytest.mark.unit
@pytest.mark.game
def test_opposite_direction():
    """Test the _opposite_direction static method."""
    from mud_server.core.engine import GameEngine

    assert GameEngine._opposite_direction("north") == "south"
    assert GameEngine._opposite_direction("south") == "north"
    assert GameEngine._opposite_direction("east") == "west"
    assert GameEngine._opposite_direction("west") == "east"
    assert GameEngine._opposite_direction("up") == "somewhere"
