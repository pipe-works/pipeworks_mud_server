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
    CreateCharacterResponse,
    LoginDirectRequest,
    LoginDirectResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    PlayerCreateCharacterRequest,
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
from mud_server.db import facade as database
from mud_server.db.errors import DatabaseError
from mud_server.services.character_provisioning import provision_generated_character_for_user

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

        try:
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
        except DatabaseError as exc:
            logger.exception("Login failed due to database error for username '%s'", username)
            raise HTTPException(
                status_code=500, detail="Authentication service unavailable."
            ) from exc

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

        if config.registration.account_registration_mode != "open":
            raise HTTPException(
                status_code=403,
                detail="Account registration is currently closed.",
            )

        username = request.username.strip()
        password = request.password
        password_confirm = request.password_confirm

        # Validate username
        if not username or len(username) < 2 or len(username) > 20:
            raise HTTPException(status_code=400, detail="Username must be 2-20 characters")

        try:
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

            guest_expires_at = (datetime.now(UTC) + timedelta(hours=24)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
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
            raise HTTPException(
                status_code=500, detail="Failed to create account. Please try again."
            )
        except DatabaseError as exc:
            logger.exception("Account registration failed due to database error for '%s'", username)
            raise HTTPException(
                status_code=500, detail="Account registration store failure."
            ) from exc

    @api.post("/register-guest", response_model=RegisterGuestResponse)
    async def register_guest(request: RegisterGuestRequest):
        """Register a new temporary guest account with a server-generated username."""
        from datetime import UTC, datetime, timedelta
        from secrets import randbelow

        from mud_server.api.password_policy import PolicyLevel, validate_password_strength

        try:
            if not config.registration.guest_registration_enabled:
                raise HTTPException(
                    status_code=403,
                    detail="Guest registration is currently disabled.",
                )

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

            guest_expires_at = (datetime.now(UTC) + timedelta(hours=24)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if not database.create_user_with_password(
                username,
                password,
                role="player",
                account_origin="visitor",
                is_guest=True,
                guest_expires_at=guest_expires_at,
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
            entity_state, entity_state_error = _fetch_local_axis_snapshot_for_character(
                character_id
            )

            # Optional fallback: if local snapshot data is unavailable, attempt to
            # fetch from the external entity integration when enabled.
            if entity_state is None:
                external_state, external_error = _fetch_entity_state_for_character(
                    seed=character_id
                )
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
                    "Temporary guest account created successfully! "
                    f"You can now login as {username}."
                ),
                username=username,
                character_id=character_id,
                character_name=character_name,
                world_id=world_id,
                entity_state=entity_state,
                entity_state_error=entity_state_error,
            )
        except DatabaseError as exc:
            logger.exception("Guest registration failed due to database error")
            raise HTTPException(
                status_code=500, detail="Guest registration store failure."
            ) from exc

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
        try:
            user_id, username, role = validate_session(session_id)
            if world_id:
                if not database.can_user_access_world(user_id, world_id, role=role):
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
        except DatabaseError as exc:
            logger.exception("Character listing failed due to database error")
            raise HTTPException(status_code=500, detail="Character listing unavailable.") from exc

    @api.post("/characters/select", response_model=SelectCharacterResponse)
    async def select_character(request: SelectCharacterRequest):
        """Select a character for the current session."""
        try:
            user_id, _, role = validate_session(request.session_id)
            character = database.get_character_by_id(request.character_id)
            if not character or character.get("user_id") != user_id:
                raise HTTPException(status_code=404, detail="Character not found for this user")

            world_id = request.world_id or character.get("world_id")
            if not world_id:
                raise HTTPException(status_code=400, detail="World id required")

            if not database.can_user_access_world(user_id, world_id, role=role):
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
        except DatabaseError as exc:
            logger.exception(
                "Character selection failed due to database error (character_id=%s)",
                request.character_id,
            )
            raise HTTPException(status_code=500, detail="Character selection failed.") from exc

    @api.post("/characters/create", response_model=CreateCharacterResponse)
    async def create_character(request: PlayerCreateCharacterRequest):
        """
        Create a generated-name character for the logged-in account.

        Temporary rollout constraints:
        - Player self-create is globally toggleable via config.
        - World policy controls open/invite access and per-world slot limits.
        - ``naming_mode=manual`` is intentionally restricted to admin/superuser
          operations in this phase.
        """
        try:
            user_id, username, role = validate_session(request.session_id)
            world_id = request.world_id.strip()
            if not world_id:
                raise HTTPException(status_code=400, detail="world_id is required")

            if not config.character_creation.player_self_create_enabled:
                raise HTTPException(
                    status_code=403,
                    detail="Player self-service character creation is disabled.",
                )

            access = database.get_world_access_decision(user_id, world_id, role=role)
            if access.reason == "world_not_found":
                raise HTTPException(status_code=404, detail=f"World '{world_id}' not found")
            if access.reason == "world_inactive":
                raise HTTPException(status_code=409, detail=f"World '{world_id}' is inactive")
            if not access.can_access:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"World '{world_id}' requires an invite. "
                        "Ask an admin to grant world access."
                    ),
                )

            # Temporary policy guardrail:
            # manual naming remains an elevated/admin-only capability for now.
            if access.naming_mode != "generated" and role not in {"admin", "superuser"}:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"World '{world_id}' currently requires admin-managed character naming."
                    ),
                )

            if not access.can_create and access.reason == "slot_limit_reached":
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"No character slots remain in '{world_id}' for account '{username}'. "
                        f"{access.current_character_count}/{access.slot_limit_per_account} used."
                    ),
                )

            provisioning = provision_generated_character_for_user(
                user_id=user_id,
                world_id=world_id,
            )
            if not provisioning.success:
                if provisioning.reason == "slot_limit_reached":
                    raise HTTPException(status_code=409, detail=provisioning.message)
                if provisioning.reason == "name_generation_failed":
                    raise HTTPException(status_code=502, detail=provisioning.message)
                raise HTTPException(status_code=409, detail=provisioning.message)

            return CreateCharacterResponse(
                success=True,
                message=f"Character '{provisioning.character_name}' created for '{username}'.",
                character_id=provisioning.character_id,
                character_name=provisioning.character_name,
                world_id=provisioning.world_id,
                seed=provisioning.seed,
                entity_state=provisioning.entity_state,
                entity_state_error=provisioning.entity_state_error,
            )
        except DatabaseError as exc:
            logger.exception("Player character creation failed due to database error")
            raise HTTPException(status_code=500, detail="Character creation unavailable.") from exc

    @api.post("/change-password")
    async def change_password(request: ChangePasswordRequest):
        """Change current user's password with policy enforcement."""
        from mud_server.api.password_policy import PolicyLevel, validate_password_strength

        _, username, _ = validate_session(request.session_id)

        try:
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
            raise HTTPException(status_code=500, detail="Failed to change password")
        except DatabaseError as exc:
            logger.exception("Password change failed due to database error for '%s'", username)
            raise HTTPException(status_code=500, detail="Password update unavailable.") from exc

    return api
