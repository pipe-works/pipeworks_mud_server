"""Admin endpoints for database and user management."""

import os
import signal

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
    DatabaseWorldStatusResponse,
    DatabaseWorldStatusRow,
    KickCharacterRequest,
    KickCharacterResponse,
    KickSessionRequest,
    KickSessionResponse,
    ManageCharacterRequest,
    ManageCharacterResponse,
    ServerStopRequest,
    ServerStopResponse,
    UserManagementRequest,
    UserManagementResponse,
    WorldActiveCharacterSession,
)
from mud_server.api.permissions import Permission, can_manage_role
from mud_server.api.routes.utils import resolve_zone_id
from mud_server.core.engine import GameEngine
from mud_server.db import facade as database
from mud_server.db.errors import DatabaseError
from mud_server.services.character_provisioning import provision_generated_character_for_user


def router(engine: GameEngine) -> APIRouter:
    """Build the admin router with access to the game engine."""
    api = APIRouter()

    @api.get("/admin/database/players", response_model=DatabasePlayersResponse)
    async def get_database_players(session_id: str):
        """Get all users from database with details (Requires VIEW_LOGS permission)."""
        _, _, _ = validate_session_with_permission(session_id, Permission.VIEW_LOGS)

        users = database.get_all_users_detailed()
        return DatabasePlayersResponse(players=users)

    @api.get("/admin/database/worlds", response_model=DatabaseWorldStatusResponse)
    async def get_database_worlds(session_id: str):
        """
        Get world operations rows with live online/session details (Admin only).

        This endpoint is purpose-built for the WebUI worlds operations table.
        It exposes per-world online state and kickable character session rows.
        """
        _, _, _ = validate_session_with_permission(session_id, Permission.VIEW_LOGS)
        worlds = []
        for row in database.get_world_admin_rows():
            active_characters = [
                WorldActiveCharacterSession(**entry) for entry in row.get("active_characters", [])
            ]
            worlds.append(
                DatabaseWorldStatusRow(
                    world_id=row["world_id"],
                    name=row["name"],
                    description=row["description"] or "",
                    is_active=bool(row["is_active"]),
                    is_online=bool(row["is_online"]),
                    active_session_count=int(row["active_session_count"]),
                    active_character_count=int(row["active_character_count"]),
                    last_activity=row.get("last_activity"),
                    active_characters=active_characters,
                )
            )
        return DatabaseWorldStatusResponse(worlds=worlds)

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

        try:
            events = [
                CharacterAxisEvent(**event)
                for event in database.get_character_axis_events(character_id, limit=limit)
            ]
            return DatabaseCharacterAxisEventsResponse(character_id=character_id, events=events)
        except DatabaseError as exc:
            raise HTTPException(status_code=500, detail="Character events unavailable") from exc

    @api.post("/admin/session/kick", response_model=KickSessionResponse)
    async def kick_session(request: KickSessionRequest):
        """Force-disconnect an active session (Admin/Superuser only)."""
        try:
            _, _, _ = validate_session_with_permission(request.session_id, Permission.KICK_USERS)

            removed = database.remove_session_by_id(request.target_session_id)
            if removed:
                return KickSessionResponse(success=True, message="Session disconnected")
            return KickSessionResponse(success=False, message="Session not found")
        except DatabaseError as exc:
            raise HTTPException(status_code=500, detail="Failed to kick session") from exc

    @api.post("/admin/character/kick", response_model=KickCharacterResponse)
    async def kick_character(request: KickCharacterRequest):
        """
        Disconnect all active sessions for a target character.

        This supports world-operations tooling where moderators target a
        character identity rather than a raw session id.
        """
        try:
            _, _, _ = validate_session_with_permission(request.session_id, Permission.KICK_USERS)

            character = database.get_character_by_id(request.character_id)
            if character is None:
                raise HTTPException(status_code=404, detail="Character not found")

            removed_count = database.remove_sessions_for_character_count(request.character_id)
            if removed_count > 0:
                return KickCharacterResponse(
                    success=True,
                    message=f"Disconnected {removed_count} session(s) for {character['name']}.",
                    removed_sessions=removed_count,
                )
            return KickCharacterResponse(
                success=False,
                message=f"No active sessions found for {character['name']}.",
                removed_sessions=0,
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=500, detail="Failed to kick character") from exc

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

        try:
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
                        try:
                            database.remove_sessions_for_user(user_id)
                        except DatabaseError as exc:
                            raise HTTPException(
                                status_code=500, detail="Failed to ban user"
                            ) from exc

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
                        status_code=400,
                        detail="new_password is required for change_password action",
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
        except DatabaseError as exc:
            raise HTTPException(status_code=500, detail="User management unavailable") from exc

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

        try:
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
                    message=(
                        f"User '{username}' created with role '{role}'. "
                        "No character was provisioned automatically."
                    ),
                )

            raise HTTPException(
                status_code=500, detail="Failed to create account. Please try again."
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=500, detail="User creation unavailable") from exc

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
        try:
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
                raise HTTPException(
                    status_code=404, detail=f"Role not found for '{target_username}'"
                )

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

            provisioning = provision_generated_character_for_user(
                user_id=target_user_id,
                world_id=world_id,
            )
            if not provisioning.success:
                if provisioning.reason == "slot_limit_reached":
                    raise HTTPException(status_code=409, detail=provisioning.message)
                if provisioning.reason == "name_generation_failed":
                    raise HTTPException(status_code=502, detail=provisioning.message)
                raise HTTPException(status_code=409, detail=provisioning.message)

            if provisioning.character_id is None or provisioning.character_name is None:
                raise HTTPException(
                    status_code=500, detail="Character provisioning returned no identity"
                )

            return CreateCharacterResponse(
                success=True,
                message=(
                    f"Character '{provisioning.character_name}' created for '{target_username}'."
                ),
                character_id=provisioning.character_id,
                character_name=provisioning.character_name,
                world_id=world_id,
                seed=provisioning.seed,
                entity_state=provisioning.entity_state,
                entity_state_error=provisioning.entity_state_error,
            )
        except DatabaseError as exc:
            raise HTTPException(
                status_code=500, detail="Character provisioning unavailable"
            ) from exc

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
        try:
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
        except DatabaseError as exc:
            raise HTTPException(status_code=500, detail="Character management failed") from exc

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
