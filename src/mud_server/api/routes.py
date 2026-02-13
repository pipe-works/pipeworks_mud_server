"""
API route definitions for the MUD server.

This module defines all HTTP API endpoints using FastAPI. The routes are organized
into several categories:

Public Endpoints (No Authentication):
    - GET / - Root endpoint
    - POST /login - User login with password
    - POST /register - New account registration

Authenticated Endpoints (Require Session):
    - POST /logout - User logout
    - POST /command - Execute game commands (movement, chat, inventory, etc.)
    - GET /chat/{session_id} - Get room chat messages
    - GET /status/{session_id} - Get player status
    - POST /change-password - Change current user's password

Admin Endpoints (Require Specific Permissions):
    - GET /admin/database/players - View all players (VIEW_LOGS)
    - GET /admin/database/sessions - View all sessions (VIEW_LOGS)
    - GET /admin/database/chat-messages - View all chat (VIEW_LOGS)
    - POST /admin/user/manage - Manage users (MANAGE_USERS)
    - POST /admin/server/stop - Stop server (STOP_SERVER)

Health Check:
    - GET /health - Server health status

Command Parsing:
    Commands can be sent with or without "/" prefix. The following commands are supported:
    - Movement: north/n, south/s, east/e, west/w
    - Actions: look/l, inventory/inv/i, get/take <item>, drop <item>
    - Chat: say <message>, yell <message>, whisper/w <player> <message>
    - Info: who, help/?

Design Notes:
    - All routes use Pydantic models for request/response validation
    - Sessions validated at start of each protected endpoint
    - Errors raised as HTTPException with appropriate status codes
    - Game logic delegated to GameEngine class
    - All database operations through database module
"""

import os
import signal
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from mud_server.api.auth import (
    get_active_session_count,
    remove_session,
    validate_session,
    validate_session_for_game,
    validate_session_with_permission,
)
from mud_server.api.models import (
    ChangePasswordRequest,
    CharactersResponse,
    ClearOllamaContextRequest,
    ClearOllamaContextResponse,
    CommandRequest,
    CommandResponse,
    CreateUserRequest,
    CreateUserResponse,
    DatabaseChatResponse,
    DatabaseConnectionsResponse,
    DatabasePlayerLocationsResponse,
    DatabasePlayersResponse,
    DatabaseSessionsResponse,
    DatabaseTableInfo,
    DatabaseTableRowsResponse,
    DatabaseTablesResponse,
    KickSessionRequest,
    KickSessionResponse,
    LoginDirectRequest,
    LoginDirectResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    OllamaCommandRequest,
    OllamaCommandResponse,
    RegisterGuestRequest,
    RegisterGuestResponse,
    RegisterRequest,
    RegisterResponse,
    SelectCharacterRequest,
    SelectCharacterResponse,
    ServerStopRequest,
    ServerStopResponse,
    StatusResponse,
    UserManagementRequest,
    UserManagementResponse,
)
from mud_server.api.permissions import Permission, can_manage_role
from mud_server.config import config
from mud_server.core.engine import GameEngine
from mud_server.db import database


def register_routes(app: FastAPI, engine: GameEngine):
    """
    Register all API routes with the FastAPI app.

    This function is called once at server startup to register all endpoints.
    It creates closures over the app and engine instances so routes can access
    the game engine.

    Args:
        app: FastAPI application instance
        engine: GameEngine instance for game logic
    """

    # Ollama conversation history storage (per session_id)
    # Structure: {session_id: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
    ollama_conversation_history: dict[str, list[dict[str, str]]] = {}

    def _resolve_zone_id(room_id: str | None, world_id: str | None) -> str | None:
        """
        Resolve a room_id to its zone id using the loaded world data.

        Returns None if the room cannot be mapped to a zone.
        """
        if not room_id or not world_id:
            return None
        try:
            world = engine.world_registry.get_world(world_id)
        except ValueError:
            return None
        for zone_id, zone in world.zones.items():
            if room_id in zone.rooms:
                return zone_id
        return None

    def _get_available_worlds(user_id: int, role: str) -> list[dict[str, Any]]:
        """
        Return available worlds filtered by permissions and account rules.

        Admins and superusers are implicitly allowed all worlds. Other users
        must have explicit grants in world_permissions.
        """
        return database.list_worlds_for_user(user_id, role=role)

    # ========================================================================
    # PUBLIC ENDPOINTS
    # ========================================================================

    @app.get("/")
    async def root():
        """Root endpoint showing API info."""
        return {"message": "MUD Server API", "version": "0.3.2"}

    @app.post("/login", response_model=LoginResponse)
    async def login(request: LoginRequest, http_request: Request):
        """
        User login with username and password.

        Validates credentials, creates session, and returns session ID + role.
        """
        username = request.username.strip()
        password = request.password
        requested_world_id = request.world_id.strip() if request.world_id else None

        if not username or len(username) < 2 or len(username) > 20:
            raise HTTPException(status_code=400, detail="Username must be 2-20 characters")

        if not database.user_exists(username):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        if not database.verify_password_for_user(username, password):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        if not database.is_user_active(username):
            raise HTTPException(status_code=401, detail="Account is deactivated")

        user_id = database.get_user_id(username)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user record")

        session_id = str(uuid.uuid4())
        client_type = http_request.headers.get("X-Client-Type", "unknown").strip().lower()
        if not client_type:
            client_type = "unknown"

        if not database.create_session(user_id, session_id, client_type=client_type):
            raise HTTPException(status_code=500, detail="Failed to create session")

        role = database.get_user_role(username)
        if not role:
            raise HTTPException(status_code=401, detail="Invalid user role")

        available_worlds = _get_available_worlds(user_id, role)

        # Filter characters by requested world when provided.
        if requested_world_id:
            characters = database.get_user_characters(user_id, world_id=requested_world_id)
        else:
            # Default to the configured world if no explicit world requested.
            characters = database.get_user_characters(user_id)
        message = "Login successful. Select a character to enter the world."

        return LoginResponse(
            success=True,
            message=message,
            session_id=session_id,
            role=role,
            characters=characters,
            available_worlds=available_worlds,
        )

    @app.post("/login-direct", response_model=LoginDirectResponse)
    async def login_direct(request: LoginDirectRequest, http_request: Request):
        """
        Direct login that binds a session to a world + character.

        This endpoint is intended for API clients that want to skip the
        explicit world/character selection steps.
        """
        username = request.username.strip()
        password = request.password
        world_id = request.world_id.strip()
        character_name = request.character_name.strip() if request.character_name else None

        if not character_name:
            raise HTTPException(status_code=400, detail="character_name is required")

        if not username or len(username) < 2 or len(username) > 20:
            raise HTTPException(status_code=400, detail="Username must be 2-20 characters")

        if not database.user_exists(username):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        if not database.verify_password_for_user(username, password):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        if not database.is_user_active(username):
            raise HTTPException(status_code=401, detail="Account is deactivated")

        user_id = database.get_user_id(username)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user record")

        role = database.get_user_role(username)
        if not role:
            raise HTTPException(status_code=401, detail="Invalid user role")

        available_worlds = _get_available_worlds(user_id, role)
        if world_id not in {world["id"] for world in available_worlds}:
            raise HTTPException(status_code=403, detail="World access denied")

        character_id: int | None = None
        if character_name:
            character = database.get_character_by_name(character_name)
            if character:
                if character.get("user_id") != user_id or character.get("world_id") != world_id:
                    raise HTTPException(status_code=403, detail="Character not available")
                character_id = int(character["id"])
            else:
                if not request.create_character:
                    raise HTTPException(status_code=404, detail="Character not found")
                if not config.worlds.allow_multi_world_characters:
                    existing_worlds = database.get_user_character_world_ids(user_id)
                    if existing_worlds and world_id not in existing_worlds:
                        raise HTTPException(
                            status_code=409,
                            detail="Multi-world characters are disabled",
                        )
                if not database.create_character_for_user(
                    user_id, character_name, world_id=world_id
                ):
                    raise HTTPException(status_code=409, detail="Failed to create character")
                character = database.get_character_by_name(character_name)
                if not character:
                    raise HTTPException(status_code=500, detail="Character creation failed")
                character_id = int(character["id"])

        session_id = str(uuid.uuid4())
        client_type = http_request.headers.get("X-Client-Type", "unknown").strip().lower()
        if not client_type:
            client_type = "unknown"

        if not database.create_session(
            user_id,
            session_id,
            client_type=client_type,
            character_id=character_id,
            world_id=world_id,
        ):
            raise HTTPException(status_code=500, detail="Failed to create session")

        if character_id is not None:
            if not database.set_session_character(session_id, character_id, world_id=world_id):
                raise HTTPException(status_code=500, detail="Failed to bind character")

        message = "Login successful."
        return LoginDirectResponse(
            success=True,
            message=message,
            session_id=session_id,
            role=role,
            character_name=character_name,
            world_id=world_id,
        )

    @app.post("/register", response_model=RegisterResponse)
    async def register(request: RegisterRequest):
        """
        Register a new temporary visitor account with password policy enforcement.

        The registration process validates:
        1. Username format (2-20 characters, unique)
        2. Password strength against STANDARD security policy
        3. Password confirmation match

        Password Policy (STANDARD level):
        - Minimum 12 characters
        - Not a commonly used password
        - No sequential characters (abc, 123)
        - No excessive repeated characters

        Returns:
            RegisterResponse with success status and message.
            Visitor accounts are purged after 24 hours.

        Raises:
            HTTPException 400: Invalid input (username, password policy, mismatch)
            HTTPException 500: Database error during account creation
        """
        from mud_server.api.password_policy import PolicyLevel, validate_password_strength

        username = request.username.strip()
        password = request.password
        password_confirm = request.password_confirm

        # Validate username
        if not username or len(username) < 2 or len(username) > 20:
            raise HTTPException(status_code=400, detail="Username must be 2-20 characters")

        # Check if username already exists
        if database.user_exists(username):
            raise HTTPException(status_code=400, detail="Username already taken")

        # Validate passwords match
        if password != password_confirm:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        # Validate password strength against security policy
        result = validate_password_strength(password, level=PolicyLevel.STANDARD)
        if not result.is_valid:
            # Combine all errors into a single detail message
            error_detail = " ".join(result.errors)
            raise HTTPException(status_code=400, detail=error_detail)

        # Create visitor account (temporary; cleaned up automatically)
        from datetime import UTC, datetime, timedelta

        guest_expires_at = (datetime.now(UTC) + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        if database.create_user_with_password(
            username,
            password,
            role="player",
            account_origin="visitor",
            is_guest=True,
            guest_expires_at=guest_expires_at,
        ):
            return RegisterResponse(
                success=True,
                message=(
                    "Temporary account created successfully! " f"You can now login as {username}."
                ),
            )
        else:
            raise HTTPException(
                status_code=500, detail="Failed to create account. Please try again."
            )

    @app.post("/register-guest", response_model=RegisterGuestResponse)
    async def register_guest(request: RegisterGuestRequest):
        """
        Register a new temporary guest account with a server-generated username.

        This endpoint enforces password policy and creates a single character
        for the guest account. Username generation is handled server-side to
        ensure consistent formatting, uniqueness, and future-proofing.

        The guest flow validates:
        1. Password strength against STANDARD security policy
        2. Password confirmation match
        3. Character name presence + uniqueness

        Returns:
            RegisterGuestResponse with generated username and status.
            Guest accounts are purged after 24 hours.

        Raises:
            HTTPException 400: Invalid input (password policy, mismatch, character name)
            HTTPException 500: Database error during account creation
        """
        from datetime import UTC, datetime, timedelta
        from secrets import randbelow

        from mud_server.api.password_policy import PolicyLevel, validate_password_strength

        password = request.password
        password_confirm = request.password_confirm
        character_name = request.character_name.strip()

        if not character_name:
            raise HTTPException(status_code=400, detail="Character name is required")

        if database.character_exists(character_name):
            raise HTTPException(status_code=400, detail="Character name already taken")

        if password != password_confirm:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        result = validate_password_strength(password, level=PolicyLevel.STANDARD)
        if not result.is_valid:
            error_detail = " ".join(result.errors)
            raise HTTPException(status_code=400, detail=error_detail)

        # Generate a short, unique guest username (fits 2-20 char constraint).
        guest_prefix = "guest_"
        max_attempts = 20
        username = None
        for _ in range(max_attempts):
            candidate = f"{guest_prefix}{randbelow(100000):05d}"
            if not database.user_exists(candidate):
                username = candidate
                break

        if username is None:
            raise HTTPException(status_code=500, detail="Failed to allocate a guest username")

        guest_expires_at = (datetime.now(UTC) + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        if not database.create_user_with_password(
            username,
            password,
            role="player",
            account_origin="visitor",
            is_guest=True,
            guest_expires_at=guest_expires_at,
            create_default_character=False,
        ):
            raise HTTPException(
                status_code=500, detail="Failed to create guest account. Please try again."
            )

        user_id = database.get_user_id(username)
        if user_id is None:
            database.delete_user(username)
            raise HTTPException(status_code=500, detail="Failed to finalize guest account")

        if not database.create_character_for_user(
            user_id,
            character_name,
            is_guest_created=True,
        ):
            database.delete_user(username)
            raise HTTPException(status_code=400, detail="Character name already taken")

        return RegisterGuestResponse(
            success=True,
            message=(
                "Temporary guest account created successfully! " f"You can now login as {username}."
            ),
            username=username,
        )

    # ========================================================================
    # AUTHENTICATED ENDPOINTS (Require Valid Session)
    # ========================================================================

    @app.post("/logout")
    async def logout(request: LogoutRequest):
        """Logout user and remove session from database."""
        _, username, _ = validate_session(request.session_id)
        remove_session(request.session_id)
        return {"success": True, "message": f"Goodbye, {username}!"}

    @app.get("/characters", response_model=CharactersResponse)
    async def list_characters(session_id: str, world_id: str | None = None):
        """List available characters for the logged-in user."""
        user_id, _, role = validate_session(session_id)
        if world_id:
            available_worlds = _get_available_worlds(user_id, role)
            if world_id not in {world["id"] for world in available_worlds}:
                raise HTTPException(status_code=403, detail="World access denied")
        characters = database.get_user_characters(user_id, world_id=world_id)
        return CharactersResponse(characters=characters)

    @app.post("/characters/select", response_model=SelectCharacterResponse)
    async def select_character(request: SelectCharacterRequest):
        """Select a character for the current session."""
        user_id, _, role = validate_session(request.session_id)
        character = database.get_character_by_id(request.character_id)
        if not character or character.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="Character not found for this user")

        world_id = request.world_id or character.get("world_id")
        if not world_id:
            raise HTTPException(status_code=400, detail="World id required")

        available_worlds = _get_available_worlds(user_id, role)
        if world_id not in {world["id"] for world in available_worlds}:
            raise HTTPException(status_code=403, detail="World access denied")

        if character.get("world_id") != world_id:
            raise HTTPException(status_code=409, detail="Character does not belong to world")

        if not database.set_session_character(
            request.session_id, request.character_id, world_id=world_id
        ):
            raise HTTPException(status_code=500, detail="Failed to select character")

        return SelectCharacterResponse(
            success=True,
            message="Character selected.",
            character_name=character["name"],
        )

    @app.post("/command", response_model=CommandResponse)
    async def execute_command(request: CommandRequest):
        """
        Execute a game command.

        Parses command string and delegates to appropriate engine method.
        Commands can start with "/" or not. Command verb is case-insensitive
        but arguments (like player names) preserve case.

        Supported Commands:
            - Movement: n/north, s/south, e/east, w/west
            - Actions: look/l, inventory/inv/i, get/take, drop
            - Chat: say, yell, whisper/w
            - Info: who, help/?
        """
        _, _, _, _, character_name, world_id = validate_session_for_game(request.session_id)

        command = request.command.strip()

        if not command:
            return CommandResponse(success=False, message="Enter a command.")

        # Strip leading slash if present (support both /command and command)
        if command.startswith("/"):
            command = command[1:]

        # Parse command (only lowercase the verb, keep args case-sensitive)
        # This is critical for whispers where usernames like "Mendit" must preserve case
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()  # Command verb is case-insensitive
        args = parts[1] if len(parts) > 1 else ""  # Arguments preserve case (e.g., player names)

        # ====================================================================
        # COMMAND ROUTING
        # Route to appropriate engine method based on command verb
        # ====================================================================
        if cmd in ["n", "north", "s", "south", "e", "east", "w", "west", "u", "up", "d", "down"]:
            # Map shorthand to full direction
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

        elif cmd in ["look", "l"]:
            message = engine.look(character_name, world_id=world_id)
            return CommandResponse(success=True, message=message)

        elif cmd in ["inventory", "inv", "i"]:
            message = engine.get_inventory(character_name, world_id=world_id)
            return CommandResponse(success=True, message=message)

        elif cmd in ["get", "take"]:
            if not args:
                return CommandResponse(success=False, message="Get what?")
            success, message = engine.pickup_item(character_name, args, world_id=world_id)
            return CommandResponse(success=success, message=message)

        elif cmd == "drop":
            if not args:
                return CommandResponse(success=False, message="Drop what?")
            success, message = engine.drop_item(character_name, args, world_id=world_id)
            return CommandResponse(success=success, message=message)

        elif cmd in ["say", "chat"]:
            if not args:
                return CommandResponse(success=False, message="Say what?")
            success, message = engine.chat(character_name, args, world_id=world_id)
            return CommandResponse(success=success, message=message)

        elif cmd == "yell":
            if not args:
                return CommandResponse(success=False, message="Yell what?")
            # Yell sends to current room and all adjoining rooms
            success, message = engine.yell(character_name, args, world_id=world_id)
            return CommandResponse(success=success, message=message)

        elif cmd in ["whisper", "w"]:
            if not args:
                return CommandResponse(
                    success=False, message="Whisper to whom? Usage: /whisper <player> <message>"
                )
            # Parse whisper target and message
            whisper_parts = args.split(maxsplit=1)
            if len(whisper_parts) < 2:
                return CommandResponse(
                    success=False, message="Whisper what? Usage: /whisper <player> <message>"
                )
            target = whisper_parts[0]
            msg = whisper_parts[1]
            # Send private whisper
            success, message = engine.whisper(character_name, target, msg, world_id=world_id)
            return CommandResponse(success=success, message=message)

        elif cmd in ["recall", "flee", "scurry"]:
            # Recall to zone spawn point
            success, message = engine.recall(character_name, world_id=world_id)
            return CommandResponse(success=success, message=message)

        elif cmd == "who":
            players = engine.get_active_players(world_id=world_id)
            if not players:
                message = "No other players online."
            else:
                message = "Active players:\n" + "\n".join(f"  - {p}" for p in players)
            return CommandResponse(success=True, message=message)

        elif cmd in ["help", "?"]:
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
  /help, /? - Show this help message

Note: Commands can be used with or without the / prefix
            """
            return CommandResponse(success=True, message=help_text)

        else:
            return CommandResponse(
                success=False,
                message=f"Unknown command: {cmd}. Type 'help' for available commands.",
            )

    @app.get("/chat/{session_id}")
    async def get_chat(session_id: str):
        """Get recent chat messages from current room."""
        _, _, _, _, character_name, world_id = validate_session_for_game(session_id)
        chat = engine.get_room_chat(character_name, world_id=world_id)
        return {"chat": chat}

    @app.post("/ping/{session_id}")
    async def heartbeat(session_id: str):
        """Heartbeat to update session activity without other actions."""
        validate_session(session_id)
        return {"ok": True}

    @app.get("/status/{session_id}")
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

    @app.post("/change-password")
    async def change_password(request: ChangePasswordRequest):
        """
        Change current user's password with policy enforcement.

        Validates the new password against the STANDARD security policy:
        - Minimum 12 characters
        - Not a commonly used password
        - No sequential characters (abc, 123)
        - No excessive repeated characters

        Args:
            request: Contains session_id, old_password, and new_password.

        Returns:
            Success message if password changed.

        Raises:
            HTTPException 401: Current password incorrect.
            HTTPException 400: New password fails policy validation or same as old.
            HTTPException 500: Database error during password change.
        """
        from mud_server.api.password_policy import PolicyLevel, validate_password_strength

        _, username, _ = validate_session(request.session_id)

        # Verify old password
        if not database.verify_password_for_user(username, request.old_password):
            raise HTTPException(status_code=401, detail="Current password is incorrect")

        # Check new password is different from old
        if request.new_password == request.old_password:
            raise HTTPException(
                status_code=400, detail="New password must be different from current password"
            )

        # Validate new password against security policy
        result = validate_password_strength(request.new_password, level=PolicyLevel.STANDARD)
        if not result.is_valid:
            error_detail = " ".join(result.errors)
            raise HTTPException(status_code=400, detail=error_detail)

        # Change password
        if database.change_password_for_user(username, request.new_password):
            return {"success": True, "message": "Password changed successfully!"}
        else:
            raise HTTPException(status_code=500, detail="Failed to change password")

    # ========================================================================
    # ADMIN ENDPOINTS (Require Specific Permissions)
    # ========================================================================

    @app.get("/admin/database/players", response_model=DatabasePlayersResponse)
    async def get_database_players(session_id: str):
        """Get all users from database with details (Requires VIEW_LOGS permission)."""
        _, _, _ = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        users = database.get_all_users_detailed()
        return DatabasePlayersResponse(players=users)

    @app.get("/admin/database/connections", response_model=DatabaseConnectionsResponse)
    async def get_database_connections(session_id: str):
        """Get active session connections with activity age (Admin only)."""
        _, _, _ = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
        try:
            _, _, _, _, _, world_id = validate_session_for_game(session_id)
        except HTTPException:
            world_id = None

        connections = database.get_active_connections(world_id=world_id)
        return DatabaseConnectionsResponse(connections=connections)

    @app.get("/admin/database/player-locations", response_model=DatabasePlayerLocationsResponse)
    async def get_database_player_locations(session_id: str):
        """Get character locations with zone context (Admin only)."""
        _, _, _ = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
        try:
            _, _, _, _, _, world_id = validate_session_for_game(session_id)
        except HTTPException:
            world_id = None

        locations = []
        for location in database.get_character_locations(world_id=world_id):
            # Zone ID is derived from the in-memory world data so we can
            # show high-level location context without storing it in the DB.
            room_id = location.get("room_id")
            zone_id = _resolve_zone_id(room_id, world_id)
            locations.append(
                {
                    **location,
                    "zone_id": zone_id,
                }
            )

        return DatabasePlayerLocationsResponse(locations=locations)

    @app.post("/admin/session/kick", response_model=KickSessionResponse)
    async def kick_session(request: KickSessionRequest):
        """Force-disconnect an active session (Admin/Superuser only)."""
        _, _, _ = validate_session_with_permission(request.session_id, Permission.KICK_USERS)

        removed = remove_session(request.target_session_id)
        if removed:
            return KickSessionResponse(success=True, message="Session disconnected")
        return KickSessionResponse(success=False, message="Session not found")

    @app.get("/admin/database/tables", response_model=DatabaseTablesResponse)
    async def get_database_tables(session_id: str):
        """Get list of database tables with schema details (Admin only)."""
        _, username, role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        tables = [DatabaseTableInfo(**table) for table in database.list_tables()]
        return DatabaseTablesResponse(tables=tables)

    @app.get("/admin/database/table/{table_name}", response_model=DatabaseTableRowsResponse)
    async def get_database_table_rows(session_id: str, table_name: str, limit: int = 100):
        """Get rows from a specific database table (Admin only)."""
        _, username, role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        try:
            columns, rows = database.get_table_rows(table_name, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return DatabaseTableRowsResponse(table=table_name, columns=columns, rows=rows)

    @app.get("/admin/database/sessions", response_model=DatabaseSessionsResponse)
    async def get_database_sessions(session_id: str):
        """Get all active sessions from the database (Admin only)."""
        _, username, role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
        try:
            _, _, _, _, _, world_id = validate_session_for_game(session_id)
        except HTTPException:
            world_id = None

        sessions = database.get_all_sessions(world_id=world_id)
        return DatabaseSessionsResponse(sessions=sessions)

    @app.get("/admin/database/chat-messages", response_model=DatabaseChatResponse)
    async def get_database_chat_messages(session_id: str, limit: int = 100):
        """Get recent chat messages from the database (Admin only)."""
        _, username, role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
        try:
            _, _, _, _, _, world_id = validate_session_for_game(session_id)
        except HTTPException:
            world_id = None

        messages = database.get_all_chat_messages(limit=limit, world_id=world_id)
        return DatabaseChatResponse(messages=messages)

    @app.post("/admin/user/manage", response_model=UserManagementResponse)
    async def manage_user(request: UserManagementRequest):
        """Manage users: change role, ban/deactivate, unban, or change password."""
        # Parse action first to determine required permission
        action = request.action.lower()

        # Normalize action aliases
        if action == "deactivate":
            action = "ban"

        # Determine required permission based on action
        if action == "change_role":
            required_permission = Permission.MANAGE_USERS
        elif action in ["ban", "unban"]:
            required_permission = Permission.BAN_USERS
        elif action == "delete":
            required_permission = Permission.MANAGE_USERS
        elif action == "change_password":
            required_permission = Permission.MANAGE_USERS
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid action '{request.action}'. Valid actions: change_role, "
                    "ban, deactivate, unban, delete, change_password"
                ),
            )

        # Validate session with appropriate permission
        _, username, role = validate_session_with_permission(
            request.session_id, required_permission
        )

        target_username = request.target_username

        # Check if target user exists
        if not database.user_exists(target_username):
            raise HTTPException(status_code=404, detail=f"User '{target_username}' not found")

        # Get target user's role
        target_role = database.get_user_role(target_username)
        if not target_role:
            raise HTTPException(status_code=404, detail="Target user not found")

        # Prevent self-management (except for password changes in the future)
        if username == target_username and action != "change_password":
            raise HTTPException(status_code=400, detail="Cannot manage your own account")

        # Check permission hierarchy (user can only manage lower-ranked users)
        if not can_manage_role(role, target_role):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions to manage user with role '{target_role}'",
            )

        # Perform action
        if action == "change_role":
            if not request.new_role:
                raise HTTPException(
                    status_code=400, detail="new_role is required for change_role action"
                )

            new_role = request.new_role.lower()
            valid_roles = ["player", "worldbuilder", "admin", "superuser"]

            if new_role not in valid_roles:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid role. Valid roles: {', '.join(valid_roles)}",
                )

            # Check if admin can assign the new role
            if not can_manage_role(role, new_role):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions to assign role '{new_role}'",
                )

            if database.set_user_role(target_username, new_role):
                return UserManagementResponse(
                    success=True,
                    message=f"Successfully changed {target_username}'s role to {new_role}",
                )
            else:
                raise HTTPException(status_code=500, detail="Failed to change role")

        elif action == "ban":
            if database.deactivate_user(target_username):
                user_id = database.get_user_id(target_username)
                if user_id:
                    database.remove_sessions_for_user(user_id)

                return UserManagementResponse(
                    success=True, message=f"Successfully banned {target_username}"
                )
            else:
                raise HTTPException(status_code=500, detail="Failed to ban user")

        elif action == "delete":
            if role != "superuser":
                raise HTTPException(
                    status_code=403,
                    detail="Only superusers may permanently delete users",
                )

            if database.delete_user(target_username):
                return UserManagementResponse(
                    success=True, message=f"Successfully deleted {target_username}"
                )
            else:
                raise HTTPException(status_code=500, detail="Failed to delete user")

        elif action == "unban":
            if database.activate_user(target_username):
                return UserManagementResponse(
                    success=True, message=f"Successfully unbanned {target_username}"
                )
            else:
                raise HTTPException(status_code=500, detail="Failed to unban user")

        elif action == "change_password":
            # Get new password from request
            new_password = request.new_password
            if not new_password:
                raise HTTPException(
                    status_code=400, detail="new_password is required for change_password action"
                )

            # Validate password length
            if len(new_password) < 8:
                raise HTTPException(
                    status_code=400, detail="Password must be at least 8 characters long"
                )

            # Change the password
            if database.change_password_for_user(target_username, new_password):
                return UserManagementResponse(
                    success=True, message=f"Successfully changed password for {target_username}"
                )
            else:
                raise HTTPException(status_code=500, detail="Failed to change password")

        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid action '{action}'. Valid actions: change_role, "
                    "ban, deactivate, unban, delete, change_password"
                ),
            )

    @app.post("/admin/user/create", response_model=CreateUserResponse)
    async def create_user(request: CreateUserRequest):
        """
        Create a new user account (Admin/Superuser only).

        Validation steps:
        1. Session has CREATE_USERS permission
        2. Username length and uniqueness
        3. Role allowed for the requesting user
        4. Password confirmation match
        5. STANDARD password policy enforcement
        """
        from mud_server.api.password_policy import PolicyLevel, validate_password_strength

        _, _creator_username, creator_role = validate_session_with_permission(
            request.session_id, Permission.CREATE_USERS
        )

        username = request.username.strip()
        role = request.role.strip().lower()
        password = request.password
        password_confirm = request.password_confirm

        # Validate username
        if not username or len(username) < 2 or len(username) > 20:
            raise HTTPException(status_code=400, detail="Username must be 2-20 characters")

        # Validate role
        valid_roles = {"player", "worldbuilder", "admin", "superuser"}
        if role not in valid_roles:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role. Valid roles: {', '.join(sorted(valid_roles))}",
            )

        # Enforce role creation rules
        if creator_role == "admin":
            allowed_roles = {"player", "worldbuilder"}
        elif creator_role == "superuser":
            allowed_roles = valid_roles
        else:
            allowed_roles = set()

        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions to create role '{role}'",
            )

        # Check if username already exists
        if database.user_exists(username):
            raise HTTPException(status_code=400, detail="Username already taken")

        # Validate passwords match
        if password != password_confirm:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        # Validate password strength against security policy
        result = validate_password_strength(password, level=PolicyLevel.STANDARD)
        if not result.is_valid:
            error_detail = " ".join(result.errors)
            raise HTTPException(status_code=400, detail=error_detail)

        # Create user account
        if database.create_user_with_password(
            username, password, role=role, account_origin=creator_role
        ):
            return CreateUserResponse(
                success=True,
                message=f"User '{username}' created with role '{role}'.",
            )

        raise HTTPException(status_code=500, detail="Failed to create account. Please try again.")

    @app.post("/admin/server/stop", response_model=ServerStopResponse)
    async def stop_server(request: ServerStopRequest):
        """Stop the server (Admin and Superuser only)."""
        _, username, role = validate_session_with_permission(
            request.session_id, Permission.STOP_SERVER
        )

        # Schedule server shutdown after a brief delay to allow response to be sent
        import asyncio

        async def shutdown():
            await asyncio.sleep(0.5)  # Give time for response to be sent
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.create_task(shutdown())

        return ServerStopResponse(
            success=True,
            message=f"Server shutdown initiated by {username}. Server will stop in 0.5 seconds.",
        )

    @app.post("/admin/ollama/command", response_model=OllamaCommandResponse)
    async def execute_ollama_command(request: OllamaCommandRequest):
        """
        Execute an Ollama command (Admin and Superuser only).

        Sends commands to the Ollama server API and returns the output.
        Supports any ollama CLI command via the API.
        """
        _, username, role = validate_session_with_permission(
            request.session_id, Permission.VIEW_LOGS
        )

        import json

        try:
            server_url = request.server_url.strip()
            command = request.command.strip()

            if not server_url or not command:
                return OllamaCommandResponse(
                    success=False, output="Server URL and command are required"
                )

            # Use requests library to interact with Ollama API
            import requests as req

            # Parse the command to determine the appropriate API endpoint
            cmd_parts = command.split()
            cmd_verb = cmd_parts[0].lower()

            # Map common ollama commands to API endpoints
            if cmd_verb == "list" or cmd_verb == "ls":
                # List models via API
                response = req.get(f"{server_url}/api/tags", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    if models:
                        output = "Available models:\n"
                        for model in models:
                            name = model.get("name", "unknown")
                            size = model.get("size", 0)
                            modified = model.get("modified_at", "")
                            output += f"  - {name} (size: {size}, modified: {modified})\n"
                    else:
                        output = "No models found."
                    return OllamaCommandResponse(success=True, output=output)
                else:
                    return OllamaCommandResponse(
                        success=False,
                        output=f"Failed to list models: HTTP {response.status_code}",
                    )

            elif cmd_verb == "ps":
                # Show running models
                response = req.get(f"{server_url}/api/ps", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    if models:
                        output = "Running models:\n"
                        for model in models:
                            name = model.get("name", "unknown")
                            output += f"  - {name}\n"
                    else:
                        output = "No models currently running."
                    return OllamaCommandResponse(success=True, output=output)
                else:
                    return OllamaCommandResponse(
                        success=False,
                        output=f"Failed to show running models: HTTP {response.status_code}",
                    )

            elif cmd_verb == "pull":
                # Pull a model
                if len(cmd_parts) < 2:
                    return OllamaCommandResponse(success=False, output="Usage: pull <model_name>")
                model_name = cmd_parts[1]

                # Pull is a streaming endpoint
                response = req.post(
                    f"{server_url}/api/pull",
                    json={"name": model_name},
                    stream=True,
                    timeout=300,
                )

                if response.status_code == 200:
                    output = f"Pulling model '{model_name}'...\n"
                    for line in response.iter_lines():
                        if line:
                            data = json.loads(line)
                            status = data.get("status", "")
                            output += f"{status}\n"
                            if data.get("error"):
                                return OllamaCommandResponse(
                                    success=False, output=f"Error: {data.get('error')}"
                                )
                    return OllamaCommandResponse(success=True, output=output)
                else:
                    return OllamaCommandResponse(
                        success=False, output=f"Failed to pull model: HTTP {response.status_code}"
                    )

            elif cmd_verb == "run":
                # Run a model with a prompt (uses conversation history)
                if len(cmd_parts) < 2:
                    return OllamaCommandResponse(
                        success=False, output="Usage: run <model_name> [prompt]"
                    )

                model_name = cmd_parts[1]
                prompt = " ".join(cmd_parts[2:]) if len(cmd_parts) > 2 else "Hello"

                # Initialize conversation history for this session if not exists
                session_id = request.session_id
                if session_id not in ollama_conversation_history:
                    ollama_conversation_history[session_id] = []

                # Add user message to conversation history
                ollama_conversation_history[session_id].append({"role": "user", "content": prompt})

                # Call Ollama's /api/chat endpoint with full conversation history
                response = req.post(
                    f"{server_url}/api/chat",
                    json={
                        "model": model_name,
                        "messages": ollama_conversation_history[session_id],
                        "stream": False,
                    },
                    timeout=120,
                )

                if response.status_code == 200:
                    data = response.json()
                    assistant_message = data.get("message", {})
                    generated_text = assistant_message.get("content", "")

                    # Add assistant response to conversation history
                    ollama_conversation_history[session_id].append(
                        {"role": "assistant", "content": generated_text}
                    )

                    # Show conversation context info
                    msg_count = len(ollama_conversation_history[session_id])
                    output = f"Model: {model_name} (Context: {msg_count} messages)\n"
                    output += f"You: {prompt}\n\nResponse:\n{generated_text}"
                    return OllamaCommandResponse(success=True, output=output)
                else:
                    # Remove the user message if the request failed
                    ollama_conversation_history[session_id].pop()
                    error_detail = response.text
                    return OllamaCommandResponse(
                        success=False,
                        output=f"Failed to run model: HTTP {response.status_code}\n{error_detail}",
                    )

            elif cmd_verb == "show":
                # Show model information
                if len(cmd_parts) < 2:
                    return OllamaCommandResponse(success=False, output="Usage: show <model_name>")
                model_name = cmd_parts[1]

                response = req.post(
                    f"{server_url}/api/show",
                    json={"name": model_name},
                    timeout=10,
                )

                if response.status_code == 200:
                    data = response.json()
                    output = f"Model: {model_name}\n"
                    output += f"Modelfile:\n{data.get('modelfile', 'N/A')}\n"
                    output += f"Parameters:\n{data.get('parameters', 'N/A')}\n"
                    return OllamaCommandResponse(success=True, output=output)
                else:
                    return OllamaCommandResponse(
                        success=False,
                        output=f"Failed to show model info: HTTP {response.status_code}",
                    )

            else:
                return OllamaCommandResponse(
                    success=False,
                    output=f"Unknown command: {cmd_verb}\nSupported commands: list, ps, pull, run, show",
                )

        except req.exceptions.ConnectionError:
            return OllamaCommandResponse(
                success=False, output=f"Cannot connect to Ollama server at {server_url}"
            )
        except req.exceptions.Timeout:
            return OllamaCommandResponse(
                success=False, output="Request timed out. The operation may still be in progress."
            )
        except Exception as e:
            return OllamaCommandResponse(success=False, output=f"Error: {str(e)}")

    @app.post("/admin/ollama/clear-context", response_model=ClearOllamaContextResponse)
    async def clear_ollama_context(request: ClearOllamaContextRequest):
        """
        Clear Ollama conversation context for the current session (Admin and Superuser only).

        Removes all stored conversation history, allowing a fresh start with the model.
        """
        _, username, role = validate_session_with_permission(
            request.session_id, Permission.VIEW_LOGS
        )

        session_id = request.session_id

        # Check if there's any context to clear
        if session_id in ollama_conversation_history:
            msg_count = len(ollama_conversation_history[session_id])
            ollama_conversation_history[session_id] = []
            return ClearOllamaContextResponse(
                success=True,
                message=f"Conversation context cleared ({msg_count} messages removed).",
            )
        else:
            return ClearOllamaContextResponse(
                success=True, message="No conversation context to clear."
            )

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "active_players": get_active_session_count()}
