"""Authentication and account management endpoints."""

import logging
import re
import uuid
from typing import Any

import requests
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

logger = logging.getLogger(__name__)


def _is_legacy_default_character_name(username: str, character_name: str) -> bool:
    """
    Return True when ``character_name`` matches the legacy auto-seeded pattern.

    Historical account creation created a bootstrap character named
    ``<username>_char`` (with optional numeric suffix when collisions occurred).
    During the account-first migration we keep these rows for compatibility, but
    some clients (for example the play shell selector) should prefer explicit
    user-created characters when both exist.

    Args:
        username: Owning account username.
        character_name: Candidate character name.

    Returns:
        True when the name matches ``<username>_char(_N)?`` exactly.
    """
    escaped_username = re.escape(username)
    pattern = rf"^{escaped_username}_char(?:_\d+)?$"
    return re.match(pattern, character_name) is not None


def _fetch_entity_state_for_character(seed: int) -> tuple[dict[str, Any] | None, str | None]:
    """
    Fetch entity-state payload for a newly created character.

    The entity API is an optional integration. Registration stays available even
    if the upstream service is unreachable, malformed, or disabled by config.

    Args:
        seed: Deterministic seed used for entity-state generation.

    Returns:
        Tuple of (entity_state_payload, error_message). When successful,
        error_message is None. When unavailable, payload is None.
    """
    if not config.integrations.entity_state_enabled:
        return None, None

    base_url = config.integrations.entity_state_base_url.strip().rstrip("/")
    if not base_url:
        return None, "Entity state integration is enabled but no base URL is configured."

    endpoint = f"{base_url}/api/entity"
    payload = {
        "seed": seed,
        "include_prompts": config.integrations.entity_state_include_prompts,
    }
    timeout = config.integrations.entity_state_timeout_seconds

    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
        if response.status_code != 200:
            return None, f"Entity state API returned HTTP {response.status_code}."
        body = response.json()
        if not isinstance(body, dict):
            return None, "Entity state API returned a non-object payload."
        return body, None
    except requests.exceptions.RequestException as exc:
        logger.warning("Entity state API request failed: %s", exc)
        return None, "Entity state API unavailable."
    except ValueError:
        logger.warning("Entity state API returned invalid JSON.")
        return None, "Entity state API returned invalid JSON."


def _fetch_local_axis_snapshot_for_character(
    character_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Fetch locally seeded axis snapshot state for a character.

    Character creation seeds axis scores and a snapshot in the MUD database.
    This local snapshot is the preferred source for onboarding UI because it
    is canonical to gameplay mechanics and available even when external
    integrations are unavailable.

    Compatibility note:
        Callers should treat snapshot keys as forward-compatible. New
        top-level metadata (for example, axis grouping fields) may be added
        without removing existing keys such as ``axes``.

    Args:
        character_id: Newly created character identifier.

    Returns:
        Tuple of (current_state_snapshot, error_message).
    """
    axis_state = database.get_character_axis_state(character_id)
    if axis_state is None:
        return None, "Character axis state unavailable."

    current_state = axis_state.get("current_state")
    if isinstance(current_state, dict):
        return current_state, None

    return None, "Character axis snapshot missing."


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
        DEPRECATED: direct world login path.

        Architectural decision (Option A / breaking change):
            Accounts must always authenticate into an account-only session
            first, then explicitly select a character via `/characters/select`
            before entering gameplay endpoints.

        This endpoint is retained temporarily only to return a deterministic
        migration error for older clients.
        """
        _ = request
        _ = http_request
        raise HTTPException(
            status_code=410,
            detail=(
                "Direct world login is deprecated. Use /login to create an account session, "
                "then call /characters/select to enter a world."
            ),
        )

    # =========================================================================
    # SIGNUP ARCHITECTURE NOTE (FOR FUTURE PERMANENT ACCOUNTS)
    # -------------------------------------------------------------------------
    # Current guest onboarding in /register-guest already implements the core
    # provisioning sequence we want for permanent signup:
    #   1) create account
    #   2) create initial character
    #   3) seed axis state/snapshot
    #   4) return onboarding payload (character_id/world_id/entity_state)
    #
    # When permanent signup is added, avoid duplicating this flow in a second
    # code path. Instead, extract shared provisioning into one internal helper
    # and vary only account policy fields:
    #   - guest: generated username, is_guest=true, guest_expires_at set
    #   - permanent: user-chosen identity, is_guest=false, no guest expiry
    #
    # Keeping one provisioning path prevents drift between guest and permanent
    # registration behavior and keeps UI onboarding payloads consistent.
    # =========================================================================
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
                    "Temporary account created successfully! "
                    f"You can now login as {username}. "
                    "Character creation is a separate step."
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

        # Resolve the freshly-created character id so onboarding consumers can
        # bind deterministic external entity-state generation to this character.
        character = database.get_character_by_name(character_name)
        if character is None:
            database.delete_user(username)
            raise HTTPException(status_code=500, detail="Failed to resolve created character")
        character_id = int(character["id"])
        world_id = str(character.get("world_id") or config.worlds.default_world_id)

        # Prefer local snapshot state from the MUD DB so onboarding reflects
        # the same canonical state used by gameplay mechanics.
        entity_state, entity_state_error = _fetch_local_axis_snapshot_for_character(character_id)

        # Optional fallback: if local snapshot data is unavailable, attempt to
        # fetch from the external entity integration when enabled.
        if entity_state is None:
            external_state, external_error = _fetch_entity_state_for_character(seed=character_id)
            if external_state is not None:
                entity_state = external_state
                entity_state_error = None
            elif external_error:
                if entity_state_error:
                    entity_state_error = f"{entity_state_error} {external_error}"
                else:
                    entity_state_error = external_error

        return RegisterGuestResponse(
            success=True,
            message=(
                "Temporary guest account created successfully! " f"You can now login as {username}."
            ),
            username=username,
            character_id=character_id,
            character_name=character_name,
            world_id=world_id,
            entity_state=entity_state,
            entity_state_error=entity_state_error,
        )

    @api.post("/logout")
    async def logout(request: LogoutRequest):
        """Logout user and remove session from database."""
        _, username, _ = validate_session(request.session_id)
        remove_session(request.session_id)
        return {"success": True, "message": f"Goodbye, {username}!"}

    @api.get("/characters", response_model=CharactersResponse)
    async def list_characters(
        session_id: str,
        world_id: str | None = None,
        exclude_legacy_defaults: bool = False,
    ):
        """
        List available characters for the logged-in user.

        Args:
            session_id: Account session identifier.
            world_id: Optional world id filter.
            exclude_legacy_defaults: When true, hide legacy auto-seeded
                ``<username>_char`` entries if at least one non-legacy
                character exists in the result set.
        """
        user_id, username, role = validate_session(session_id)
        if world_id:
            available_worlds = get_available_worlds(user_id, role)
            if world_id not in {world["id"] for world in available_worlds}:
                raise HTTPException(status_code=403, detail="World access denied")
        characters = database.get_user_characters(user_id, world_id=world_id)

        if exclude_legacy_defaults and characters:
            non_legacy_characters = [
                row
                for row in characters
                if not _is_legacy_default_character_name(username, str(row.get("name", "")))
            ]
            if non_legacy_characters:
                characters = non_legacy_characters

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
