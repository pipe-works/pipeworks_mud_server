"""
Unit tests for World class and data structures (mud_server/core/world.py).

Tests cover:
- Room and Item dataclasses
- World initialization and data loading
- Room and item retrieval
- Room description generation
- Movement validation
- Exit resolution

All tests use mocked world data to avoid file dependencies.
"""

from unittest.mock import patch

import pytest

# ============================================================================
# ROOM DATACLASS TESTS
# ============================================================================


@pytest.mark.unit
def test_room_creation(sample_room):
    """Test creating a Room instance."""
    assert sample_room.id == "test_room"
    assert sample_room.name == "Test Room"
    assert sample_room.description == "A room for testing"
    assert sample_room.exits == {"north": "other_room"}
    assert sample_room.items == ["torch"]


@pytest.mark.unit
def test_room_str_representation(sample_room):
    """Test Room string representation."""
    result = str(sample_room)
    assert "Test Room" in result
    assert "A room for testing" in result


# ============================================================================
# ITEM DATACLASS TESTS
# ============================================================================


@pytest.mark.unit
def test_item_creation(sample_item):
    """Test creating an Item instance."""
    assert sample_item.id == "test_item"
    assert sample_item.name == "Test Item"
    assert sample_item.description == "An item for testing"


# ============================================================================
# WORLD INITIALIZATION TESTS
# ============================================================================


@pytest.mark.unit
def test_world_loads_from_mock_data(mock_world):
    """Test that World successfully loads from mocked data."""
    assert len(mock_world.rooms) == 3
    assert len(mock_world.items) == 2


@pytest.mark.unit
def test_world_loads_rooms_correctly(mock_world):
    """Test that rooms are loaded with correct data."""
    spawn = mock_world.get_room("spawn")
    assert spawn is not None
    assert spawn.name == "Test Spawn"
    assert spawn.description == "A test spawn room"
    assert "north" in spawn.exits
    assert "south" in spawn.exits


@pytest.mark.unit
def test_world_loads_items_correctly(mock_world):
    """Test that items are loaded with correct data."""
    torch = mock_world.get_item("torch")
    assert torch is not None
    assert torch.name == "Torch"
    assert torch.description == "A wooden torch"


# ============================================================================
# ROOM RETRIEVAL TESTS
# ============================================================================


@pytest.mark.unit
def test_get_room_existing(mock_world):
    """Test retrieving an existing room."""
    room = mock_world.get_room("spawn")
    assert room is not None
    assert room.id == "spawn"
    assert room.name == "Test Spawn"


@pytest.mark.unit
def test_get_room_nonexistent(mock_world):
    """Test retrieving a non-existent room returns None."""
    room = mock_world.get_room("nonexistent")
    assert room is None


# ============================================================================
# ITEM RETRIEVAL TESTS
# ============================================================================


@pytest.mark.unit
def test_get_item_existing(mock_world):
    """Test retrieving an existing item."""
    item = mock_world.get_item("torch")
    assert item is not None
    assert item.id == "torch"
    assert item.name == "Torch"


@pytest.mark.unit
def test_get_item_nonexistent(mock_world):
    """Test retrieving a non-existent item returns None."""
    item = mock_world.get_item("nonexistent")
    assert item is None


# ============================================================================
# MOVEMENT VALIDATION TESTS
# ============================================================================


@pytest.mark.unit
def test_can_move_valid_direction(mock_world):
    """Test movement validation for valid direction."""
    can_move, destination = mock_world.can_move("spawn", "north")
    assert can_move is True
    assert destination == "forest"


@pytest.mark.unit
def test_can_move_invalid_direction(mock_world):
    """Test movement validation for invalid direction."""
    can_move, destination = mock_world.can_move("spawn", "west")
    assert can_move is False
    assert destination is None


@pytest.mark.unit
def test_can_move_case_insensitive(mock_world):
    """Test that movement direction is case-insensitive."""
    can_move, destination = mock_world.can_move("spawn", "NORTH")
    assert can_move is True
    assert destination == "forest"


@pytest.mark.unit
def test_can_move_from_nonexistent_room(mock_world):
    """Test movement from non-existent room."""
    can_move, destination = mock_world.can_move("nonexistent", "north")
    assert can_move is False
    assert destination is None


# ============================================================================
# ROOM DESCRIPTION TESTS
# ============================================================================


@pytest.mark.unit
def test_get_room_description_basic(mock_world):
    """Test generating basic room description."""
    with patch("mud_server.core.world.database.get_players_in_room", return_value=[]):
        desc = mock_world.get_room_description("spawn", "testplayer")

        # Check room name and description
        assert "Test Spawn" in desc
        assert "A test spawn room" in desc


@pytest.mark.unit
def test_get_room_description_with_items(mock_world):
    """Test room description includes items."""
    with patch("mud_server.core.world.database.get_players_in_room", return_value=[]):
        desc = mock_world.get_room_description("spawn", "testplayer")

        # Check items section
        assert "[Items here]:" in desc
        assert "Torch" in desc
        assert "Rope" in desc


@pytest.mark.unit
def test_get_room_description_with_exits(mock_world):
    """Test room description includes exits."""
    with patch("mud_server.core.world.database.get_players_in_room", return_value=[]):
        desc = mock_world.get_room_description("spawn", "testplayer")

        # Check exits section
        assert "[Exits]:" in desc
        assert "north" in desc
        assert "south" in desc
        assert "Test Forest" in desc  # Destination room name
        assert "Test Desert" in desc


@pytest.mark.unit
def test_get_room_description_with_other_players(mock_world):
    """Test room description includes other players."""
    with patch(
        "mud_server.core.world.database.get_players_in_room",
        return_value=["testplayer", "otherplayer", "admin"],
    ):
        desc = mock_world.get_room_description("spawn", "testplayer")

        # Check players section
        assert "[Players here]:" in desc
        assert "otherplayer" in desc
        assert "admin" in desc
        # Requesting player should be excluded
        assert (
            desc.count("testplayer") == 0
            or "testplayer" not in desc.split("[Players here]:")[1].split("\n")[0:5]
        )


@pytest.mark.unit
def test_get_room_description_no_other_players(mock_world):
    """Test room description when player is alone."""
    with patch("mud_server.core.world.database.get_players_in_room", return_value=["testplayer"]):
        desc = mock_world.get_room_description("spawn", "testplayer")

        # Players section should not appear when alone
        assert "[Players here]:" not in desc


@pytest.mark.unit
def test_get_room_description_nonexistent_room(mock_world):
    """Test room description for non-existent room."""
    desc = mock_world.get_room_description("nonexistent", "testplayer")
    assert desc == "Unknown room."


@pytest.mark.unit
def test_get_room_description_no_items(mock_world):
    """Test room description for room without items."""
    with patch("mud_server.core.world.database.get_players_in_room", return_value=[]):
        desc = mock_world.get_room_description("forest", "testplayer")

        # Items section should not appear
        assert "[Items here]:" not in desc
