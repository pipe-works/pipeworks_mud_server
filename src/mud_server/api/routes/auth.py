"""Authentication and account management endpoints."""

import uuid

from fastapi import APIRouter, HTTPException, Request

from mud_server.api.auth import remove_session, validate_session
from mud_server.api.models import (
    ChangePasswordRequest,
    CharactersResponse,
    LoginDirectRequest,
    LoginDirectResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RegisterGuestRequest,
    RegisterGuestResponse,
    RegisterRequest,
    RegisterResponse,
    SelectCharacterRequest,
    SelectCharacterResponse,
)
from mud_server.api.routes.utils import get_available_worlds
from mud_server.config import config
from mud_server.core.engine import GameEngine
from mud_server.db import database


def router(engine: GameEngine) -> APIRouter:
    """Build the auth router with access to the game engine."""
    api = APIRouter()

    @api.post("/login", response_model=LoginResponse)
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

        available_worlds = get_available_worlds(user_id, role)

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

    @api.post("/login-direct", response_model=LoginDirectResponse)
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

        available_worlds = get_available_worlds(user_id, role)
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

    @api.post("/register", response_model=RegisterResponse)
    async def register(request: RegisterRequest):
        """
        Register a new temporary visitor account with password policy enforcement.
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

    @api.post("/register-guest", response_model=RegisterGuestResponse)
    async def register_guest(request: RegisterGuestRequest):
        """Register a new temporary guest account with a server-generated username."""
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

    @api.post("/logout")
    async def logout(request: LogoutRequest):
        """Logout user and remove session from database."""
        _, username, _ = validate_session(request.session_id)
        remove_session(request.session_id)
        return {"success": True, "message": f"Goodbye, {username}!"}

    @api.get("/characters", response_model=CharactersResponse)
    async def list_characters(session_id: str, world_id: str | None = None):
        """List available characters for the logged-in user."""
        user_id, _, role = validate_session(session_id)
        if world_id:
            available_worlds = get_available_worlds(user_id, role)
            if world_id not in {world["id"] for world in available_worlds}:
                raise HTTPException(status_code=403, detail="World access denied")
        characters = database.get_user_characters(user_id, world_id=world_id)
        return CharactersResponse(characters=characters)

    @api.post("/characters/select", response_model=SelectCharacterResponse)
    async def select_character(request: SelectCharacterRequest):
        """Select a character for the current session."""
        user_id, _, role = validate_session(request.session_id)
        character = database.get_character_by_id(request.character_id)
        if not character or character.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="Character not found for this user")

        world_id = request.world_id or character.get("world_id")
        if not world_id:
            raise HTTPException(status_code=400, detail="World id required")

        available_worlds = get_available_worlds(user_id, role)
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

    @api.post("/change-password")
    async def change_password(request: ChangePasswordRequest):
        """Change current user's password with policy enforcement."""
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

    return api
