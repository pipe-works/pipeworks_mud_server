"""
Main game engine with game logic.

This module contains the GameEngine class which implements all core game
mechanics and business logic for the MUD server. It acts as the interface
between the API routes and the underlying world/database systems.

The engine handles:
- Player authentication and sessions
- Movement between rooms
- Inventory management (pickup/drop items)
- Chat systems (say, yell, whisper)
- Room observation and interaction
- Player presence and status

Design Pattern:
    The GameEngine uses the Facade pattern, providing a simplified interface
    to the complex subsystems (World, Database). API routes call engine methods
    which coordinate between the world data and database operations.

Architecture:
    API Routes → GameEngine → World + Database

    - Routes validate sessions and call engine methods
    - Engine implements game logic and coordinates subsystems
    - World provides static game data (rooms, items)
    - Database provides persistent player state
"""

import html

from mud_server.core.bus import MudBus
from mud_server.core.events import Events
from mud_server.core.world import World
from mud_server.db import database


def _get_bus() -> MudBus:
    """
    Get the current event bus singleton.

    This function exists because of Python's module import system. If we imported
    `bus` at module level, tests that call `reset_for_testing()` would orphan that
    reference - the engine would emit to the old bus while tests check the new one.

    By calling `MudBus()` at runtime, we always get the current singleton, even
    after test resets.

    Returns:
        The current MudBus singleton instance
    """
    return MudBus()


def sanitize_chat_message(message: str) -> str:
    """
    Sanitize a chat message to prevent XSS attacks.

    Escapes HTML special characters to prevent injection of malicious
    scripts through chat messages. This is critical for security when
    messages are displayed in web interfaces.

    Args:
        message: Raw message text from user input

    Returns:
        Sanitized message with HTML entities escaped

    Example:
        >>> sanitize_chat_message("Hello <script>alert('xss')</script>")
        "Hello &lt;script&gt;alert('xss')&lt;/script&gt;"
    """
    return html.escape(message)


class GameEngine:
    """
    Main game engine managing all game logic and mechanics.

    This class is instantiated once at server startup and handles all game
    operations. It coordinates between the World (static game data) and the
    Database (dynamic player state) to implement game mechanics.

    Attributes:
        world: World instance containing rooms and items from JSON

    Responsibilities:
        - Player login/logout with authentication
        - Movement validation and execution
        - Inventory operations (pickup, drop, view)
        - Chat message handling (say, yell, whisper)
        - Room descriptions and observation
        - Player status and presence queries

    Design Notes:
        - All methods return (success: bool, message: str) tuples for API responses
        - Database operations are called directly (no repository pattern)
        - Broadcasting to other players is stubbed (not yet implemented)
        - All game state is persisted to database immediately
    """

    def __init__(self):
        """
        Initialize the game engine.

        Loads the world data from JSON and initializes the database schema.
        This is called once when the server starts.

        Side Effects:
            - Loads world_data.json into memory
            - Creates database tables if they don't exist
            - Creates default superuser if no players exist
        """
        # Load world data (rooms and items) from JSON
        self.world = World()

        # Initialize database schema (creates tables, default admin)
        database.init_database()

    def login(
        self, username: str, password: str, session_id: str, client_type: str = "unknown"
    ) -> tuple[bool, str, str | None]:
        """
        Handle account login with authentication and session creation.

        This method validates the account and creates a session, but does not
        select a character. Character selection happens separately.
        """
        if not database.verify_password_for_user(username, password):
            return False, "Invalid username or password.", None

        if not database.is_user_active(username):
            return (
                False,
                "This account has been deactivated. Please contact an administrator.",
                None,
            )

        role = database.get_user_role(username)
        if not role:
            return False, "Failed to retrieve account information.", None

        user_id = database.get_user_id(username)
        if not user_id:
            return False, "Failed to retrieve account information.", None

        if not database.create_session(user_id, session_id, client_type=client_type):
            return False, "Failed to create session.", None

        message = "Login successful. Select a character to enter the world."
        return True, message, role

    def logout(self, username: str) -> bool:
        """
        Handle player logout by removing their session.

        Removes the player's sessions from the database, effectively logging
        them out on all devices.

        Args:
            username: Username of the player logging out

        Returns:
            True if session removed successfully, False otherwise

        Side Effects:
            - Removes session record from database sessions table
            - Player will no longer appear in active players list

        Note:
            This removes all sessions for the user. If you want to remove a
            single session (multi-device support), use database.remove_session_by_id().
        """
        user_id = database.get_user_id(username)
        if not user_id:
            return False
        return database.remove_sessions_for_user(user_id)

    def move(self, username: str, direction: str) -> tuple[bool, str]:
        """
        Handle player movement between rooms.

        Validates the move, updates player location in database, and generates
        appropriate response messages. Also broadcasts movement notifications
        to other players in the affected rooms (currently stubbed).

        Movement Process:
        1. Get player's current room from database
        2. Check if move is valid (exit exists, destination valid)
        3. Update player's room in database
        4. Emit PLAYER_MOVED event (the move is now a fact)
        5. Generate room description for new location
        6. Broadcast departure message to old room
        7. Broadcast arrival message to new room

        Args:
            username: Player attempting to move
            direction: Direction to move ("north", "south", "east", "west")

        Returns:
            Tuple of (success, message)
            - success: True if move succeeded, False otherwise
            - message: New room description OR error message

        Failure Cases:
            - Player not in a valid room
            - No exit in that direction
            - Database update failed

        Events Emitted:
            - PLAYER_MOVED: When movement succeeds
            - PLAYER_MOVE_FAILED: When movement fails

        Example:
            >>> engine.move("player1", "north")
            (True, "You move north.\\n=== Enchanted Forest ===...")
            >>> engine.move("player1", "west")
            (False, "You cannot move west from here.")
        """
        current_room = database.get_character_room(username)
        if not current_room:
            # Emit failure event - player has no valid room
            _get_bus().emit(
                Events.PLAYER_MOVE_FAILED,
                {
                    "username": username,
                    "room": None,
                    "direction": direction,
                    "reason": "Player not in a valid room",
                },
            )
            return False, "You are not in a valid room."

        # Check if current room exists in the world
        if not self.world.get_room(current_room):
            # Emit failure event - room doesn't exist in world data
            _get_bus().emit(
                Events.PLAYER_MOVE_FAILED,
                {
                    "username": username,
                    "room": current_room,
                    "direction": direction,
                    "reason": "Room not in world data",
                },
            )
            return False, "You are not in a valid room."

        can_move, destination = self.world.can_move(current_room, direction)
        if not can_move or destination is None:
            # Emit failure event - no exit in that direction
            _get_bus().emit(
                Events.PLAYER_MOVE_FAILED,
                {
                    "username": username,
                    "room": current_room,
                    "direction": direction,
                    "reason": f"No exit {direction}",
                },
            )
            return False, f"You cannot move {direction} from here."

        # Update player room in database
        if not database.set_character_room(username, destination):
            # Emit failure event - database update failed
            _get_bus().emit(
                Events.PLAYER_MOVE_FAILED,
                {
                    "username": username,
                    "room": current_room,
                    "direction": direction,
                    "reason": "Database update failed",
                },
            )
            return False, "Failed to move."

        # =====================================================================
        # MOVEMENT SUCCEEDED - Emit the event
        # =====================================================================
        # This is the point of no return. The player has moved.
        # The event records this fact for any listeners.
        _get_bus().emit(
            Events.PLAYER_MOVED,
            {
                "username": username,
                "from_room": current_room,
                "to_room": destination,
                "direction": direction,
            },
        )

        # Get room description
        room_desc = self.world.get_room_description(destination, username)
        message = f"You move {direction}.\n{room_desc}"

        # Notify other players (legacy broadcast - will eventually be event-driven)
        self._broadcast_to_room(current_room, f"{username} leaves {direction}.", exclude=username)
        self._broadcast_to_room(
            destination,
            f"{username} arrives from {self._opposite_direction(direction)}.",
            exclude=username,
        )

        return True, message

    def recall(self, username: str) -> tuple[bool, str]:
        """
        Recall player to their current zone's spawn point.

        This is the "hearthstone" equivalent - a way for players to return
        to a known safe location. The destination is the spawn_room defined
        in the player's current zone.

        If the player is not in a known zone, they are sent to the world's
        default spawn point instead.

        Args:
            username: Player recalling

        Returns:
            Tuple of (success, message)
            - success: True if recall succeeded
            - message: Description of new location

        Side Effects:
            - Updates player's current_room in database
            - Broadcasts departure/arrival messages (when implemented)
        """
        current_room = database.get_character_room(username)

        # Find which zone the player is in
        current_zone = None
        for _zone_id, zone in self.world.zones.items():
            if current_room in zone.rooms:
                current_zone = zone
                break

        # Determine destination
        if current_zone:
            destination = current_zone.spawn_room
            zone_name = current_zone.name
        else:
            # Not in a known zone - use world default
            _zone_id, destination = self.world.default_spawn
            zone_name = "the world"

        # Check if already at spawn
        if current_room == destination:
            return True, "You are already at the spawn point."

        # Update player location
        if not database.set_character_room(username, destination):
            return False, "Failed to recall."

        # Broadcast departure (when implemented)
        if current_room:
            self._broadcast_to_room(
                current_room, f"{username} vanishes in a puff of smoke.", exclude=username
            )

        # Broadcast arrival
        self._broadcast_to_room(
            destination, f"{username} appears in a puff of smoke.", exclude=username
        )

        # Generate response
        room_desc = self.world.get_room_description(destination, username)
        message = f"You recall to {zone_name}'s spawn point.\n{room_desc}"

        return True, message

    def chat(self, username: str, message: str) -> tuple[bool, str]:
        """
        Handle player chat messages within their current room.

        Sends a chat message to all players in the same room. The message is
        stored in the database and can be retrieved by other players in the room.

        Args:
            username: Player sending the message
            message: Chat message text

        Returns:
            Tuple of (success, message)
            - success: True if message sent, False otherwise
            - message: Confirmation message OR error message

        Failure Cases:
            - Player not in a valid room
            - Database insert failed

        Side Effects:
            - Adds message to chat_messages table with room association
            - Message will appear in other players' chat history

        Example:
            >>> engine.chat("player1", "Hello everyone!")
            (True, "You say: Hello everyone!")

        Security Note:
            Messages are sanitized to prevent XSS attacks before storage.
        """
        room = database.get_character_room(username)
        if not room:
            return False, "You are not in a valid room."

        # Sanitize message to prevent XSS attacks
        safe_message = sanitize_chat_message(message)

        if not database.add_chat_message(username, safe_message, room):
            return False, "Failed to send message."

        return True, f"You say: {safe_message}"

    def yell(self, username: str, message: str) -> tuple[bool, str]:
        """
        Yell a message to current room and all adjoining rooms.

        Unlike regular chat which only reaches the current room, yell sends
        the message to:
        1. The player's current room
        2. All rooms directly connected via exits

        The message is prefixed with [YELL] to distinguish it from normal chat.

        Args:
            username: Player yelling the message
            message: Message text to yell

        Returns:
            Tuple of (success, message)
            - success: True if yell sent, False otherwise
            - message: Confirmation message OR error message

        Failure Cases:
            - Player not in a valid room
            - Room data invalid
            - Database insert failed

        Side Effects:
            - Adds [YELL] message to current room's chat
            - Adds [YELL] message to all adjoining rooms' chat
            - Players in multiple affected rooms will see the message

        Example:
            If player in "spawn" with exits to "forest" and "desert":
            >>> engine.yell("player1", "Can anyone hear me?")
            (True, "You yell: Can anyone hear me?")
            # Message appears in spawn, forest, and desert rooms

        Security Note:
            Messages are sanitized to prevent XSS attacks before storage.
        """
        current_room_id = database.get_character_room(username)
        if not current_room_id:
            return False, "You are not in a valid room."

        # Get current room to find adjoining rooms
        current_room = self.world.get_room(current_room_id)
        if not current_room:
            return False, "Invalid room."

        # Sanitize message to prevent XSS attacks
        safe_message = sanitize_chat_message(message)

        # Add [YELL] prefix to sanitized message
        yell_message = f"[YELL] {safe_message}"

        # Send to current room
        if not database.add_chat_message(username, yell_message, current_room_id):
            return False, "Failed to send message."

        # Send to all adjoining rooms
        for _direction, room_id in current_room.exits.items():
            database.add_chat_message(username, yell_message, room_id)

        return True, f"You yell: {safe_message}"

    def whisper(self, username: str, target: str, message: str) -> tuple[bool, str]:
        """
        Send a private whisper to a specific player in the same room.

        Whispers are private messages that only the sender and recipient can see.
        They are filtered by recipient when retrieving room chat messages.

        Validation Checks:
        1. Sender must be in a valid room
        2. Target player must exist in database
        3. Target must be online (have an active session)
        4. Target must be in the same room as sender

        The message is prefixed with [WHISPER: sender → target] to clearly
        indicate it's a private message and show the direction.

        Args:
            username: Player sending the whisper
            target: Username of player to whisper to (case-sensitive!)
            message: Private message text

        Returns:
            Tuple of (success, message)
            - success: True if whisper sent, False otherwise
            - message: Confirmation message OR error message explaining failure

        Failure Cases:
            - Sender not in a valid room
            - Target player doesn't exist
            - Target player is not online
            - Target player is in a different room
            - Database insert failed

        Side Effects:
            - Adds message to chat_messages with recipient field set
            - Only sender and target can see this message in their chat
            - Extensive logging for debugging whisper issues

        Security Note:
            Target username is case-sensitive. Command parser preserves case
            for arguments to ensure usernames like "Mendit" work correctly.

        Example:
            >>> engine.whisper("player1", "Admin", "Help me please")
            (True, "You whisper to Admin: Help me please")
            # Only player1 and Admin see: [WHISPER: player1 → Admin] Help me please

            >>> engine.whisper("player1", "Player2", "Hi")
            (False, "Player 'Player2' is not in this room.")
        """
        import logging

        logger = logging.getLogger(__name__)

        sender_room = database.get_character_room(username)
        logger.info(f"Whisper: {username} in room {sender_room} attempting to whisper to {target}")

        if not sender_room:
            logger.warning(f"Whisper failed: {username} not in valid room")
            return False, "You are not in a valid room."

        # Check if target player exists
        if not database.character_exists(target):
            logger.warning(f"Whisper failed: target {target} does not exist")
            return False, f"Player '{target}' does not exist."

        # Check if target is online (has an active session)
        active_players = database.get_active_characters()
        logger.info(f"Active players: {active_players}")
        if target not in active_players:
            logger.warning(f"Whisper failed: target {target} not online")
            return False, f"Player '{target}' is not online."

        # Check if target is in the same room
        target_room = database.get_character_room(target)
        logger.info(f"Target {target} is in room {target_room}")
        if target_room != sender_room:
            logger.warning(f"Whisper failed: {target} in {target_room}, sender in {sender_room}")
            return False, f"Player '{target}' is not in this room."

        # Sanitize message to prevent XSS attacks
        safe_message = sanitize_chat_message(message)

        # Add whisper message with recipient (include both sender and target for clarity)
        whisper_message = f"[WHISPER: {username} → {target}] {safe_message}"
        result = database.add_chat_message(username, whisper_message, sender_room, recipient=target)
        logger.info(f"Whisper message save result: {result}")

        if not result:
            logger.error("Failed to save whisper to database")
            return False, "Failed to send whisper."

        logger.info(f"Whisper successful: {username} -> {target}: {safe_message}")
        return True, f"You whisper to {target}: {safe_message}"

    def get_room_chat(self, username: str, limit: int = 20) -> str:
        """
        Get recent chat messages from the player's current room.

        Retrieves and formats chat messages, including regular chat, yells,
        and whispers. Whispers are filtered so each player only sees:
        - Public messages (no recipient)
        - Whispers sent by them
        - Whispers sent to them

        Args:
            username: Player requesting chat history
            limit: Maximum number of messages to retrieve (default 20)

        Returns:
            Formatted string with recent messages
            Format: "[Recent messages]:\nusername: message\n..."
            Returns "[No messages in this room yet]" if empty
            Returns "No messages." if player not in valid room

        Example:
            >>> engine.get_room_chat("player1", limit=5)
            '''[Recent messages]:
            player2: Hello!
            player1: [WHISPER: player1 → player2] Hi there
            player3: [YELL] Can anyone help?
            '''
        """
        room = database.get_character_room(username)
        if not room:
            return "No messages."

        messages = database.get_room_messages(room, limit=limit, username=username)
        if not messages:
            return "[No messages in this room yet]"

        chat_text = "[Recent messages]:\n"
        for msg in messages:
            chat_text += f"{msg['username']}: {msg['message']}\n"
        return chat_text

    def get_inventory(self, username: str) -> str:
        """
        Get formatted player inventory listing.

        Retrieves the player's inventory from the database and formats it
        as a readable list with item names.

        Args:
            username: Player whose inventory to retrieve

        Returns:
            Formatted inventory string
            - "Your inventory:\n  - Item1\n  - Item2..." if items present
            - "Your inventory is empty." if no items

        Example:
            >>> engine.get_inventory("player1")
            "Your inventory:\n  - Torch\n  - Rope\n"
            >>> engine.get_inventory("new_player")
            "Your inventory is empty."
        """
        inventory = database.get_character_inventory(username)
        if not inventory:
            return "Your inventory is empty."

        inv_text = "Your inventory:\n"
        for item_id in inventory:
            item = self.world.get_item(item_id)
            if item:
                inv_text += f"  - {item.name}\n"
        return inv_text

    def pickup_item(self, username: str, item_name: str) -> tuple[bool, str]:
        """
        Pick up an item from the current room and add to inventory.

        Searches for an item with matching name (case-insensitive) in the
        current room. If found, adds it to the player's inventory.

        Design Note:
            Items are NOT removed from the room when picked up. This allows
            multiple players to pick up the same item. This is intentional
            for the current proof-of-concept design.

        Args:
            username: Player picking up the item
            item_name: Name of item to pick up (case-insensitive match)

        Returns:
            Tuple of (success, message)
            - success: True if item picked up, False otherwise
            - message: Success confirmation OR error message

        Failure Cases:
            - Player not in a valid room
            - Room doesn't exist in world data
            - No item with that name in the room

        Example:
            >>> engine.pickup_item("player1", "torch")
            (True, "You picked up the Torch.")
            >>> engine.pickup_item("player1", "sword")
            (False, "There is no 'sword' here.")
        """
        room_id = database.get_character_room(username)
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
        inventory = database.get_character_inventory(username)
        if matching_item not in inventory:
            inventory.append(matching_item)
            database.set_character_inventory(username, inventory)

        item = self.world.get_item(matching_item)
        item_name_display = item.name if item else matching_item
        return True, f"You picked up the {item_name_display}."

    def drop_item(self, username: str, item_name: str) -> tuple[bool, str]:
        """
        Drop an item from player's inventory.

        Searches inventory for an item with matching name (case-insensitive)
        and removes it from the player's inventory.

        Design Note:
            Dropped items are NOT added back to the room. They simply disappear
            from the player's inventory. This is intentional for the current
            proof-of-concept design.

        Args:
            username: Player dropping the item
            item_name: Name of item to drop (case-insensitive match)

        Returns:
            Tuple of (success, message)
            - success: True if item dropped, False otherwise
            - message: Success confirmation OR error message

        Failure Cases:
            - Player doesn't have an item with that name

        Example:
            >>> engine.drop_item("player1", "torch")
            (True, "You dropped the Torch.")
            >>> engine.drop_item("player1", "sword")
            (False, "You don't have a 'sword'.")
        """
        inventory = database.get_character_inventory(username)

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
        database.set_character_inventory(username, inventory)

        item = self.world.get_item(matching_item)
        item_name_display = item.name if item else matching_item
        return True, f"You dropped the {item_name_display}."

    def look(self, username: str) -> str:
        """
        Look around the current room to get a full description.

        Generates a detailed description of the player's current room including
        room name, description, items, other players, and available exits.

        Args:
            username: Player looking around

        Returns:
            Formatted room description string
            Returns "You are not in a valid room." if player location invalid

        Example:
            >>> engine.look("player1")
            '''
            === Spawn Zone ===
            You stand in a peaceful plaza...

            [Items here]:
              - Torch
              - Rope

            [Players here]:
              - player2

            [Exits]:
              - north: Enchanted Forest
              - south: Golden Desert
            '''
        """
        room_id = database.get_character_room(username)
        if not room_id:
            return "You are not in a valid room."

        # Check if room exists in the world
        if not self.world.get_room(room_id):
            return "You are not in a valid room."

        return self.world.get_room_description(room_id, username)

    def get_active_players(self) -> list[str]:
        """
        Get list of all currently active (logged in) characters.

        Queries the database sessions table to get all characters with active
        sessions. These are characters currently logged into the server.

        Returns:
            List of character names for all active players

        Example:
            >>> engine.get_active_players()
            ['player1', 'Admin', 'Mendit']
        """
        return database.get_active_characters()

    def _broadcast_to_room(self, room_id: str, message: str, exclude: str | None = None):
        """
        Broadcast a message to all players in a room.

        This method is currently a stub and doesn't actually send messages.
        Real implementation would require:
        - WebSocket connections or message queue system
        - Per-player message buffers
        - Push notification mechanism

        When implemented, this would be called by move() to notify other
        players when someone enters or leaves a room.

        Args:
            room_id: Room to broadcast to
            message: Message to send
            exclude: Optional username to exclude from broadcast (usually sender)

        Current Status:
            Not implemented - movement notifications not sent to other players
        """
        # This would be handled by the server's message queue
        # TODO: Implement real-time message broadcasting
        pass

    @staticmethod
    def _opposite_direction(direction: str) -> str:
        """
        Get the opposite direction for movement notifications.

        Used when broadcasting arrival messages. If a player moves north,
        players in the destination room see them arrive from the south.

        Args:
            direction: Direction of movement (north, south, east, west)

        Returns:
            Opposite direction string
            Returns "somewhere" for unrecognized directions

        Example:
            >>> engine._opposite_direction("north")
            "south"
            >>> engine._opposite_direction("east")
            "west"
            >>> engine._opposite_direction("up")
            "down"
        """
        opposites = {
            "north": "south",
            "south": "north",
            "east": "west",
            "west": "east",
            "up": "down",
            "down": "up",
        }
        return opposites.get(direction.lower(), "somewhere")
