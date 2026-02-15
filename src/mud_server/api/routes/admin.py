"""Admin endpoints for database and user management."""

import logging
import os
import signal
from secrets import randbelow
from typing import Any

import requests
from fastapi import APIRouter, HTTPException

from mud_server.api.auth import validate_session_for_game, validate_session_with_permission
from mud_server.api.models import (
    CharacterAxisEvent,
    CreateCharacterRequest,
    CreateCharacterResponse,
    CreateUserRequest,
    CreateUserResponse,
    DatabaseCharacterAxisEventsResponse,
    DatabaseCharacterAxisStateResponse,
    DatabaseChatResponse,
    DatabaseConnectionsResponse,
    DatabasePlayerLocationsResponse,
    DatabasePlayersResponse,
    DatabaseSchemaResponse,
    DatabaseSchemaTable,
    DatabaseSessionsResponse,
    DatabaseTableInfo,
    DatabaseTableRowsResponse,
    DatabaseTablesResponse,
    KickSessionRequest,
    KickSessionResponse,
    ManageCharacterRequest,
    ManageCharacterResponse,
    ServerStopRequest,
    ServerStopResponse,
    UserManagementRequest,
    UserManagementResponse,
)
from mud_server.api.permissions import Permission, can_manage_role
from mud_server.api.routes.utils import resolve_zone_id
from mud_server.config import config
from mud_server.core.engine import GameEngine
from mud_server.db import database

logger = logging.getLogger(__name__)


def _generate_provisioning_seed() -> int:
    """
    Generate a replayable, non-zero seed for provisioning flows.

    We intentionally use ``secrets.randbelow`` rather than the global
    ``random`` module to keep provisioning entropy isolated from any
    deterministic RNG state that gameplay systems may rely on.
    """
    return randbelow(2_147_483_647) + 1


def _fetch_generated_name(
    seed: int, *, class_key: str = "first_name"
) -> tuple[str | None, str | None]:
    """
    Request one character name from the external name-generation API.

    Args:
        seed: Deterministic seed sent to the upstream service.
        class_key: Name-generation class key (for example "first_name").

    Returns:
        Tuple ``(name, error_message)``. On success, error is ``None``.
    """
    if not config.integrations.namegen_enabled:
        return None, "Name generation integration is disabled."

    base_url = config.integrations.namegen_base_url.strip().rstrip("/")
    if not base_url:
        return None, "Name generation integration is enabled but no base URL is configured."

    endpoint = f"{base_url}/api/generate"
    payload = {
        "class_key": class_key,
        "package_id": 1,
        "syllable_key": "all",
        "generation_count": 1,
        "unique_only": True,
        "output_format": "json",
        "render_style": "title",
        "seed": seed,
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=config.integrations.namegen_timeout_seconds,
        )
        if response.status_code != 200:
            return None, f"Name generation API returned HTTP {response.status_code}."
        body = response.json()
        if not isinstance(body, dict):
            return None, "Name generation API returned a non-object payload."
        names = body.get("names")
        if not isinstance(names, list) or not names or not isinstance(names[0], str):
            return None, "Name generation API did not return a valid name."
        name = names[0].strip()
        if not name:
            return None, "Name generation API returned an empty name."
        return name, None
    except requests.exceptions.RequestException as exc:
        logger.warning("Name generation API request failed: %s", exc)
        return None, "Name generation API unavailable."
    except ValueError:
        logger.warning("Name generation API returned invalid JSON.")
        return None, "Name generation API returned invalid JSON."


def _fetch_generated_full_name(seed: int) -> tuple[str | None, str | None]:
    """
    Generate a deterministic ``first last`` character name for provisioning.

    The same base seed is used for both lookups with an offset for the surname.
    This keeps retries deterministic while avoiding global RNG mutation.

    Args:
        seed: Base deterministic seed for the provisioning attempt.

    Returns:
        Tuple ``(full_name, error_message)``.
    """
    first_name, first_error = _fetch_generated_name(seed, class_key="first_name")
    if first_name is None:
        return None, first_error or "Unable to generate first name."

    # Use a stable offset so the "surname stream" remains deterministic per attempt.
    last_name, last_error = _fetch_generated_name(seed + 1, class_key="last_name")
    if last_name is None:
        return None, last_error or "Unable to generate last name."

    full_name = f"{first_name.strip()} {last_name.strip()}".strip()
    if " " not in full_name:
        return None, "Name generation API returned an invalid full name."
    return full_name, None


def _fetch_entity_state_for_seed(seed: int) -> tuple[dict[str, Any] | None, str | None]:
    """
    Fetch an entity-state payload for a provisioning seed.

    Args:
        seed: Deterministic seed sent to the entity API.

    Returns:
        Tuple ``(payload, error_message)``. On success, error is ``None``.
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

    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=config.integrations.entity_state_timeout_seconds,
        )
        if response.status_code != 200:
            return None, f"Entity state API returned HTTP {response.status_code}."
        body = response.json()
        if not isinstance(body, dict):
            return None, "Entity state API returned a non-object payload."
        return body, None
    except requests.exceptions.RequestException as exc:
        logger.warning("Entity state API request failed during admin provisioning: %s", exc)
        return None, "Entity state API unavailable."
    except ValueError:
        logger.warning("Entity state API returned invalid JSON during admin provisioning.")
        return None, "Entity state API returned invalid JSON."


def router(engine: GameEngine) -> APIRouter:
    """Build the admin router with access to the game engine."""
    api = APIRouter()

    @api.get("/admin/database/players", response_model=DatabasePlayersResponse)
    async def get_database_players(session_id: str):
        """Get all users from database with details (Requires VIEW_LOGS permission)."""
        _, _, _ = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        users = database.get_all_users_detailed()
        return DatabasePlayersResponse(players=users)

    @api.get("/admin/database/connections", response_model=DatabaseConnectionsResponse)
    async def get_database_connections(session_id: str):
        """Get active session connections with activity age (Admin only)."""
        _, _, _ = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
        try:
            _, _, _, _, _, world_id = validate_session_for_game(session_id)
        except HTTPException:
            world_id = None

        connections = database.get_active_connections(world_id=world_id)
        return DatabaseConnectionsResponse(connections=connections)

    @api.get("/admin/database/player-locations", response_model=DatabasePlayerLocationsResponse)
    async def get_database_player_locations(session_id: str):
        """Get character locations with zone context (Admin only)."""
        _, _, _ = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
        try:
            _, _, _, _, _, world_id = validate_session_for_game(session_id)
        except HTTPException:
            world_id = None

        locations = []
        for location in database.get_character_locations(world_id=world_id):
            room_id = location.get("room_id")
            zone_id = resolve_zone_id(engine, room_id, world_id)
            locations.append({**location, "zone_id": zone_id})

        return DatabasePlayerLocationsResponse(locations=locations)

    @api.get(
        "/admin/characters/{character_id}/axis-state",
        response_model=DatabaseCharacterAxisStateResponse,
    )
    async def get_character_axis_state(session_id: str, character_id: int):
        """Get axis scores and snapshots for a character (Admin only)."""
        _, _username, _role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        axis_state = database.get_character_axis_state(character_id)
        if not axis_state:
            raise HTTPException(status_code=404, detail="Character not found")

        return DatabaseCharacterAxisStateResponse(**axis_state)

    @api.get(
        "/admin/characters/{character_id}/axis-events",
        response_model=DatabaseCharacterAxisEventsResponse,
    )
    async def get_character_axis_events(session_id: str, character_id: int, limit: int = 50):
        """Get recent axis events for a character (Admin only)."""
        _, _username, _role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        events = [
            CharacterAxisEvent(**event)
            for event in database.get_character_axis_events(character_id, limit=limit)
        ]
        return DatabaseCharacterAxisEventsResponse(character_id=character_id, events=events)

    @api.post("/admin/session/kick", response_model=KickSessionResponse)
    async def kick_session(request: KickSessionRequest):
        """Force-disconnect an active session (Admin/Superuser only)."""
        _, _, _ = validate_session_with_permission(request.session_id, Permission.KICK_USERS)

        removed = database.remove_session_by_id(request.target_session_id)
        if removed:
            return KickSessionResponse(success=True, message="Session disconnected")
        return KickSessionResponse(success=False, message="Session not found")

    @api.get("/admin/database/tables", response_model=DatabaseTablesResponse)
    async def get_database_tables(session_id: str):
        """Get list of database tables with schema details (Admin only)."""
        _, _username, _role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        tables = [DatabaseTableInfo(**table) for table in database.list_tables()]
        return DatabaseTablesResponse(tables=tables)

    @api.get("/admin/database/schema", response_model=DatabaseSchemaResponse)
    async def get_database_schema(session_id: str):
        """Get database schema relationships (Admin only)."""
        _, _username, _role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        tables = [DatabaseSchemaTable(**table) for table in database.get_schema_map()]
        return DatabaseSchemaResponse(tables=tables)

    @api.get("/admin/database/table/{table_name}", response_model=DatabaseTableRowsResponse)
    async def get_database_table_rows(session_id: str, table_name: str, limit: int = 100):
        """Get rows from a specific database table (Admin only)."""
        _, _username, _role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        try:
            columns, rows = database.get_table_rows(table_name, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return DatabaseTableRowsResponse(table=table_name, columns=columns, rows=rows)

    @api.get("/admin/database/sessions", response_model=DatabaseSessionsResponse)
    async def get_database_sessions(session_id: str):
        """Get all active sessions from the database (Admin only)."""
        _, _username, _role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
        try:
            _, _, _, _, _, world_id = validate_session_for_game(session_id)
        except HTTPException:
            world_id = None

        sessions = database.get_all_sessions(world_id=world_id)
        return DatabaseSessionsResponse(sessions=sessions)

    @api.get("/admin/database/chat-messages", response_model=DatabaseChatResponse)
    async def get_database_chat_messages(session_id: str, limit: int = 100):
        """Get recent chat messages from the database (Admin only)."""
        _, _username, _role = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
        try:
            _, _, _, _, _, world_id = validate_session_for_game(session_id)
        except HTTPException:
            world_id = None

        messages = database.get_all_chat_messages(limit=limit, world_id=world_id)
        return DatabaseChatResponse(messages=messages)

    @api.post("/admin/user/manage", response_model=UserManagementResponse)
    async def manage_user(request: UserManagementRequest):
        """Manage users: change role, ban/deactivate, unban, delete, or change password."""
        action = request.action.lower()
        if action == "deactivate":
            action = "ban"

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

        _, username, role = validate_session_with_permission(
            request.session_id, required_permission
        )

        target_username = request.target_username
        if not database.user_exists(target_username):
            raise HTTPException(status_code=404, detail=f"User '{target_username}' not found")

        target_role = database.get_user_role(target_username)
        if not target_role:
            raise HTTPException(status_code=404, detail="Target user not found")

        if username == target_username and action != "change_password":
            raise HTTPException(status_code=400, detail="Cannot manage your own account")

        if not can_manage_role(role, target_role):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions to manage user with role '{target_role}'",
            )

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
            raise HTTPException(status_code=500, detail="Failed to change role")

        if action == "ban":
            if database.deactivate_user(target_username):
                user_id = database.get_user_id(target_username)
                if user_id:
                    database.remove_sessions_for_user(user_id)

                return UserManagementResponse(
                    success=True, message=f"Successfully banned {target_username}"
                )
            raise HTTPException(status_code=500, detail="Failed to ban user")

        if action == "delete":
            if role != "superuser":
                raise HTTPException(
                    status_code=403,
                    detail="Only superusers may permanently delete users",
                )

            if database.delete_user(target_username):
                return UserManagementResponse(
                    success=True, message=f"Successfully deleted {target_username}"
                )
            raise HTTPException(status_code=500, detail="Failed to delete user")

        if action == "unban":
            if database.activate_user(target_username):
                return UserManagementResponse(
                    success=True, message=f"Successfully unbanned {target_username}"
                )
            raise HTTPException(status_code=500, detail="Failed to unban user")

        if action == "change_password":
            new_password = request.new_password
            if not new_password:
                raise HTTPException(
                    status_code=400, detail="new_password is required for change_password action"
                )

            if len(new_password) < 8:
                raise HTTPException(
                    status_code=400, detail="Password must be at least 8 characters long"
                )

            if database.change_password_for_user(target_username, new_password):
                return UserManagementResponse(
                    success=True, message=f"Successfully changed password for {target_username}"
                )
            raise HTTPException(status_code=500, detail="Failed to change password")

        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid action '{action}'. Valid actions: change_role, "
                "ban, deactivate, unban, delete, change_password"
            ),
        )

    @api.post("/admin/user/create", response_model=CreateUserResponse)
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

        if not username or len(username) < 2 or len(username) > 20:
            raise HTTPException(status_code=400, detail="Username must be 2-20 characters")

        valid_roles = {"player", "worldbuilder", "admin", "superuser"}
        if role not in valid_roles:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role. Valid roles: {', '.join(sorted(valid_roles))}",
            )

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

        if database.user_exists(username):
            raise HTTPException(status_code=400, detail="Username already taken")

        if password != password_confirm:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        result = validate_password_strength(password, level=PolicyLevel.STANDARD)
        if not result.is_valid:
            error_detail = " ".join(result.errors)
            raise HTTPException(status_code=400, detail=error_detail)

        if database.create_user_with_password(
            username, password, role=role, account_origin=creator_role
        ):
            return CreateUserResponse(
                success=True,
                message=f"User '{username}' created with role '{role}'.",
            )

        raise HTTPException(status_code=500, detail="Failed to create account. Please try again.")

    @api.post("/admin/user/create-character", response_model=CreateCharacterResponse)
    async def create_character(request: CreateCharacterRequest):
        """
        Provision a new character for an existing account.

        Flow:
        1. Validate caller permission + target account/world.
        2. Generate a non-zero provisioning seed.
        3. Mint a full ``first last`` character name from namegen (retry on collisions).
        4. Create character in DB and seed baseline axis snapshot.
        5. Fetch entity profile and apply axis deltas through the event ledger.
        """
        _, actor_username, actor_role = validate_session_with_permission(
            request.session_id,
            Permission.CREATE_USERS,
        )

        target_username = request.target_username.strip()
        world_id = request.world_id.strip()
        if not target_username:
            raise HTTPException(status_code=400, detail="target_username is required")
        if not world_id:
            raise HTTPException(status_code=400, detail="world_id is required")

        if not database.user_exists(target_username):
            raise HTTPException(status_code=404, detail=f"User '{target_username}' not found")

        target_role = database.get_user_role(target_username)
        if not target_role:
            raise HTTPException(status_code=404, detail=f"Role not found for '{target_username}'")

        # Follow the same role hierarchy guardrails as other admin-management
        # operations, but permit self-service character creation.
        if actor_username != target_username and not can_manage_role(actor_role, target_role):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions to manage user with role '{target_role}'",
            )

        target_user_id = database.get_user_id(target_username)
        if target_user_id is None:
            raise HTTPException(status_code=404, detail=f"User '{target_username}' not found")

        world = database.get_world_by_id(world_id)
        if world is None:
            raise HTTPException(status_code=404, detail=f"World '{world_id}' not found")
        if not world.get("is_active", False):
            raise HTTPException(status_code=409, detail=f"World '{world_id}' is inactive")

        max_attempts = 8
        base_seed = _generate_provisioning_seed()
        chosen_name: str | None = None
        chosen_seed: int | None = None

        for attempt in range(max_attempts):
            candidate_seed = base_seed + attempt
            generated_name, name_error = _fetch_generated_full_name(candidate_seed)
            if generated_name is None:
                raise HTTPException(
                    status_code=502,
                    detail=name_error or "Unable to generate character name.",
                )
            if database.create_character_for_user(
                target_user_id,
                generated_name,
                world_id=world_id,
                state_seed=candidate_seed,
            ):
                chosen_name = generated_name
                chosen_seed = candidate_seed
                break

        if chosen_name is None or chosen_seed is None:
            raise HTTPException(
                status_code=409,
                detail="Unable to allocate a unique character name. Try again.",
            )

        character = database.get_character_by_name(chosen_name)
        if character is None:
            raise HTTPException(status_code=500, detail="Character creation did not persist")
        character_id = int(character["id"])

        entity_state, entity_state_error = _fetch_entity_state_for_seed(chosen_seed)
        if entity_state is not None:
            try:
                database.apply_entity_state_to_character(
                    character_id=character_id,
                    world_id=world_id,
                    entity_state=entity_state,
                    seed=chosen_seed,
                )
            except Exception:  # nosec B110 - surfaced as controlled API error
                logger.exception(
                    "Failed to apply entity-state payload for character %s", character_id
                )
                entity_state_error = "Entity state axis seeding failed."

        return CreateCharacterResponse(
            success=True,
            message=f"Character '{chosen_name}' created for '{target_username}'.",
            character_id=character_id,
            character_name=chosen_name,
            world_id=world_id,
            seed=chosen_seed,
            entity_state=entity_state,
            entity_state_error=entity_state_error,
        )

    @api.post("/admin/character/manage", response_model=ManageCharacterResponse)
    async def manage_character(request: ManageCharacterRequest):
        """
        Tombstone or permanently delete a character (superuser only).

        Security model:
        - We gate access behind ``MANAGE_USERS`` (superuser permission).
        - We also assert the resolved role is ``superuser`` for explicitness.

        Operational behavior:
        - Any sessions currently bound to the character are removed first.
        - ``tombstone`` preserves historical audit rows while detaching ownership.
        - ``delete`` permanently removes the character and cascades dependent rows.
        """
        _, _actor_username, actor_role = validate_session_with_permission(
            request.session_id,
            Permission.MANAGE_USERS,
        )
        if actor_role != "superuser":
            raise HTTPException(
                status_code=403,
                detail="Only superusers may remove characters.",
            )

        action = request.action.strip().lower()
        if action not in {"tombstone", "delete"}:
            raise HTTPException(
                status_code=400,
                detail="Invalid action. Valid actions: tombstone, delete",
            )

        character = database.get_character_by_id(request.character_id)
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found")

        # Ensure no in-world session remains attached to a soon-to-be removed
        # character identity. This avoids stale gameplay sessions.
        database.remove_sessions_for_character(request.character_id)

        if action == "tombstone":
            if character.get("user_id") is None:
                raise HTTPException(status_code=409, detail="Character is already tombstoned")
            if not database.tombstone_character(request.character_id):
                raise HTTPException(status_code=404, detail="Character not found")
            return ManageCharacterResponse(
                success=True,
                message=f"Character '{character['name']}' tombstoned.",
                character_id=request.character_id,
                action="tombstone",
            )

        if not database.delete_character(request.character_id):
            raise HTTPException(status_code=404, detail="Character not found")
        return ManageCharacterResponse(
            success=True,
            message=f"Character '{character['name']}' permanently deleted.",
            character_id=request.character_id,
            action="delete",
        )

    @api.post("/admin/server/stop", response_model=ServerStopResponse)
    async def stop_server(request: ServerStopRequest):
        """Stop the server (Admin and Superuser only)."""
        _, username, _role = validate_session_with_permission(
            request.session_id, Permission.STOP_SERVER
        )

        import asyncio

        async def shutdown():
            await asyncio.sleep(0.5)
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.create_task(shutdown())

        return ServerStopResponse(
            success=True,
            message=f"Server shutdown initiated by {username}. Server will stop in 0.5 seconds.",
        )

    return api
