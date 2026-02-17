"""Game interaction endpoints (commands, chat, status)."""

from fastapi import APIRouter

from mud_server.api.auth import validate_session, validate_session_for_game
from mud_server.api.models import CommandRequest, CommandResponse, StatusResponse
from mud_server.api.permissions import Permission, has_permission
from mud_server.core.engine import GameEngine
from mud_server.db import facade as database


def router(engine: GameEngine) -> APIRouter:
    """Build the game router with access to the game engine."""
    api = APIRouter()

    @api.post("/command", response_model=CommandResponse)
    async def execute_command(request: CommandRequest):
        """
        Execute a game command.

        Parses command string and delegates to appropriate engine method.
        Commands can start with "/" or not. Command verb is case-insensitive
        but arguments (like player names) preserve case.
        """
        _, _, role, _, character_name, world_id = validate_session_for_game(request.session_id)

        command = request.command.strip()

        if not command:
            return CommandResponse(success=False, message="Enter a command.")

        # Strip leading slash if present (support both /command and command)
        if command.startswith("/"):
            command = command[1:]

        # Parse command (only lowercase the verb, keep args case-sensitive)
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ["n", "north", "s", "south", "e", "east", "w", "west", "u", "up", "d", "down"]:
            direction_map = {
                "n": "north",
                "s": "south",
                "e": "east",
                "w": "west",
                "u": "up",
                "d": "down",
            }
            direction = direction_map.get(cmd, cmd)
            success, message = engine.move(character_name, direction, world_id=world_id)
            return CommandResponse(success=success, message=message)

        if cmd in ["look", "l"]:
            message = engine.look(character_name, world_id=world_id)
            return CommandResponse(success=True, message=message)

        if cmd in ["inventory", "inv", "i"]:
            message = engine.get_inventory(character_name, world_id=world_id)
            return CommandResponse(success=True, message=message)

        if cmd in ["get", "take"]:
            if not args:
                return CommandResponse(success=False, message="Get what?")
            success, message = engine.pickup_item(character_name, args, world_id=world_id)
            return CommandResponse(success=success, message=message)

        if cmd == "drop":
            if not args:
                return CommandResponse(success=False, message="Drop what?")
            success, message = engine.drop_item(character_name, args, world_id=world_id)
            return CommandResponse(success=success, message=message)

        if cmd in ["say", "chat"]:
            if not args:
                return CommandResponse(success=False, message="Say what?")
            success, message = engine.chat(character_name, args, world_id=world_id)
            return CommandResponse(success=success, message=message)

        if cmd == "yell":
            if not args:
                return CommandResponse(success=False, message="Yell what?")
            success, message = engine.yell(character_name, args, world_id=world_id)
            return CommandResponse(success=success, message=message)

        if cmd in ["whisper", "w"]:
            if not args:
                return CommandResponse(
                    success=False, message="Whisper to whom? Usage: /whisper <player> <message>"
                )
            whisper_parts = args.split(maxsplit=1)
            if len(whisper_parts) < 2:
                return CommandResponse(
                    success=False, message="Whisper what? Usage: /whisper <player> <message>"
                )
            target = whisper_parts[0]
            msg = whisper_parts[1]
            success, message = engine.whisper(character_name, target, msg, world_id=world_id)
            return CommandResponse(success=success, message=message)

        if cmd in ["recall", "flee", "scurry"]:
            success, message = engine.recall(character_name, world_id=world_id)
            return CommandResponse(success=success, message=message)

        if cmd == "who":
            players = engine.get_active_players(world_id=world_id)
            if not players:
                message = "No other players online."
            else:
                message = "Active players:\n" + "\n".join(f"  - {p}" for p in players)
            return CommandResponse(success=True, message=message)

        if cmd == "kick":
            if not has_permission(role, Permission.KICK_USERS):
                return CommandResponse(
                    success=False,
                    message="Insufficient permissions. /kick is admin/superuser only.",
                )
            if not args:
                return CommandResponse(success=False, message="Kick whom? Usage: /kick <character>")
            success, message = engine.kick_character(character_name, args, world_id=world_id)
            return CommandResponse(success=success, message=message)

        if cmd in ["help", "?"]:
            help_text = """
[Available Commands]
Movement:
  /north, /n, /south, /s, /east, /e, /west, /w - Move in a direction
  /up, /u, /down, /d - Move up or down

Actions:
  /look, /l - Examine the current room
  /inventory, /inv, /i - View your inventory
  /get <item>, /take <item> - Pick up an item
  /drop <item> - Drop an item
  /recall, /flee, /scurry - Return to zone spawn point

Communication:
  /say <message> - Send a message to the current room
  /yell <message> - Yell to current room and adjoining rooms
  /whisper <player> <message> - Send private message (only you and target see it)

Other:
  /who - List active players
  /kick <character> - Disconnect a character (admin/superuser only)
  /help, /? - Show this help message

Note: Commands can be used with or without the / prefix
            """
            return CommandResponse(success=True, message=help_text)

        return CommandResponse(
            success=False,
            message=f"Unknown command: {cmd}. Type 'help' for available commands.",
        )

    @api.get("/chat/{session_id}")
    async def get_chat(session_id: str):
        """Get recent chat messages from current room."""
        _, _, _, _, character_name, world_id = validate_session_for_game(session_id)
        chat = engine.get_room_chat(character_name, world_id=world_id)
        return {"chat": chat}

    @api.post("/ping/{session_id}")
    async def heartbeat(session_id: str):
        """Heartbeat to update session activity without other actions."""
        validate_session(session_id)
        return {"ok": True}

    @api.get("/status/{session_id}", response_model=StatusResponse)
    async def get_status(session_id: str):
        """Get player status."""
        _, _, _, _, character_name, world_id = validate_session_for_game(session_id)

        current_room = database.get_character_room(character_name, world_id=world_id)
        inventory = engine.get_inventory(character_name, world_id=world_id)
        active_players = engine.get_active_players(world_id=world_id)

        return StatusResponse(
            active_players=active_players,
            current_room=current_room,
            inventory=inventory,
        )

    return api
