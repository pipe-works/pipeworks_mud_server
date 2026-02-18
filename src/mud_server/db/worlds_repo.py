"""World catalog and world-access policy repository operations."""

from __future__ import annotations

import sqlite3
from typing import Any, NoReturn, cast

from mud_server.db.connection import connection_scope
from mud_server.db.errors import DatabaseError, DatabaseOperationContext, DatabaseReadError
from mud_server.db.types import WorldAccessDecision


def _raise_read_error(operation: str, exc: Exception, *, details: str | None = None) -> NoReturn:
    """Raise a typed repository read error while preserving chained cause."""
    if isinstance(exc, DatabaseError):
        raise exc
    raise DatabaseReadError(
        context=DatabaseOperationContext(operation=operation, details=details),
        cause=exc,
    ) from exc


def get_world_by_id(world_id: str) -> dict[str, Any] | None:
    """Return one world catalog row by id."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, description, is_active, config_json, created_at
                FROM worlds
                WHERE id = ?
                """,
                (world_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "is_active": bool(row[3]),
                "config_json": row[4],
                "created_at": row[5],
            }
    except Exception as exc:
        _raise_read_error("worlds.get_world_by_id", exc, details=f"world_id={world_id!r}")


def list_worlds(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    """Return world catalog rows, optionally including inactive worlds."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            if include_inactive:
                cursor.execute("""
                    SELECT id, name, description, is_active, config_json, created_at
                    FROM worlds
                    ORDER BY id
                    """)
            else:
                cursor.execute("""
                    SELECT id, name, description, is_active, config_json, created_at
                    FROM worlds
                    WHERE is_active = 1
                    ORDER BY id
                    """)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "is_active": bool(row[3]),
                    "config_json": row[4],
                    "created_at": row[5],
                }
                for row in rows
            ]
    except Exception as exc:
        _raise_read_error(
            "worlds.list_worlds",
            exc,
            details=f"include_inactive={include_inactive}",
        )


def _query_world_rows(cursor: sqlite3.Cursor, *, include_inactive: bool) -> list[tuple[Any, ...]]:
    """Query world catalog rows with optional inactive filtering."""
    if include_inactive:
        cursor.execute("""
            SELECT id, name, description, is_active, config_json, created_at
            FROM worlds
            ORDER BY id
            """)
    else:
        cursor.execute("""
            SELECT id, name, description, is_active, config_json, created_at
            FROM worlds
            WHERE is_active = 1
            ORDER BY id
            """)
    return cursor.fetchall()


def _user_has_world_permission(cursor: sqlite3.Cursor, *, user_id: int, world_id: str) -> bool:
    """Return ``True`` when an explicit world access grant exists."""
    cursor.execute(
        """
        SELECT 1
        FROM world_permissions
        WHERE user_id = ? AND world_id = ? AND can_access = 1
        LIMIT 1
        """,
        (user_id, world_id),
    )
    return cursor.fetchone() is not None


def _count_user_characters_in_world(cursor: sqlite3.Cursor, *, user_id: int, world_id: str) -> int:
    """Count characters owned by ``user_id`` in ``world_id``."""
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM characters
        WHERE user_id = ? AND world_id = ?
        """,
        (user_id, world_id),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def _resolve_world_access_for_row(
    cursor: sqlite3.Cursor,
    *,
    user_id: int,
    role: str | None,
    world_row: tuple[Any, ...],
) -> WorldAccessDecision:
    """Resolve effective access/create capabilities for one world row."""
    from mud_server.config import config

    world_id = str(world_row[0])
    is_active = bool(world_row[3])
    world_policy = config.resolve_world_character_policy(world_id)

    current_count = _count_user_characters_in_world(cursor, user_id=user_id, world_id=world_id)
    has_existing_character = current_count > 0
    has_permission = _user_has_world_permission(cursor, user_id=user_id, world_id=world_id)

    # Elevated roles always have operational world access, but slot limits
    # still constrain character creation counts.
    if role in {"admin", "superuser"}:
        can_access = True
    else:
        can_access = (
            has_permission or has_existing_character or world_policy.creation_mode == "open"
        )

    if not is_active:
        return WorldAccessDecision(
            world_id=world_id,
            can_access=False,
            can_create=False,
            access_mode=world_policy.creation_mode,
            naming_mode=world_policy.naming_mode,
            slot_limit_per_account=int(world_policy.slot_limit_per_account),
            current_character_count=current_count,
            has_permission_grant=has_permission,
            has_existing_character=has_existing_character,
            reason="world_inactive",
        )

    if not can_access:
        return WorldAccessDecision(
            world_id=world_id,
            can_access=False,
            can_create=False,
            access_mode=world_policy.creation_mode,
            naming_mode=world_policy.naming_mode,
            slot_limit_per_account=int(world_policy.slot_limit_per_account),
            current_character_count=current_count,
            has_permission_grant=has_permission,
            has_existing_character=has_existing_character,
            reason="invite_required",
        )

    slot_limit = max(0, int(world_policy.slot_limit_per_account))
    if current_count >= slot_limit:
        return WorldAccessDecision(
            world_id=world_id,
            can_access=True,
            can_create=False,
            access_mode=world_policy.creation_mode,
            naming_mode=world_policy.naming_mode,
            slot_limit_per_account=slot_limit,
            current_character_count=current_count,
            has_permission_grant=has_permission,
            has_existing_character=has_existing_character,
            reason="slot_limit_reached",
        )

    return WorldAccessDecision(
        world_id=world_id,
        can_access=True,
        can_create=True,
        access_mode=world_policy.creation_mode,
        naming_mode=world_policy.naming_mode,
        slot_limit_per_account=slot_limit,
        current_character_count=current_count,
        has_permission_grant=has_permission,
        has_existing_character=has_existing_character,
        reason="ok",
    )


def get_world_access_decision(
    user_id: int,
    world_id: str,
    *,
    role: str | None = None,
) -> WorldAccessDecision:
    """Resolve world access/create decision for one account and world."""
    from mud_server.config import config

    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, description, is_active, config_json, created_at
                FROM worlds
                WHERE id = ?
                LIMIT 1
                """,
                (world_id,),
            )
            world_row = cursor.fetchone()
            if world_row is None:
                world_policy = config.resolve_world_character_policy(world_id)
                return WorldAccessDecision(
                    world_id=world_id,
                    can_access=False,
                    can_create=False,
                    access_mode=world_policy.creation_mode,
                    naming_mode=world_policy.naming_mode,
                    slot_limit_per_account=int(world_policy.slot_limit_per_account),
                    current_character_count=0,
                    has_permission_grant=False,
                    has_existing_character=False,
                    reason="world_not_found",
                )

            return _resolve_world_access_for_row(
                cursor,
                user_id=user_id,
                role=role,
                world_row=world_row,
            )
    except Exception as exc:
        _raise_read_error(
            "worlds.get_world_access_decision",
            exc,
            details=f"user_id={user_id}, world_id={world_id!r}, role={role!r}",
        )


def can_user_access_world(user_id: int, world_id: str, *, role: str | None = None) -> bool:
    """Return ``True`` when the account may access/select the world."""
    return bool(get_world_access_decision(user_id, world_id, role=role).can_access)


def get_user_character_count_for_world(user_id: int, world_id: str) -> int:
    """Return the number of characters the account owns in a world."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            return _count_user_characters_in_world(cursor, user_id=user_id, world_id=world_id)
    except Exception as exc:
        _raise_read_error(
            "worlds.get_user_character_count_for_world",
            exc,
            details=f"user_id={user_id}, world_id={world_id!r}",
        )


def get_world_admin_rows() -> list[dict[str, Any]]:
    """Return operational world rows for admin/superuser world monitoring."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT w.id,
                       w.name,
                       w.description,
                       w.is_active,
                       w.config_json,
                       w.created_at,
                       s.session_id,
                       s.last_activity,
                       s.client_type,
                       c.id,
                       c.name,
                       u.username
                FROM worlds w
                LEFT JOIN sessions s
                       ON s.world_id = w.id
                      AND s.character_id IS NOT NULL
                      AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
                LEFT JOIN characters c ON c.id = s.character_id
                LEFT JOIN users u ON u.id = s.user_id
                ORDER BY w.id ASC, datetime(s.last_activity) DESC
                """)
            rows = cursor.fetchall()
    except Exception as exc:
        _raise_read_error("worlds.get_world_admin_rows", exc)

    worlds_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        world_id = cast(str, row[0])
        world = worlds_by_id.get(world_id)
        if world is None:
            world = {
                "world_id": world_id,
                "name": row[1],
                "description": row[2],
                "is_active": bool(row[3]),
                "config_json": row[4],
                "created_at": row[5],
                "active_session_count": 0,
                "active_character_count": 0,
                "is_online": False,
                "last_activity": None,
                "active_characters": [],
                "_session_ids": set(),
                "_character_ids": set(),
            }
            worlds_by_id[world_id] = world

        session_id = row[6]
        if session_id:
            session_ids = cast(set[str], world["_session_ids"])
            if session_id not in session_ids:
                session_ids.add(session_id)
                world["active_session_count"] = int(world["active_session_count"]) + 1

            if world["last_activity"] is None and row[7] is not None:
                world["last_activity"] = row[7]

        character_id = row[9]
        if character_id is None:
            continue

        character_ids = cast(set[int], world["_character_ids"])
        if int(character_id) not in character_ids:
            character_ids.add(int(character_id))
            world["active_character_count"] = int(world["active_character_count"]) + 1

        world["is_online"] = True
        world["active_characters"].append(
            {
                "character_id": int(character_id),
                "character_name": row[10],
                "username": row[11],
                "session_id": session_id,
                "last_activity": row[7],
                "client_type": row[8] or "unknown",
            }
        )

    result: list[dict[str, Any]] = []
    for world_id in sorted(worlds_by_id):
        world = worlds_by_id[world_id]
        world.pop("_session_ids", None)
        world.pop("_character_ids", None)
        result.append(world)
    return result


def list_worlds_for_user(
    user_id: int,
    *,
    role: str | None = None,
    include_inactive: bool = False,
    include_invite_worlds: bool = False,
) -> list[dict[str, Any]]:
    """Return world rows decorated with access policy for one account."""
    from mud_server.db.users_repo import get_user_role, get_username_by_id

    if role is None:
        username = get_username_by_id(user_id)
        if username:
            role = get_user_role(username)

    try:
        with connection_scope() as conn:
            cursor = conn.cursor()

            rows = _query_world_rows(cursor, include_inactive=include_inactive)
            worlds: list[dict[str, Any]] = []
            is_elevated = role in {"admin", "superuser"}
            for row in rows:
                decision = _resolve_world_access_for_row(
                    cursor,
                    user_id=user_id,
                    role=role,
                    world_row=row,
                )
                if not is_elevated and not include_invite_worlds and not decision.can_access:
                    continue
                worlds.append(
                    {
                        "id": row[0],
                        "name": row[1],
                        "description": row[2],
                        "is_active": bool(row[3]),
                        "config_json": row[4],
                        "created_at": row[5],
                        "can_access": decision.can_access,
                        "can_create": decision.can_create,
                        "access_mode": decision.access_mode,
                        "naming_mode": decision.naming_mode,
                        "slot_limit_per_account": decision.slot_limit_per_account,
                        "current_character_count": decision.current_character_count,
                        "has_permission_grant": decision.has_permission_grant,
                        "has_existing_character": decision.has_existing_character,
                        "is_invite_only": decision.access_mode == "invite",
                        "is_locked": not decision.can_access,
                        "access_reason": decision.reason,
                    }
                )
            return worlds
    except Exception as exc:
        _raise_read_error(
            "worlds.list_worlds_for_user",
            exc,
            details=(
                f"user_id={user_id}, role={role!r}, include_inactive={include_inactive}, "
                f"include_invite_worlds={include_invite_worlds}"
            ),
        )
