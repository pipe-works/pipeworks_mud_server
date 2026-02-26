"""
World data management and structures.

This module defines the world data structures (rooms and items) and provides
the World class for loading and querying world data. The world is loaded from
JSON files at server startup and kept in memory for fast access.

World Structure:
- Rooms: Named locations with descriptions, exits to other rooms, and items
- Items: Objects that can be found in rooms and picked up by players
- Exits: Directional connections between rooms (north, south, east, west, up, down)
- Zones: Collections of related rooms loaded from separate files

Data Storage (Zone-based - preferred):
- World registry: data/world.json (zone list, global config)
- Zone files: data/zones/<zone_id>.json (rooms and items per zone)

Data Storage (Legacy - fallback):
- Single file: data/world_data.json (all rooms and items)

Design Notes:
- Rooms and items are identified by unique string IDs
- Exits are one-way unless defined in both rooms
- Items in rooms are shared (multiple players can pick up same item)
- Room descriptions are generated dynamically to include current state
- Cross-zone exits use "zone:room" format (e.g., "docks:east_pier")
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from mud_server.db import facade as database

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Base data directory
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"

# Zone-based structure (preferred)
WORLD_JSON_PATH = DATA_DIR / "world.json"
ZONES_DIR = DATA_DIR / "zones"

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


@dataclass
class Zone:
    """
    Represents a zone/region in the MUD world.

    Zones are collections of related rooms loaded from separate JSON files.
    Each zone has its own spawn point and can define zone-specific items.

    Attributes:
        id: Unique identifier for this zone (e.g., "crooked_pipe", "docks")
        name: Human-readable name (e.g., "Crooked Pipe District")
        description: Description of the zone's theme/purpose
        spawn_room: Default room ID for players entering this zone
        rooms: List of room IDs belonging to this zone

    Example:
        Zone(
            id="crooked_pipe",
            name="Crooked Pipe District",
            description="A warren of goblin pubs...",
            spawn_room="spawn",
            rooms=["spawn", "front_parlour", "back_parlour", ...]
        )
    """

    id: str
    name: str
    description: str
    spawn_room: str
    rooms: list[str] = field(default_factory=list)


# ============================================================================
# WORLD MANAGEMENT CLASS
# ============================================================================


class World:
    """
    Manages the MUD world data, providing access to rooms and items.

    This class is instantiated once at server startup and loads all world
    data from JSON files into memory. It supports two loading modes:

    1. Zone-based (preferred): Loads world.json registry + individual zone files
    2. Legacy (fallback): Loads single world_data.json file

    Attributes:
        rooms: Dictionary mapping room IDs to Room objects
        items: Dictionary mapping item IDs to Item objects
        zones: Dictionary mapping zone IDs to Zone objects
        default_spawn: Tuple of (zone_id, room_id) for new player spawn
        world_name: Name of the world (from world.json)

    Design Notes:
        - World data is immutable after loading (read-only)
        - All data kept in memory for fast access
        - No database storage for world data (uses JSON files)
        - Changes to JSON require server restart to take effect
        - Zone-based loading allows modular world building
    """

    def __init__(self, *, world_root: Path | None = None):
        """
        Initialize the World by loading data from JSON files.

        Loads zone-based data (world.json + zones/).

        Args:
            world_root: Optional path to a world package directory. When provided,
                world.json and zones are loaded relative to this directory.

        Raises:
            FileNotFoundError: If no world data files exist
            JSONDecodeError: If JSON files are malformed
            KeyError: If required fields are missing from JSON
        """
        self._world_root = world_root
        if world_root is not None:
            self._world_json_path = world_root / "world.json"
            self._zones_dir = world_root / "zones"
        else:
            self._world_json_path = WORLD_JSON_PATH
            self._zones_dir = ZONES_DIR

        # Initialize empty dictionaries for world data
        self.rooms: dict[str, Room] = {}  # room_id -> Room object
        self.items: dict[str, Item] = {}  # item_id -> Item object
        self.zones: dict[str, Zone] = {}  # zone_id -> Zone object

        # World metadata
        self.world_name: str = "Unknown World"
        self.default_spawn: tuple[str, str] = ("", "spawn")  # (zone_id, room_id)

        # The world_id is the name of the world package directory.
        # When world_root is None (legacy single-file mode) we have no
        # directory-derived ID; the translation layer will be disabled.
        self.world_id: str = world_root.name if world_root is not None else ""

        # Translation layer — initialised to None here; populated by
        # _load_from_zones once it has parsed world.json.
        # The type annotation uses a string forward-reference to avoid a
        # circular import at module level; no runtime import is needed here.
        self._translation_service = None  # type: OOCToICTranslationService | None

        # Load world data from JSON files
        self._load_world()

    def _load_world(self):
        """
        Load world data from zone-based structure.

        Side Effects:
            Populates self.rooms, self.items, self.zones dictionaries
            Sets self.world_name and self.default_spawn
        """
        # Try zone-based loading
        try:
            self._load_from_zones()
            if self.rooms:
                return
        except FileNotFoundError:
            pass  # No zone files

        # If we get here with no rooms, something is wrong
        if not self.rooms:
            logger.warning("No world data loaded - check data/worlds/<world_id>/world.json")

    def _load_from_zones(self):
        """
        Load world data from zone-based file structure.

        Reads world.json for the zone registry and global config,
        then loads each zone file from data/zones/<zone_id>.json.

        File Structure:
            data/world.json - Zone registry and global config
            data/zones/<zone_id>.json - Zone-specific rooms and items

        Side Effects:
            Populates self.rooms, self.items, self.zones dictionaries
            Sets self.world_name and self.default_spawn
        """
        # Load world registry
        with open(self._world_json_path) as f:
            world_data = json.load(f)

        self.world_name = world_data.get("name", "Unknown World")

        # Parse default spawn
        spawn_config = world_data.get("default_spawn", {})
        if isinstance(spawn_config, dict):
            self.default_spawn = (
                spawn_config.get("zone", ""),
                spawn_config.get("room", "spawn"),
            )
        else:
            self.default_spawn = ("", "spawn")

        # Load global items
        for item_id, item_data in world_data.get("global_items", {}).items():
            self.items[item_id] = Item(
                id=item_data["id"],
                name=item_data["name"],
                description=item_data["description"],
            )

        # Load each zone
        zone_ids = world_data.get("zones", [])
        for zone_id in zone_ids:
            zone_path = self._zones_dir / f"{zone_id}.json"
            if zone_path.exists():
                self._load_zone(zone_path)
            else:
                logger.warning(f"Zone file not found: {zone_path}")

        logger.info(
            f"Loaded world '{self.world_name}': "
            f"{len(self.zones)} zones, {len(self.rooms)} rooms, {len(self.items)} items"
        )

        # ── Translation layer ────────────────────────────────────────────────
        # Parse the optional ``translation_layer`` block from world.json.
        # If the block is absent or ``enabled`` is false, the service is
        # left as ``None`` and the layer is inactive for this world.
        #
        # Configuration precedence (locked):
        # 1. If server.ini ``ollama_translation.enabled = false`` → OFF globally.
        #    (Enforced here by checking config before instantiating.)
        # 2. Else if world.json ``translation_layer.enabled = true`` → ON.
        # 3. Otherwise → OFF.
        #
        # FUTURE(server-config): read the server-level master switch from
        # ``mud_server.config.config.ollama_translation.enabled`` (to be
        # added in a follow-up).  For now, only the world-level switch is
        # checked so the layer can be exercised without a config change.
        self._init_translation_service(world_data)

    def _init_translation_service(self, world_data: dict) -> None:
        """Parse the translation_layer block and instantiate the service.

        Called at the end of ``_load_from_zones`` once ``world.json`` is
        fully loaded.  Any errors during service construction are caught and
        logged rather than propagated, so a misconfigured translation block
        never prevents the world from loading.

        Args:
            world_data: The parsed ``world.json`` dict.
        """
        from mud_server.translation.config import TranslationLayerConfig
        from mud_server.translation.service import OOCToICTranslationService

        translation_data = world_data.get("translation_layer", {})

        if not translation_data.get("enabled", False):
            # No block, or explicitly disabled — leave service as None.
            return

        if not self.world_id:
            # Legacy (no world_root) — cannot scope the service to a world_id.
            logger.warning(
                "Translation layer is enabled in world.json but world_id "
                "could not be determined (no world_root).  Skipping."
            )
            return

        if self._world_root is None:
            logger.warning(
                "Translation layer is enabled for world %r but world_root "
                "is None.  Cannot load prompt template.  Skipping.",
                self.world_id,
            )
            return

        try:
            cfg = TranslationLayerConfig.from_dict(
                translation_data, world_root=self._world_root
            )
            self._translation_service = OOCToICTranslationService(
                world_id=self.world_id,
                config=cfg,
                world_root=self._world_root,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to initialise translation layer for world %r: %s.  "
                "Translation will be disabled for this world.",
                self.world_id,
                exc,
            )
            self._translation_service = None

    def get_translation_service(self):
        """Return the OOCToICTranslationService for this world, or None.

        Callers must check for ``None`` before use.  A ``None`` return means
        the translation layer is either disabled in config, failed to
        initialise, or this world has no ``translation_layer`` block.

        Returns:
            OOCToICTranslationService instance, or None.
        """
        return self._translation_service

    def translation_layer_enabled(self) -> bool:
        """Return True if the translation service is configured and active.

        Returns:
            True if a live OOCToICTranslationService is attached; False otherwise.
        """
        return self._translation_service is not None

    def _load_zone(self, zone_path: Path):
        """
        Load a single zone from its JSON file.

        Args:
            zone_path: Path to the zone JSON file

        Side Effects:
            Adds zone to self.zones
            Adds zone's rooms to self.rooms
            Adds zone's items to self.items
        """
        with open(zone_path) as f:
            zone_data = json.load(f)

        zone_id = zone_data["id"]

        rooms_payload = zone_data.get("rooms", {})
        if isinstance(rooms_payload, list):
            rooms_map = {room["id"]: room for room in rooms_payload}
        else:
            rooms_map = rooms_payload

        items_payload = zone_data.get("items", {})
        if isinstance(items_payload, list):
            items_map = {item["id"]: item for item in items_payload}
        else:
            items_map = items_payload

        # Create Zone object
        zone = Zone(
            id=zone_id,
            name=zone_data.get("name", zone_id),
            description=zone_data.get("description", ""),
            spawn_room=zone_data.get("spawn_room", "spawn"),
            rooms=list(rooms_map.keys()),
        )
        self.zones[zone_id] = zone

        # Load zone's rooms
        for room_id, room_data in rooms_map.items():
            self.rooms[room_id] = Room(
                id=room_data["id"],
                name=room_data["name"],
                description=room_data["description"],
                exits=room_data.get("exits", {}),
                items=room_data.get("items", []),
            )

        # Load zone's items
        for item_id, item_data in items_map.items():
            self.items[item_id] = Item(
                id=item_data["id"],
                name=item_data["name"],
                description=item_data["description"],
            )

        logger.debug(f"Loaded zone '{zone_id}': {len(zone.rooms)} rooms")

    def _parse_room_ref(self, room_ref: str) -> tuple[str | None, str]:
        """
        Parse a room reference that may include a zone prefix.

        Room references can be:
        - Simple: "spawn" → (None, "spawn")
        - Cross-zone: "docks:east_pier" → ("docks", "east_pier")

        Args:
            room_ref: Room reference string, optionally with zone prefix

        Returns:
            Tuple of (zone_id, room_id)
            - zone_id is None for same-zone references
            - zone_id is the zone name for cross-zone references
        """
        if ":" in room_ref:
            zone_id, room_id = room_ref.split(":", 1)
            return zone_id, room_id
        return None, room_ref

    def resolve_room(self, room_ref: str) -> Room | None:
        """
        Resolve a room reference to a Room object.

        Handles both simple room IDs and cross-zone references (zone:room).
        Currently all rooms are stored in a flat namespace, so the zone
        prefix is parsed but the room is looked up by ID only.

        Args:
            room_ref: Room reference (e.g., "spawn" or "docks:east_pier")

        Returns:
            Room object if found, None if room doesn't exist

        Example:
            >>> world.resolve_room("spawn")
            Room(id='spawn', ...)
            >>> world.resolve_room("docks:east_pier")
            Room(id='east_pier', ...)  # Looks up 'east_pier' in rooms
        """
        zone_id, room_id = self._parse_room_ref(room_ref)

        # If zone is specified but not loaded, try to load it
        if zone_id and zone_id not in self.zones:
            zone_path = self._zones_dir / f"{zone_id}.json"
            if zone_path.exists():
                logger.info(f"Lazy-loading zone '{zone_id}' for cross-zone exit")
                self._load_zone(zone_path)

        return self.rooms.get(room_id)

    def get_room(self, room_id: str) -> Room | None:
        """
        Retrieve a room by its ID.

        For cross-zone references (zone:room format), use resolve_room() instead.

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

    def get_room_description(self, room_id: str, username: str, *, world_id: str) -> str:
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
        other_players = [
            p for p in database.get_characters_in_room(room_id, world_id=world_id) if p != username
        ]
        if other_players:
            desc += "\n[Players here]:\n"
            for player in other_players:
                desc += f"  - {player}\n"

        # Add exits section with destination room names
        if room.exits:
            desc += "\n[Exits]:\n"
            for direction, destination_ref in room.exits.items():
                # Resolve destination room name (handles cross-zone refs)
                dest_room = self.resolve_room(destination_ref)
                dest_name = dest_room.name if dest_room else "Unknown"
                desc += f"  - {direction}: {dest_name}\n"

        return desc

    def can_move(self, room_id: str, direction: str) -> tuple[bool, str | None]:
        """
        Check if movement in a direction is valid and get the destination.

        Validates that:
        1. The current room exists
        2. The room has an exit in the specified direction
        3. The destination room exists (supports cross-zone exits)

        Cross-zone exits use "zone:room" format (e.g., "docks:east_pier").
        The zone will be lazy-loaded if not already present.

        Args:
            room_id: Current room ID
            direction: Direction to move (e.g., "north", "south", "east", "west")
                      Case-insensitive

        Returns:
            Tuple of (can_move, destination_room_id)
            - (True, "room_id"): Movement is valid, destination is the room ID
            - (False, None): Movement is invalid

        Example:
            >>> world.can_move("spawn", "north")
            (True, "forest_1")
            >>> world.can_move("spawn", "west")
            (False, None)  # No west exit
            >>> world.can_move("pub_entrance", "west")
            (True, "east_pier")  # Cross-zone exit "docks:east_pier" resolves to "east_pier"
        """
        # Check if current room exists
        room = self.get_room(room_id)
        if not room:
            return False, None

        # Check if room has an exit in that direction (case-insensitive)
        if direction.lower() not in room.exits:
            return False, None

        # Get destination reference (may be "room_id" or "zone:room_id")
        destination_ref = room.exits[direction.lower()]

        # Resolve the destination (handles cross-zone refs, lazy-loads zones)
        dest_room = self.resolve_room(destination_ref)
        if not dest_room:
            logger.warning(
                f"Exit '{direction}' from '{room_id}' leads to unknown room: {destination_ref}"
            )
            return False, None

        # Movement is valid - return the actual room ID (not the zone:room ref)
        return True, dest_room.id
