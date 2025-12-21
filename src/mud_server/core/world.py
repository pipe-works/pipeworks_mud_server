"""
World data management and structures.

This module defines the world data structures (rooms and items) and provides
the World class for loading and querying world data. The world is loaded from
a JSON file at server startup and kept in memory for fast access.

World Structure:
- Rooms: Named locations with descriptions, exits to other rooms, and items
- Items: Objects that can be found in rooms and picked up by players
- Exits: Directional connections between rooms (north, south, east, west)

Data Storage:
- World data is stored in data/world_data.json
- Loaded once at server startup into memory
- Read-only during gameplay (modifications not persisted)
- Changes to JSON require server restart to take effect

Design Notes:
- Rooms and items are identified by unique string IDs
- Exits are one-way unless defined in both rooms
- Items in rooms are shared (multiple players can pick up same item)
- Room descriptions are generated dynamically to include current state
"""

import json
from dataclasses import dataclass
from pathlib import Path

from mud_server.db import database

# ============================================================================
# CONFIGURATION
# ============================================================================

# Path to the world data JSON file
# Navigates from this file up to project root, then into data/ directory
# Structure: src/mud_server/core/world.py -> ../../../../data/world_data.json
WORLD_DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "world_data.json"


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class Room:
    """
    Represents a room/location in the MUD world.

    Rooms are the fundamental spatial unit of the game world. Players move
    between rooms using directional exits. Each room can contain items and
    multiple players.

    Attributes:
        id: Unique identifier for this room (e.g., "spawn", "forest_1")
        name: Human-readable name displayed to players (e.g., "Spawn Zone")
        description: Detailed description of the room's appearance
        exits: Dictionary mapping directions to destination room IDs
               Format: {"north": "forest_1", "south": "desert_1"}
        items: List of item IDs currently in this room

    Example:
        Room(
            id="spawn",
            name="Spawn Zone",
            description="You stand in a peaceful plaza...",
            exits={"north": "forest_1", "south": "desert_1"},
            items=["torch", "rope"]
        )
    """

    id: str
    name: str
    description: str
    exits: dict[str, str]  # direction -> destination room_id
    items: list[str]  # List of item IDs

    def __str__(self) -> str:
        """
        String representation showing room name and description.

        Returns:
            Formatted string with name and description
        """
        return f"{self.name}\n{self.description}"


@dataclass
class Item:
    """
    Represents an item/object in the MUD world.

    Items can be found in rooms and picked up by players. They are stored
    in player inventories and can be dropped back into rooms.

    Attributes:
        id: Unique identifier for this item (e.g., "torch", "sword_1")
        name: Human-readable name displayed to players (e.g., "Rusty Torch")
        description: Detailed description of the item's appearance

    Example:
        Item(
            id="torch",
            name="Rusty Torch",
            description="A flickering torch that barely lights the way."
        )

    Note:
        Items currently have no gameplay mechanics (no stats, durability, etc.)
        They are purely for inventory and flavor. Future enhancements could
        add item types, usability, combat stats, etc.
    """

    id: str
    name: str
    description: str


# ============================================================================
# WORLD MANAGEMENT CLASS
# ============================================================================


class World:
    """
    Manages the MUD world data, providing access to rooms and items.

    This class is instantiated once at server startup and loads all world
    data from the JSON file into memory. It provides methods to query rooms,
    items, and generate room descriptions.

    Attributes:
        rooms: Dictionary mapping room IDs to Room objects
        items: Dictionary mapping item IDs to Item objects

    Design Notes:
        - World data is immutable after loading (read-only)
        - All data kept in memory for fast access
        - No database storage for world data (uses JSON file)
        - Changes to JSON require server restart to take effect
    """

    def __init__(self):
        """
        Initialize the World by loading data from JSON file.

        Automatically calls _load_world() to populate rooms and items
        dictionaries from the world_data.json file.

        Raises:
            FileNotFoundError: If world_data.json doesn't exist
            JSONDecodeError: If world_data.json is malformed
            KeyError: If required fields are missing from JSON
        """
        # Initialize empty dictionaries for world data
        self.rooms: dict[str, Room] = {}  # room_id -> Room object
        self.items: dict[str, Item] = {}  # item_id -> Item object

        # Load world data from JSON file
        self._load_world()

    def _load_world(self):
        """
        Load world data from JSON file into memory.

        Reads the world_data.json file and parses it into Room and Item objects.
        This is called once during World initialization.

        JSON Structure Expected:
            {
                "rooms": {
                    "room_id": {
                        "id": "room_id",
                        "name": "Room Name",
                        "description": "Room description",
                        "exits": {"north": "other_room_id"},
                        "items": ["item_id"]
                    }
                },
                "items": {
                    "item_id": {
                        "id": "item_id",
                        "name": "Item Name",
                        "description": "Item description"
                    }
                }
            }

        Side Effects:
            Populates self.rooms and self.items dictionaries

        Raises:
            FileNotFoundError: If WORLD_DATA_PATH doesn't exist
            JSONDecodeError: If JSON is malformed
            KeyError: If required fields are missing
        """
        # Read and parse JSON file
        with open(WORLD_DATA_PATH) as f:
            data = json.load(f)

        # Load all rooms from JSON
        for room_id, room_data in data.get("rooms", {}).items():
            self.rooms[room_id] = Room(
                id=room_data["id"],
                name=room_data["name"],
                description=room_data["description"],
                exits=room_data.get("exits", {}),  # Default to no exits
                items=room_data.get("items", []),  # Default to no items
            )

        # Load all items from JSON
        for item_id, item_data in data.get("items", {}).items():
            self.items[item_id] = Item(
                id=item_data["id"],
                name=item_data["name"],
                description=item_data["description"],
            )

    def get_room(self, room_id: str) -> Room | None:
        """
        Retrieve a room by its ID.

        Args:
            room_id: Unique room identifier (e.g., "spawn", "forest_1")

        Returns:
            Room object if found, None if room doesn't exist

        Example:
            >>> world.get_room("spawn")
            Room(id='spawn', name='Spawn Zone', ...)
            >>> world.get_room("nonexistent")
            None
        """
        return self.rooms.get(room_id)

    def get_item(self, item_id: str) -> Item | None:
        """
        Retrieve an item by its ID.

        Args:
            item_id: Unique item identifier (e.g., "torch", "sword_1")

        Returns:
            Item object if found, None if item doesn't exist

        Example:
            >>> world.get_item("torch")
            Item(id='torch', name='Rusty Torch', ...)
            >>> world.get_item("nonexistent")
            None
        """
        return self.items.get(item_id)

    def get_room_description(self, room_id: str, username: str) -> str:
        """
        Generate a detailed, formatted description of a room.

        Creates a comprehensive room description including:
        - Room name and description
        - Items present in the room
        - Other players in the room (excluding the requesting player)
        - Available exits with destination names

        Args:
            room_id: ID of the room to describe
            username: Username of the player requesting description
                     (excluded from the player list)

        Returns:
            Formatted multi-line string with complete room information
            Returns "Unknown room." if room_id doesn't exist

        Format:
            === Room Name ===
            Room description text here.

            [Items here]:
              - Item Name 1
              - Item Name 2

            [Players here]:
              - Player1
              - Player2

            [Exits]:
              - north: Destination Room Name
              - south: Another Room Name

        Example:
            >>> world.get_room_description("spawn", "player1")
            '''
            === Spawn Zone ===
            You stand in a peaceful plaza...

            [Items here]:
              - Torch
              - Rope

            [Players here]:
              - player2
              - admin

            [Exits]:
              - north: Enchanted Forest
              - south: Golden Desert
            '''
        """
        # Look up the room
        room = self.get_room(room_id)
        if not room:
            return "Unknown room."

        # Start with room name and description
        desc = f"\n=== {room.name} ===\n{room.description}\n"

        # Add items section if any items are present
        if room.items:
            desc += "\n[Items here]:\n"
            for item_id in room.items:
                item = self.get_item(item_id)
                if item:  # Only show if item exists in items dict
                    desc += f"  - {item.name}\n"

        # Add players section (query database for active players in this room)
        # Exclude the requesting player from the list
        other_players = [p for p in database.get_players_in_room(room_id) if p != username]
        if other_players:
            desc += "\n[Players here]:\n"
            for player in other_players:
                desc += f"  - {player}\n"

        # Add exits section with destination room names
        if room.exits:
            desc += "\n[Exits]:\n"
            for direction, destination in room.exits.items():
                # Resolve destination room name
                dest_room = self.get_room(destination)
                dest_name = dest_room.name if dest_room else "Unknown"
                desc += f"  - {direction}: {dest_name}\n"

        return desc

    def can_move(self, room_id: str, direction: str) -> tuple[bool, str | None]:
        """
        Check if movement in a direction is valid and get the destination.

        Validates that:
        1. The current room exists
        2. The room has an exit in the specified direction
        3. The destination room exists

        Args:
            room_id: Current room ID
            direction: Direction to move (e.g., "north", "south", "east", "west")
                      Case-insensitive

        Returns:
            Tuple of (can_move, destination_room_id)
            - (True, "room_id"): Movement is valid, destination is "room_id"
            - (False, None): Movement is invalid

        Example:
            >>> world.can_move("spawn", "north")
            (True, "forest_1")
            >>> world.can_move("spawn", "west")
            (False, None)  # No west exit
            >>> world.can_move("invalid_room", "north")
            (False, None)  # Room doesn't exist
        """
        # Check if current room exists
        room = self.get_room(room_id)
        if not room:
            return False, None

        # Check if room has an exit in that direction (case-insensitive)
        if direction.lower() not in room.exits:
            return False, None

        # Get destination room ID
        destination = room.exits[direction.lower()]

        # Verify destination room exists
        if not self.get_room(destination):
            return False, None

        # Movement is valid
        return True, destination
