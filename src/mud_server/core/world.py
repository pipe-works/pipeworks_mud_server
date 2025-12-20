"""World data management and structures."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from mud_server.db import database

# Path to world data file
WORLD_DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "world_data.json"


@dataclass
class Room:
    """Represents a room in the MUD world."""

    id: str
    name: str
    description: str
    exits: Dict[str, str]
    items: List[str]

    def __str__(self) -> str:
        return f"{self.name}\n{self.description}"


@dataclass
class Item:
    """Represents an item in the MUD world."""

    id: str
    name: str
    description: str


class World:
    """Manages the MUD world data."""

    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.items: Dict[str, Item] = {}
        self._load_world()

    def _load_world(self):
        """Load world data from JSON file."""
        with open(WORLD_DATA_PATH, "r") as f:
            data = json.load(f)

        # Load rooms
        for room_id, room_data in data.get("rooms", {}).items():
            self.rooms[room_id] = Room(
                id=room_data["id"],
                name=room_data["name"],
                description=room_data["description"],
                exits=room_data.get("exits", {}),
                items=room_data.get("items", []),
            )

        # Load items
        for item_id, item_data in data.get("items", {}).items():
            self.items[item_id] = Item(
                id=item_data["id"],
                name=item_data["name"],
                description=item_data["description"],
            )

    def get_room(self, room_id: str) -> Optional[Room]:
        """Get a room by ID."""
        return self.rooms.get(room_id)

    def get_item(self, item_id: str) -> Optional[Item]:
        """Get an item by ID."""
        return self.items.get(item_id)

    def get_room_description(self, room_id: str, username: str) -> str:
        """Get a detailed description of a room including items and players."""
        room = self.get_room(room_id)
        if not room:
            return "Unknown room."

        desc = f"\n=== {room.name} ===\n{room.description}\n"

        # List items in room
        if room.items:
            desc += "\n[Items here]:\n"
            for item_id in room.items:
                item = self.get_item(item_id)
                if item:
                    desc += f"  - {item.name}\n"

        # List other players in room
        other_players = [
            p for p in database.get_players_in_room(room_id) if p != username
        ]
        if other_players:
            desc += "\n[Players here]:\n"
            for player in other_players:
                desc += f"  - {player}\n"

        # List exits
        if room.exits:
            desc += "\n[Exits]:\n"
            for direction, destination in room.exits.items():
                desc += f"  - {direction}: {self.get_room(destination).name if self.get_room(destination) else 'Unknown'}\n"

        return desc

    def can_move(self, room_id: str, direction: str) -> Tuple[bool, Optional[str]]:
        """Check if a player can move in a direction and return the destination."""
        room = self.get_room(room_id)
        if not room:
            return False, None

        if direction.lower() not in room.exits:
            return False, None

        destination = room.exits[direction.lower()]
        if not self.get_room(destination):
            return False, None

        return True, destination
