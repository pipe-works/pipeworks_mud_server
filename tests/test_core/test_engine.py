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

from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.core.bus import MudBus
from mud_server.core.engine import GameEngine
from mud_server.core.events import Events
from mud_server.db import database
from tests.constants import TEST_PASSWORD

# ============================================================================
# BUS RESET FIXTURE
# ============================================================================
# The event bus is a singleton that persists across tests. We must reset it
# before and after each test to ensure event isolation.


@pytest.fixture(autouse=True)
def reset_bus_for_engine_tests():
    """
    Reset the event bus before and after each test.

    This ensures:
    - Tests start with empty event log
    - Tests don't leak events to other tests
    - Sequence numbers reset to 0
    """
    MudBus.reset_for_testing()
    yield
    MudBus.reset_for_testing()


# ============================================================================
# LOGIN/LOGOUT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_login_success(mock_engine, test_db, temp_db_path, db_with_users):
    """Test successful player login."""
    with use_test_database(temp_db_path):
        success, message, role = mock_engine.login("testplayer", TEST_PASSWORD, "session-123")

        assert success is True
        assert "Login successful" in message
        assert role == "player"


@pytest.mark.unit
@pytest.mark.game
def test_login_wrong_password(mock_engine, test_db, temp_db_path, db_with_users):
    """Test login with incorrect password."""
    with use_test_database(temp_db_path):
        success, message, role = mock_engine.login("testplayer", "wrongpassword", "session-123")

        assert success is False
        assert "Invalid username or password" in message
        assert role is None


@pytest.mark.unit
@pytest.mark.game
def test_login_nonexistent_user(mock_engine, test_db, temp_db_path):
    """Test login with non-existent username."""
    with use_test_database(temp_db_path):
        success, message, role = mock_engine.login("nonexistent", "password", "session-123")

        assert success is False
        assert "Invalid username or password" in message
        assert role is None


@pytest.mark.unit
@pytest.mark.game
def test_login_missing_user_id(mock_engine):
    """Test login fails when user id lookup fails."""
    with (
        patch.object(database, "user_exists", return_value=True),
        patch.object(database, "verify_password_for_user", return_value=True),
        patch.object(database, "is_user_active", return_value=True),
        patch.object(database, "get_user_role", return_value="player"),
        patch.object(database, "get_user_id", return_value=None),
    ):
        success, message, role = mock_engine.login("testplayer", TEST_PASSWORD, "session-123")

    assert success is False
    assert "Failed to retrieve account information" in message
    assert role is None


@pytest.mark.unit
@pytest.mark.game
def test_login_missing_role(mock_engine):
    """Test login fails when role lookup fails."""
    with (
        patch.object(database, "user_exists", return_value=True),
        patch.object(database, "verify_password_for_user", return_value=True),
        patch.object(database, "is_user_active", return_value=True),
        patch.object(database, "get_user_role", return_value=None),
    ):
        success, message, role = mock_engine.login("testplayer", TEST_PASSWORD, "session-123")

    assert success is False
    assert "Failed to retrieve account information" in message
    assert role is None


@pytest.mark.unit
@pytest.mark.game
def test_login_create_session_failure(mock_engine):
    """Test login fails when session creation fails."""
    with (
        patch.object(database, "user_exists", return_value=True),
        patch.object(database, "verify_password_for_user", return_value=True),
        patch.object(database, "is_user_active", return_value=True),
        patch.object(database, "get_user_role", return_value="player"),
        patch.object(database, "get_user_id", return_value=1),
        patch.object(database, "create_session", return_value=False),
    ):
        success, message, role = mock_engine.login("testplayer", TEST_PASSWORD, "session-123")

    assert success is False
    assert "Failed to create session" in message
    assert role is None


@pytest.mark.unit
@pytest.mark.game
def test_login_inactive_account(mock_engine, test_db, temp_db_path, db_with_users):
    """Test login with deactivated account."""
    with use_test_database(temp_db_path):
        database.deactivate_player("testplayer")
        success, message, role = mock_engine.login("testplayer", TEST_PASSWORD, "session-123")

        assert success is False
        assert "deactivated" in message.lower()
        assert role is None


@pytest.mark.unit
@pytest.mark.game
def test_logout(mock_engine, test_db, temp_db_path, db_with_users):
    """Test player logout."""
    with use_test_database(temp_db_path):
        # Create session
        database.create_session("testplayer", "session-123")

        # Logout
        result = mock_engine.logout("testplayer")
        assert result is True

        # Session should be removed
        active_players = database.get_active_players()
        assert "testplayer_char" not in active_players


@pytest.mark.unit
@pytest.mark.game
def test_logout_missing_user_id(mock_engine):
    """Test logout returns False when user id lookup fails."""
    with patch.object(database, "get_user_id", return_value=None):
        assert mock_engine.logout("missing") is False


# ============================================================================
# MOVEMENT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_move_valid_direction(mock_engine, test_db, temp_db_path, db_with_users):
    """Test moving in a valid direction."""
    with use_test_database(temp_db_path):
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
    with use_test_database(temp_db_path):
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
    with use_test_database(temp_db_path):
        # Set invalid room (non-existent room ID)
        database.set_player_room("testplayer", "invalid_room_xyz")

        success, message = mock_engine.move("testplayer", "north")

        assert success is False
        assert "not in a valid room" in message.lower()


# ============================================================================
# MOVEMENT EVENT EMISSION TESTS
# ============================================================================
# These tests verify that the event bus receives correct events when players
# move (or fail to move). The bus records facts about what happened - these
# events enable plugins to react to player movement.


@pytest.mark.unit
@pytest.mark.game
def test_move_emits_player_moved_event(mock_engine, test_db, temp_db_path, db_with_users):
    """
    Test that successful movement emits PLAYER_MOVED event.

    The event should contain:
    - username: Who moved
    - from_room: Where they were
    - to_room: Where they went
    - direction: Which way they went

    This is a FACT about what happened (Ledger), not a request (Newspaper).
    """
    with use_test_database(temp_db_path):
        # Set player in spawn
        database.set_player_room("testplayer", "spawn")

        # Clear any events from setup
        current_bus = MudBus()
        initial_count = len(current_bus.get_event_log())

        # Move north to forest
        success, message = mock_engine.move("testplayer", "north")

        assert success is True

        # Get events emitted after our move
        events = current_bus.get_event_log()[initial_count:]

        # Find the PLAYER_MOVED event
        moved_events = [e for e in events if e.type == Events.PLAYER_MOVED]
        assert len(moved_events) == 1, f"Expected 1 PLAYER_MOVED event, got {len(moved_events)}"

        event = moved_events[0]
        assert event.detail["username"] == "testplayer"
        assert event.detail["from_room"] == "spawn"
        assert event.detail["to_room"] == "forest"
        assert event.detail["direction"] == "north"


@pytest.mark.unit
@pytest.mark.game
def test_move_emits_player_move_failed_on_invalid_direction(
    mock_engine, test_db, temp_db_path, db_with_users
):
    """
    Test that failed movement (invalid direction) emits PLAYER_MOVE_FAILED event.

    The event should contain:
    - username: Who tried to move
    - room: Where they are (unchanged)
    - direction: Which way they tried to go
    - reason: Why it failed
    """
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        current_bus = MudBus()
        initial_count = len(current_bus.get_event_log())

        # Try to move west (no exit in spawn)
        success, message = mock_engine.move("testplayer", "west")

        assert success is False

        # Get events emitted after our move attempt
        events = current_bus.get_event_log()[initial_count:]

        # Find the PLAYER_MOVE_FAILED event
        failed_events = [e for e in events if e.type == Events.PLAYER_MOVE_FAILED]
        assert (
            len(failed_events) == 1
        ), f"Expected 1 PLAYER_MOVE_FAILED event, got {len(failed_events)}"

        event = failed_events[0]
        assert event.detail["username"] == "testplayer"
        assert event.detail["room"] == "spawn"
        assert event.detail["direction"] == "west"
        assert "no exit" in event.detail["reason"].lower()


@pytest.mark.unit
@pytest.mark.game
def test_move_emits_player_move_failed_on_invalid_room(
    mock_engine, test_db, temp_db_path, db_with_users
):
    """
    Test that movement from invalid room emits PLAYER_MOVE_FAILED event.

    When a player's current room doesn't exist, the move fails and an
    event is emitted with reason explaining the invalid room situation.
    """
    with use_test_database(temp_db_path):
        # Set invalid room (non-existent room ID)
        database.set_player_room("testplayer", "invalid_room_xyz")

        current_bus = MudBus()
        initial_count = len(current_bus.get_event_log())

        success, message = mock_engine.move("testplayer", "north")

        assert success is False

        # Get events emitted after our move attempt
        events = current_bus.get_event_log()[initial_count:]

        # Find the PLAYER_MOVE_FAILED event
        failed_events = [e for e in events if e.type == Events.PLAYER_MOVE_FAILED]
        assert (
            len(failed_events) == 1
        ), f"Expected 1 PLAYER_MOVE_FAILED event, got {len(failed_events)}"

        event = failed_events[0]
        assert event.detail["username"] == "testplayer"
        assert event.detail["room"] == "invalid_room_xyz"
        assert event.detail["direction"] == "north"
        # The engine's reason is "Room not in world data" - this is the internal reason
        assert "not in world data" in event.detail["reason"].lower()


@pytest.mark.unit
@pytest.mark.game
def test_move_events_have_sequential_sequence_numbers(
    mock_engine, test_db, temp_db_path, db_with_users
):
    """
    Test that movement events have monotonically increasing sequence numbers.

    Sequence numbers are critical for deterministic replay - they establish
    the authoritative ordering of events in Logical Time.
    """
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        current_bus = MudBus()

        # Make two successful moves
        mock_engine.move("testplayer", "north")  # spawn -> forest
        mock_engine.move("testplayer", "south")  # forest -> spawn

        events = current_bus.get_event_log()
        moved_events = [e for e in events if e.type == Events.PLAYER_MOVED]

        assert len(moved_events) == 2

        # Sequence numbers should be monotonically increasing
        assert moved_events[0].meta is not None
        assert moved_events[1].meta is not None
        assert moved_events[0].meta.sequence < moved_events[1].meta.sequence


@pytest.mark.unit
@pytest.mark.game
def test_move_events_have_engine_source(mock_engine, test_db, temp_db_path, db_with_users):
    """
    Test that movement events have 'engine' as their source.

    The source identifies which system emitted the event, enabling
    plugins to filter or prioritize based on origin.
    """
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        current_bus = MudBus()

        mock_engine.move("testplayer", "north")

        events = current_bus.get_event_log()
        moved_events = [e for e in events if e.type == Events.PLAYER_MOVED]

        assert len(moved_events) == 1
        assert moved_events[0].meta is not None
        assert moved_events[0].meta.source == "engine"


# ============================================================================
# CHAT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_chat_success(mock_engine, test_db, temp_db_path, db_with_users):
    """Test sending a chat message."""
    with use_test_database(temp_db_path):
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
    with use_test_database(temp_db_path):
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
    with use_test_database(temp_db_path):
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
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        # testadmin exists but is not online (no session)
        success, message = mock_engine.whisper("testplayer", "testadmin", "Hello")

        assert success is False
        assert "not online" in message.lower()


@pytest.mark.unit
@pytest.mark.game
def test_whisper_target_different_room(mock_engine, test_db, temp_db_path, db_with_users):
    """Test whispering to player in different room."""
    with use_test_database(temp_db_path):
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
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        success, message = mock_engine.whisper("testplayer", "nonexistent", "Hello")

        assert success is False
        assert "does not exist" in message.lower()


# ============================================================================
# XSS SANITIZATION TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
@pytest.mark.security
def test_chat_sanitizes_xss(mock_engine, test_db, temp_db_path, db_with_users):
    """Test that chat messages are sanitized to prevent XSS attacks."""
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        xss_payload = "<script>alert('xss')</script>"
        success, message = mock_engine.chat("testplayer", xss_payload)

        assert success is True
        # Verify the response contains escaped HTML
        assert "&lt;script&gt;" in message
        assert "<script>" not in message

        # Verify stored message is also sanitized
        messages = database.get_room_messages("spawn", limit=10)
        assert len(messages) == 1
        assert "&lt;script&gt;" in messages[0]["message"]
        assert "<script>" not in messages[0]["message"]


@pytest.mark.unit
@pytest.mark.game
@pytest.mark.security
def test_yell_sanitizes_xss(mock_engine, test_db, temp_db_path, db_with_users):
    """Test that yell messages are sanitized to prevent XSS attacks."""
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        xss_payload = "<img src=x onerror=alert('xss')>"
        success, message = mock_engine.yell("testplayer", xss_payload)

        assert success is True
        # Verify the response contains escaped HTML
        assert "&lt;img" in message
        assert "<img" not in message


@pytest.mark.unit
@pytest.mark.game
@pytest.mark.security
def test_whisper_sanitizes_xss(mock_engine, test_db, temp_db_path, db_with_users):
    """Test that whisper messages are sanitized to prevent XSS attacks."""
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")
        database.set_player_room("testadmin", "spawn")
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        xss_payload = "<a href='javascript:alert(1)'>click</a>"
        success, message = mock_engine.whisper("testplayer", "testadmin", xss_payload)

        assert success is True
        # Verify the response contains escaped HTML
        assert "&lt;a href" in message
        assert "<a href" not in message


# ============================================================================
# INVENTORY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_pickup_item_success(mock_engine, test_db, temp_db_path, db_with_users):
    """Test picking up an item from room."""
    with use_test_database(temp_db_path):
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
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "forest")  # No items in forest

        success, message = mock_engine.pickup_item("testplayer", "torch")

        assert success is False
        assert "no" in message.lower()
        assert "torch" in message.lower()


@pytest.mark.unit
@pytest.mark.game
def test_pickup_item_case_insensitive(mock_engine, test_db, temp_db_path, db_with_users):
    """Test that item pickup is case-insensitive."""
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        success, message = mock_engine.pickup_item("testplayer", "TORCH")

        assert success is True
        assert "torch" in database.get_player_inventory("testplayer")


@pytest.mark.unit
@pytest.mark.game
def test_drop_item_success(mock_engine, test_db, temp_db_path, db_with_users):
    """Test dropping an item from inventory."""
    with use_test_database(temp_db_path):
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
    with use_test_database(temp_db_path):
        success, message = mock_engine.drop_item("testplayer", "sword")

        assert success is False
        assert "don't have" in message.lower()
        assert "sword" in message.lower()


@pytest.mark.unit
@pytest.mark.game
def test_get_inventory_empty(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting empty inventory."""
    with use_test_database(temp_db_path):
        inventory_text = mock_engine.get_inventory("testplayer")

        assert "empty" in inventory_text.lower()


@pytest.mark.unit
@pytest.mark.game
def test_get_inventory_with_items(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting inventory with items."""
    with use_test_database(temp_db_path):
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
    with use_test_database(temp_db_path):
        with patch("mud_server.core.world.database.get_players_in_room", return_value=[]):
            database.set_player_room("testplayer", "spawn")

            description = mock_engine.look("testplayer")

            assert "Test Spawn" in description
            assert "A test spawn room" in description


@pytest.mark.unit
@pytest.mark.game
def test_look_invalid_room(mock_engine, test_db, temp_db_path, db_with_users):
    """Test looking when not in a valid room."""
    with use_test_database(temp_db_path):
        # Set invalid room (non-existent room ID)
        database.set_player_room("testplayer", "invalid_room_xyz")

        description = mock_engine.look("testplayer")

        assert "not in a valid room" in description.lower()


# ============================================================================
# ACTIVE PLAYERS TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_get_active_players(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting list of active players."""
    with use_test_database(temp_db_path):
        # Create sessions
        database.create_session("testplayer", "session-1")
        database.create_session("testadmin", "session-2")

        active = mock_engine.get_active_players()

        assert len(active) == 2
        assert "testplayer_char" in active
        assert "testadmin_char" in active


@pytest.mark.unit
@pytest.mark.game
def test_get_active_players_empty(mock_engine, test_db, temp_db_path):
    """Test getting active players when none are online."""
    with use_test_database(temp_db_path):
        active = mock_engine.get_active_players()
        assert len(active) == 0


# ============================================================================
# GET ROOM CHAT TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.game
def test_get_room_chat_with_messages(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting room chat history."""
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        # Add some messages
        database.add_chat_message("testplayer", "Hello!", "spawn")
        database.add_chat_message("testadmin", "Hi there!", "spawn")

        chat_text = mock_engine.get_room_chat("testplayer", limit=10)

        assert "[Recent messages]:" in chat_text
        assert "testplayer_char: Hello!" in chat_text
        assert "testadmin_char: Hi there!" in chat_text


@pytest.mark.unit
@pytest.mark.game
def test_get_room_chat_empty(mock_engine, test_db, temp_db_path, db_with_users):
    """Test getting chat when room has no messages."""
    with use_test_database(temp_db_path):
        database.set_player_room("testplayer", "spawn")

        chat_text = mock_engine.get_room_chat("testplayer", limit=10)

        assert "No messages in this room yet" in chat_text


@pytest.mark.unit
@pytest.mark.game
def test_recall_to_zone_spawn(mock_engine, test_db, temp_db_path, db_with_users):
    """Test recall returns player to their zone's spawn point."""
    with use_test_database(temp_db_path):
        # Move player away from spawn
        database.set_player_room("testplayer", "forest")

        # Recall should return to spawn (mock world's default/only zone spawn)
        success, message = mock_engine.recall("testplayer")

        assert success is True
        assert "recall" in message.lower() or "spawn" in message.lower()
        # Player should be back at spawn
        assert database.get_player_room("testplayer") == "spawn"


@pytest.mark.unit
@pytest.mark.game
def test_recall_already_at_spawn(mock_engine, test_db, temp_db_path, db_with_users):
    """Test recall when already at spawn point."""
    with use_test_database(temp_db_path):
        # Player already at spawn
        database.set_player_room("testplayer", "spawn")

        success, message = mock_engine.recall("testplayer")

        assert success is True
        assert "already" in message.lower()
        assert database.get_player_room("testplayer") == "spawn"


@pytest.mark.unit
@pytest.mark.game
def test_recall_with_zone_configured(test_db, temp_db_path, db_with_users):
    """Test recall returns to zone spawn when player is in a zone with zones configured."""
    from mud_server.core.world import Room, Zone

    with use_test_database(temp_db_path):
        # Create engine with zones configured
        with patch.object(GameEngine, "__init__", lambda self: None):
            engine = GameEngine()

            # Create a mock world with zones
            engine.world = type("MockWorld", (), {})()
            engine.world.zones = {
                "pub_zone": Zone(
                    id="pub_zone",
                    name="The Pub District",
                    description="A district of pubs",
                    spawn_room="pub_spawn",
                    rooms=["pub_spawn", "back_room"],
                ),
            }
            engine.world.rooms = {
                "pub_spawn": Room(
                    id="pub_spawn",
                    name="Pub Spawn",
                    description="The pub entrance",
                    exits={"east": "back_room"},
                    items=[],
                ),
                "back_room": Room(
                    id="back_room",
                    name="Back Room",
                    description="A back room",
                    exits={"west": "pub_spawn"},
                    items=[],
                ),
            }
            engine.world.default_spawn = ("pub_zone", "pub_spawn")
            with (
                patch.object(
                    engine.world,
                    "get_room",
                    side_effect=lambda rid: engine.world.rooms.get(rid),
                    create=True,
                ),
                patch.object(
                    engine.world,
                    "get_room_description",
                    side_effect=lambda rid, user: f"You are in {rid}",
                    create=True,
                ),
            ):
                # Set player in the zone's back_room
                database.set_player_room("testplayer", "back_room")

                # Recall should return to zone spawn
                success, message = engine.recall("testplayer")

            assert success is True
            assert "The Pub District" in message  # Zone name in message
            assert database.get_player_room("testplayer") == "pub_spawn"


@pytest.mark.unit
@pytest.mark.game
def test_recall_database_failure(test_db, temp_db_path, db_with_users):
    """Test recall when database update fails."""
    from mud_server.core.world import Room

    with use_test_database(temp_db_path):
        with patch.object(GameEngine, "__init__", lambda self: None):
            engine = GameEngine()

            # Create a mock world
            engine.world = type("MockWorld", (), {})()
            engine.world.zones = {}
            engine.world.default_spawn = ("", "spawn")
            engine.world.rooms = {
                "spawn": Room(
                    id="spawn",
                    name="Spawn",
                    description="Spawn",
                    exits={},
                    items=[],
                ),
                "other_room": Room(
                    id="other_room",
                    name="Other",
                    description="Other",
                    exits={},
                    items=[],
                ),
            }
            with (
                patch.object(
                    engine.world,
                    "get_room",
                    side_effect=lambda rid: engine.world.rooms.get(rid),
                    create=True,
                ),
                patch.object(
                    engine.world,
                    "get_room_description",
                    side_effect=lambda rid, user: f"You are in {rid}",
                    create=True,
                ),
            ):
                # Set player away from spawn
                database.set_player_room("testplayer", "other_room")

                # Mock database failure
                with patch.object(database, "set_character_room", return_value=False):
                    success, message = engine.recall("testplayer")

            assert success is False
            assert "Failed to recall" in message


@pytest.mark.unit
@pytest.mark.game
def test_opposite_direction():
    """Test the _opposite_direction static method."""

    assert GameEngine._opposite_direction("north") == "south"
    assert GameEngine._opposite_direction("south") == "north"
    assert GameEngine._opposite_direction("east") == "west"
    assert GameEngine._opposite_direction("west") == "east"
    assert GameEngine._opposite_direction("up") == "down"
    assert GameEngine._opposite_direction("down") == "up"
    # Unrecognized directions return "somewhere"
    assert GameEngine._opposite_direction("diagonal") == "somewhere"
