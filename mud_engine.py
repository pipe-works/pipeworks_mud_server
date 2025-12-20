"""MUD game engine with world and player logic."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import database

WORLD_DATA_PATH = Path(__file__).parent / "world_data.json"


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


class GameEngine:
    """Main game engine managing game logic."""

    def __init__(self):
        self.world = World()
        database.init_database()

    def login(self, username: str, session_id: str) -> Tuple[bool, str]:
        """Handle player login."""
        # Create player if doesn't exist
        if not database.player_exists(username):
            if not database.create_player(username):
                return False, "Failed to create player account."

        # Create session
        if not database.create_session(username, session_id):
            return False, "Failed to create session."

        room = database.get_player_room(username)
        if not room:
            room = "spawn"
            database.set_player_room(username, room)

        message = f"Welcome, {username}!\n"
        message += self.world.get_room_description(room, username)
        return True, message

    def logout(self, username: str) -> bool:
        """Handle player logout."""
        return database.remove_session(username)

    def move(self, username: str, direction: str) -> Tuple[bool, str]:
        """Handle player movement."""
        current_room = database.get_player_room(username)
        if not current_room:
            return False, "You are not in a valid room."

        can_move, destination = self.world.can_move(current_room, direction)
        if not can_move:
            return False, f"You cannot move {direction} from here."

        # Update player room
        if not database.set_player_room(username, destination):
            return False, "Failed to move."

        # Get room description
        room_desc = self.world.get_room_description(destination, username)
        message = f"You move {direction}.\n{room_desc}"

        # Notify other players
        self._broadcast_to_room(
            current_room, f"{username} leaves {direction}.", exclude=username
        )
        self._broadcast_to_room(
            destination, f"{username} arrives from {self._opposite_direction(direction)}.", exclude=username
        )

        return True, message

    def chat(self, username: str, message: str) -> Tuple[bool, str]:
        """Handle player chat."""
        room = database.get_player_room(username)
        if not room:
            return False, "You are not in a valid room."

        if not database.add_chat_message(username, message, room):
            return False, "Failed to send message."

        return True, f"You say: {message}"

    def get_room_chat(self, username: str, limit: int = 20) -> str:
        """Get recent chat from current room."""
        room = database.get_player_room(username)
        if not room:
            return "No messages."

        messages = database.get_room_messages(room, limit)
        if not messages:
            return "[No messages in this room yet]"

        chat_text = "[Recent messages]:\n"
        for msg in messages:
            chat_text += f"{msg['username']}: {msg['message']}\n"
        return chat_text

    def get_inventory(self, username: str) -> str:
        """Get player inventory."""
        inventory = database.get_player_inventory(username)
        if not inventory:
            return "Your inventory is empty."

        inv_text = "Your inventory:\n"
        for item_id in inventory:
            item = self.world.get_item(item_id)
            if item:
                inv_text += f"  - {item.name}\n"
        return inv_text

    def pickup_item(self, username: str, item_name: str) -> Tuple[bool, str]:
        """Pick up an item from the current room."""
        room_id = database.get_player_room(username)
        if not room_id:
            return False, "You are not in a valid room."

        room = self.world.get_room(room_id)
        if not room:
            return False, "Invalid room."

        # Find matching item
        matching_item = None
        for item_id in room.items:
            item = self.world.get_item(item_id)
            if item and item.name.lower() == item_name.lower():
                matching_item = item_id
                break

        if not matching_item:
            return False, f"There is no '{item_name}' here."

        # Add to inventory
        inventory = database.get_player_inventory(username)
        if matching_item not in inventory:
            inventory.append(matching_item)
            database.set_player_inventory(username, inventory)

        item = self.world.get_item(matching_item)
        return True, f"You picked up the {item.name}."

    def drop_item(self, username: str, item_name: str) -> Tuple[bool, str]:
        """Drop an item from inventory."""
        inventory = database.get_player_inventory(username)

        # Find matching item in inventory
        matching_item = None
        for item_id in inventory:
            item = self.world.get_item(item_id)
            if item and item.name.lower() == item_name.lower():
                matching_item = item_id
                break

        if not matching_item:
            return False, f"You don't have a '{item_name}'."

        # Remove from inventory
        inventory.remove(matching_item)
        database.set_player_inventory(username, inventory)

        item = self.world.get_item(matching_item)
        return True, f"You dropped the {item.name}."

    def look(self, username: str) -> str:
        """Look around the current room."""
        room_id = database.get_player_room(username)
        if not room_id:
            return "You are not in a valid room."

        return self.world.get_room_description(room_id, username)

    def get_active_players(self) -> List[str]:
        """Get list of active players."""
        return database.get_active_players()

    def _broadcast_to_room(
        self, room_id: str, message: str, exclude: Optional[str] = None
    ):
        """Broadcast a message to all players in a room."""
        # This would be handled by the server's message queue
        pass

    @staticmethod
    def _opposite_direction(direction: str) -> str:
        """Get the opposite direction."""
        opposites = {"north": "south", "south": "north", "east": "west", "west": "east"}
        return opposites.get(direction.lower(), "somewhere")


if __name__ == "__main__":
    engine = GameEngine()
    print("MUD Engine initialized successfully!")
