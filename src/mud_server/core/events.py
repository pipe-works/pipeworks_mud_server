"""
Event Type Constants for the MUD Server

This module defines all standard event types used in the MUD server.
Using constants instead of string literals provides:

1. Autocomplete support in IDEs
2. Typo prevention (undefined constant = error)
3. Single source of truth for event names
4. Easy refactoring if event names change

=============================================================================
NAMING CONVENTION
=============================================================================

Events use "domain:action" format in PAST TENSE:

    Good: "player:moved", "item:picked_up", "chat:sent"
    Bad:  "player:move", "pick_up_item", "send_chat"

The past tense emphasizes that events record FACTS about what HAPPENED,
not requests for something to happen.

Exception: "tick" doesn't use past tense because it's a continuous concept.

=============================================================================
USAGE
=============================================================================

    from mud_server.core.events import Events
    from mud_server.core.bus import bus

    # Emit using constants
    bus.emit(Events.PLAYER_MOVED, {"username": "Gribnak", ...})

    # Subscribe using constants
    bus.on(Events.PLAYER_MOVED, handle_player_move)

=============================================================================
"""


class Events:
    """
    All standard event types in the MUD server.

    These are class attributes (not instance attributes) because event
    types are global constants, not per-instance values.

    Organized by domain for easy navigation.
    """

    # =========================================================================
    # SERVER LIFECYCLE
    # =========================================================================
    # Events related to server startup, shutdown, and health

    SERVER_STARTED = "server:started"
    """
    Emitted once when the server has finished initialization and is ready
    to accept connections.

    Detail: {}
    """

    SERVER_STOPPING = "server:stopping"
    """
    Emitted when the server begins shutdown sequence.

    Detail: {"reason": str}  # Why the server is stopping
    """

    SERVER_STOPPED = "server:stopped"
    """
    Emitted after the server has completed shutdown.

    Detail: {}
    """

    # =========================================================================
    # TICK (GAME LOOP)
    # =========================================================================
    # The heartbeat of the living world

    TICK = "tick"
    """
    Emitted every game tick (typically once per second).
    Drives time-based systems: weather, NPC AI, cooldowns, etc.

    Detail: {
        "delta": float,  # Seconds since last tick (usually 1.0)
        "tick_number": int  # Monotonic tick counter
    }
    """

    # =========================================================================
    # PLAYER LIFECYCLE
    # =========================================================================
    # Events about player accounts and sessions

    PLAYER_CREATED = "player:created"
    """
    Emitted when a new player account is created (registration).

    Detail: {
        "username": str,
        "role": str  # "player", "worldbuilder", "admin", "superuser"
    }
    """

    PLAYER_LOGGED_IN = "player:logged_in"
    """
    Emitted when a player successfully logs in.

    Detail: {
        "username": str,
        "session_id": str,
        "room": str,  # The room they logged into
        "role": str
    }
    """

    PLAYER_LOGGED_OUT = "player:logged_out"
    """
    Emitted when a player logs out (voluntarily or session expired).

    Detail: {
        "username": str,
        "room": str,  # The room they were in
        "reason": str  # "voluntary", "timeout", "kicked"
    }
    """

    # =========================================================================
    # PLAYER MOVEMENT
    # =========================================================================
    # Events about players moving between rooms

    PLAYER_MOVED = "player:moved"
    """
    Emitted when a player successfully moves to a new room.

    Detail: {
        "username": str,
        "from_room": str,
        "to_room": str,
        "direction": str  # "north", "south", "east", "west"
    }
    """

    PLAYER_MOVE_FAILED = "player:move_failed"
    """
    Emitted when a player's movement attempt fails.

    Detail: {
        "username": str,
        "room": str,  # Current room (didn't change)
        "direction": str,  # Attempted direction
        "reason": str  # Why it failed
    }
    """

    # =========================================================================
    # ROOM EVENTS
    # =========================================================================
    # Events about room state and descriptions

    ROOM_ENTERED = "room:entered"
    """
    Emitted when a player enters a room (from any source).
    Includes login, movement, teleport, etc.

    Detail: {
        "username": str,
        "room": str,
        "source": str  # "login", "movement", "teleport"
    }
    """

    ROOM_EXITED = "room:exited"
    """
    Emitted when a player exits a room.

    Detail: {
        "username": str,
        "room": str,
        "destination": str,  # Where they went (or "logout")
        "direction": str | None  # Direction if movement, None otherwise
    }
    """

    ROOM_DESCRIBED = "room:described"
    """
    Emitted when a room description is generated (for 'look' command).
    Plugins can react by emitting additional description events.

    Detail: {
        "username": str,  # Who requested the description
        "room": str,
        "description": str  # The base description
    }
    """

    # =========================================================================
    # INVENTORY EVENTS
    # =========================================================================
    # Events about items being picked up, dropped, used

    ITEM_PICKED_UP = "item:picked_up"
    """
    Emitted when a player picks up an item.

    Detail: {
        "username": str,
        "item_id": str,
        "item_name": str,
        "room": str  # Where they picked it up
    }
    """

    ITEM_PICKUP_FAILED = "item:pickup_failed"
    """
    Emitted when a player fails to pick up an item.

    Detail: {
        "username": str,
        "item_name": str,  # What they tried to pick up
        "room": str,
        "reason": str  # Why it failed
    }
    """

    ITEM_DROPPED = "item:dropped"
    """
    Emitted when a player drops an item.

    Detail: {
        "username": str,
        "item_id": str,
        "item_name": str,
        "room": str  # Where they dropped it
    }
    """

    ITEM_DROP_FAILED = "item:drop_failed"
    """
    Emitted when a player fails to drop an item.

    Detail: {
        "username": str,
        "item_name": str,
        "reason": str
    }
    """

    # =========================================================================
    # CHAT EVENTS
    # =========================================================================
    # Events about communication between players

    CHAT_SAID = "chat:said"
    """
    Emitted when a player says something in their current room.

    Detail: {
        "username": str,
        "message": str,  # The sanitized message
        "room": str
    }
    """

    CHAT_YELLED = "chat:yelled"
    """
    Emitted when a player yells (reaches adjacent rooms).

    Detail: {
        "username": str,
        "message": str,
        "origin_room": str,
        "rooms_reached": list[str]  # All rooms that heard it
    }
    """

    CHAT_WHISPERED = "chat:whispered"
    """
    Emitted when a player whispers to another player.

    Detail: {
        "username": str,  # Sender
        "target": str,  # Recipient
        "message": str,
        "room": str
    }
    """

    CHAT_FAILED = "chat:failed"
    """
    Emitted when a chat action fails.

    Detail: {
        "username": str,
        "action": str,  # "say", "yell", "whisper"
        "reason": str
    }
    """

    # =========================================================================
    # COMMAND EVENTS
    # =========================================================================
    # Events about command execution

    COMMAND_EXECUTED = "command:executed"
    """
    Emitted when a command is successfully executed.

    Detail: {
        "username": str,
        "command": str,  # The command name
        "args": list[str],  # Command arguments
        "result": str  # Success message
    }
    """

    COMMAND_FAILED = "command:failed"
    """
    Emitted when a command fails.

    Detail: {
        "username": str,
        "command": str,
        "args": list[str],
        "error": str  # Error message
    }
    """

    COMMAND_UNKNOWN = "command:unknown"
    """
    Emitted when an unknown command is entered.
    Plugins can listen to this to implement custom commands.

    Detail: {
        "username": str,
        "command": str,
        "args": list[str]
    }
    """


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def is_valid_event_type(event_type: str) -> bool:
    """
    Check if an event type is a known standard event.

    This doesn't prevent custom events - it just checks if an event
    type is one of the predefined constants.

    Args:
        event_type: The event type string to check

    Returns:
        True if this is a standard event type, False otherwise
    """
    # Get all string attributes from Events class
    standard_events = {
        value
        for name, value in vars(Events).items()
        if isinstance(value, str) and not name.startswith("_")
    }
    return event_type in standard_events


def get_all_event_types() -> list[str]:
    """
    Get a list of all standard event types.

    Useful for documentation, debugging, or validation.

    Returns:
        List of all standard event type strings
    """
    return sorted(
        [
            value
            for name, value in vars(Events).items()
            if isinstance(value, str) and not name.startswith("_")
        ]
    )
