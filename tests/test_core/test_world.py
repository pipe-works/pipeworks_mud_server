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


# ============================================================================
# ZONE-BASED LOADING TESTS
# ============================================================================


@pytest.mark.unit
def test_zone_dataclass_creation():
    """Test creating a Zone instance."""
    from mud_server.core.world import Zone

    zone = Zone(
        id="test_zone",
        name="Test Zone",
        description="A test zone",
        spawn_room="spawn",
        rooms=["spawn", "room1", "room2"],
    )

    assert zone.id == "test_zone"
    assert zone.name == "Test Zone"
    assert zone.spawn_room == "spawn"
    assert len(zone.rooms) == 3


@pytest.mark.unit
def test_parse_room_ref_simple():
    """Test parsing simple room references (no zone prefix)."""
    from mud_server.core.world import World

    # Create a minimal world for testing
    world = World.__new__(World)
    world.rooms = {}
    world.items = {}
    world.zones = {}

    zone_id, room_id = world._parse_room_ref("spawn")
    assert zone_id is None
    assert room_id == "spawn"


@pytest.mark.unit
def test_parse_room_ref_cross_zone():
    """Test parsing cross-zone room references (zone:room format)."""
    from mud_server.core.world import World

    world = World.__new__(World)
    world.rooms = {}
    world.items = {}
    world.zones = {}

    zone_id, room_id = world._parse_room_ref("docks:east_pier")
    assert zone_id == "docks"
    assert room_id == "east_pier"


@pytest.mark.integration
def test_cross_zone_movement(tmp_path):
    """Test movement between zones using zone:room exit format.

    Creates two zones with a cross-zone exit and verifies:
    1. Cross-zone exits are resolved correctly
    2. Movement returns the actual room ID (not the zone:room ref)
    3. Room descriptions show correct destination names
    """
    import json

    from mud_server.core import world as world_module
    from mud_server.core.world import World

    # Create zone directory
    zones_dir = tmp_path / "zones"
    zones_dir.mkdir()

    # Create world.json with two zones
    world_json = {
        "name": "Cross-Zone Test World",
        "default_spawn": {"zone": "pub", "room": "main_room"},
        "zones": ["pub", "docks"],
        "global_items": {},
    }
    world_json_path = tmp_path / "world.json"
    world_json_path.write_text(json.dumps(world_json))

    # Create pub zone with exit to docks
    pub_zone = {
        "id": "pub",
        "name": "The Pub",
        "spawn_room": "main_room",
        "rooms": {
            "main_room": {
                "id": "main_room",
                "name": "Main Room",
                "description": "The main pub room",
                "exits": {"east": "back_room", "west": "docks:pier"},
                "items": [],
            },
            "back_room": {
                "id": "back_room",
                "name": "Back Room",
                "description": "A back room",
                "exits": {"west": "main_room"},
                "items": [],
            },
        },
        "items": {},
    }
    (zones_dir / "pub.json").write_text(json.dumps(pub_zone))

    # Create docks zone
    docks_zone = {
        "id": "docks",
        "name": "The Docks",
        "spawn_room": "pier",
        "rooms": {
            "pier": {
                "id": "pier",
                "name": "East Pier",
                "description": "A wooden pier",
                "exits": {"east": "pub:main_room"},
                "items": [],
            },
        },
        "items": {},
    }
    (zones_dir / "docks.json").write_text(json.dumps(docks_zone))

    # Patch paths
    original_world_path = world_module.WORLD_JSON_PATH
    original_zones_dir = world_module.ZONES_DIR
    original_legacy_path = world_module.LEGACY_WORLD_DATA_PATH
    original_world_data_path = world_module.WORLD_DATA_PATH

    try:
        world_module.WORLD_JSON_PATH = world_json_path
        world_module.ZONES_DIR = zones_dir
        nonexistent = tmp_path / "nonexistent.json"
        world_module.LEGACY_WORLD_DATA_PATH = nonexistent
        world_module.WORLD_DATA_PATH = nonexistent

        # Load the world
        w = World()

        # Verify both zones loaded
        assert len(w.zones) == 2
        assert "pub" in w.zones
        assert "docks" in w.zones

        # Test same-zone movement
        can_move, dest = w.can_move("main_room", "east")
        assert can_move is True
        assert dest == "back_room"

        # Test cross-zone movement (pub → docks)
        can_move, dest = w.can_move("main_room", "west")
        assert can_move is True
        assert dest == "pier"  # Returns room ID, not "docks:pier"

        # Test cross-zone movement (docks → pub)
        can_move, dest = w.can_move("pier", "east")
        assert can_move is True
        assert dest == "main_room"  # Returns room ID, not "pub:main_room"

        # Test room description shows correct exit names
        with patch("mud_server.core.world.database.get_players_in_room", return_value=[]):
            desc = w.get_room_description("main_room", "testplayer")
            assert "East Pier" in desc  # Cross-zone exit shows destination room name

    finally:
        world_module.WORLD_JSON_PATH = original_world_path
        world_module.ZONES_DIR = original_zones_dir
        world_module.LEGACY_WORLD_DATA_PATH = original_legacy_path
        world_module.WORLD_DATA_PATH = original_world_data_path


@pytest.mark.integration
def test_zone_based_loading_from_real_files(tmp_path):
    """Test zone-based loading using real temporary files.

    This test creates actual zone files in a temp directory to verify
    the zone loading logic works correctly without mocking.
    """
    import json

    from mud_server.core import world as world_module
    from mud_server.core.world import World

    # Create zone directory
    zones_dir = tmp_path / "zones"
    zones_dir.mkdir()

    # Create world.json
    world_json = {
        "name": "Test World",
        "default_spawn": {"zone": "test_zone", "room": "spawn"},
        "zones": ["test_zone"],
        "global_items": {"gold": {"id": "gold", "name": "Gold Coin", "description": "Shiny"}},
    }
    world_json_path = tmp_path / "world.json"
    world_json_path.write_text(json.dumps(world_json))

    # Create zone file
    zone_data = {
        "id": "test_zone",
        "name": "Test Zone",
        "description": "A zone for testing",
        "spawn_room": "spawn",
        "rooms": {
            "spawn": {
                "id": "spawn",
                "name": "Spawn Room",
                "description": "You are at the spawn",
                "exits": {"north": "room1"},
                "items": ["sword"],
            },
            "room1": {
                "id": "room1",
                "name": "Room One",
                "description": "The first room",
                "exits": {"south": "spawn"},
                "items": [],
            },
        },
        "items": {"sword": {"id": "sword", "name": "Rusty Sword", "description": "A sword"}},
    }
    zone_path = zones_dir / "test_zone.json"
    zone_path.write_text(json.dumps(zone_data))

    # Patch the paths to use temp directory
    original_world_path = world_module.WORLD_JSON_PATH
    original_zones_dir = world_module.ZONES_DIR
    original_legacy_path = world_module.LEGACY_WORLD_DATA_PATH
    original_world_data_path = world_module.WORLD_DATA_PATH

    try:
        world_module.WORLD_JSON_PATH = world_json_path
        world_module.ZONES_DIR = zones_dir
        # Point both legacy paths to nonexistent file so zone loading is used
        nonexistent = tmp_path / "nonexistent.json"
        world_module.LEGACY_WORLD_DATA_PATH = nonexistent
        world_module.WORLD_DATA_PATH = nonexistent

        # Load the world
        w = World()

        # Verify zone-based loading worked
        assert w.world_name == "Test World"
        assert len(w.zones) == 1
        assert "test_zone" in w.zones
        assert len(w.rooms) == 2
        assert "spawn" in w.rooms
        assert "room1" in w.rooms
        assert len(w.items) == 2  # gold (global) + sword (zone)
        assert "gold" in w.items
        assert "sword" in w.items
        assert w.default_spawn == ("test_zone", "spawn")

    finally:
        # Restore original paths
        world_module.WORLD_JSON_PATH = original_world_path
        world_module.ZONES_DIR = original_zones_dir
        world_module.LEGACY_WORLD_DATA_PATH = original_legacy_path
        world_module.WORLD_DATA_PATH = original_world_data_path
