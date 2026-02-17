"""Character repository operations for the SQLite backend.

This module isolates character persistence and room/inventory state operations
from the compatibility facade in ``mud_server.db.database``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, NoReturn, cast

from mud_server.db.connection import connection_scope
from mud_server.db.errors import (
    DatabaseError,
    DatabaseOperationContext,
    DatabaseReadError,
    DatabaseWriteError,
)


def _raise_read_error(operation: str, exc: Exception, *, details: str | None = None) -> NoReturn:
    """Raise a typed repository read error while preserving chained cause."""
    if isinstance(exc, DatabaseError):
        raise exc
    raise DatabaseReadError(
        context=DatabaseOperationContext(operation=operation, details=details),
        cause=exc,
    ) from exc


def _raise_write_error(operation: str, exc: Exception, *, details: str | None = None) -> NoReturn:
    """Raise a typed repository write error while preserving chained cause."""
    if isinstance(exc, DatabaseError):
        raise exc
    raise DatabaseWriteError(
        context=DatabaseOperationContext(operation=operation, details=details),
        cause=exc,
    ) from exc


def _count_user_characters_in_world(cursor: Any, *, user_id: int, world_id: str) -> int:
    """Return the number of characters a user owns in a world."""
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


def _resolve_character_name(cursor: Any, name: str, *, world_id: str) -> str | None:
    """Resolve a character name strictly by character identity in an explicit world."""
    cursor.execute(
        "SELECT name FROM characters WHERE name = ? AND world_id = ? LIMIT 1",
        (name, world_id),
    )
    row = cursor.fetchone()
    if row:
        return cast(str, row[0])
    return None


def _generate_default_character_name(cursor: Any, username: str) -> str:
    """Generate a unique compatibility default character name for a username."""
    base = f"{username}_char"
    candidate = base
    counter = 1
    while True:
        cursor.execute("SELECT 1 FROM characters WHERE name = ? LIMIT 1", (candidate,))
        if cursor.fetchone() is None:
            return candidate
        counter += 1
        candidate = f"{base}_{counter}"


def _create_default_character(cursor: Any, user_id: int, username: str, *, world_id: str) -> int:
    """Create a default character row and seed axis/location snapshot state."""
    from mud_server.db import database

    character_name = _generate_default_character_name(cursor, username)
    cursor.execute(
        """
        INSERT INTO characters (user_id, name, world_id, is_guest_created)
        VALUES (?, ?, ?, 0)
        """,
        (user_id, character_name, world_id),
    )
    character_id = cursor.lastrowid
    if character_id is None:
        raise ValueError("Failed to create default character.")
    character_id_int = int(character_id)

    database._seed_character_axis_scores(cursor, character_id=character_id_int, world_id=world_id)
    database._seed_character_state_snapshot(
        cursor, character_id=character_id_int, world_id=world_id
    )
    return character_id_int


def _seed_character_location(cursor: Any, character_id: int, *, world_id: str) -> None:
    """Seed a new character location row to the world spawn room."""
    cursor.execute(
        """
        INSERT INTO character_locations (character_id, world_id, room_id)
        VALUES (?, ?, ?)
        """,
        (character_id, world_id, "spawn"),
    )


def resolve_character_name(name: str, *, world_id: str) -> str | None:
    """Return a world-scoped character name for an exact character identity."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            resolved = _resolve_character_name(cursor, name, world_id=world_id)
        return resolved
    except Exception as exc:
        _raise_read_error(
            "characters.resolve_character_name",
            exc,
            details=f"name={name!r}, world_id={world_id!r}",
        )


def create_character_for_user(
    user_id: int,
    name: str,
    *,
    is_guest_created: bool = False,
    room_id: str = "spawn",
    world_id: str,
    state_seed: int | None = None,
) -> bool:
    """Create a character for an existing account.

    The function enforces world-scoped slot limits and seeds both location and
    axis/snapshot state in the same transaction.
    """
    try:
        from mud_server.config import config
        from mud_server.db import database

        with connection_scope(write=True) as conn:
            cursor = conn.cursor()

            # Slot enforcement is world-specific and policy-driven.
            world_policy = config.resolve_world_character_policy(world_id)
            slot_limit = max(0, int(world_policy.slot_limit_per_account))
            existing_count = _count_user_characters_in_world(
                cursor, user_id=user_id, world_id=world_id
            )
            if existing_count >= slot_limit:
                return False

            cursor.execute(
                """
                INSERT INTO characters (user_id, name, world_id, is_guest_created)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, name, world_id, int(is_guest_created)),
            )
            character_id = cursor.lastrowid
            if character_id is None:
                raise ValueError("Failed to create character.")
            character_id_int = int(character_id)

            # Keep seed/init behavior centralized in existing helpers during the
            # incremental refactor so downstream state logic remains unchanged.
            database._seed_character_location(cursor, character_id_int, world_id=world_id)
            database._seed_character_axis_scores(
                cursor,
                character_id=character_id_int,
                world_id=world_id,
            )
            database._seed_character_state_snapshot(
                cursor,
                character_id=character_id_int,
                world_id=world_id,
                seed=state_seed,
            )

            if room_id != "spawn":
                cursor.execute(
                    """
                    UPDATE character_locations
                    SET room_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE character_id = ?
                    """,
                    (room_id, character_id_int),
                )

        return True
    except sqlite3.IntegrityError:
        # Name collisions and related uniqueness constraints are represented as
        # a normal domain outcome for existing callers.
        return False
    except Exception as exc:
        _raise_write_error(
            "characters.create_character_for_user",
            exc,
            details=f"user_id={user_id}, name={name!r}, world_id={world_id!r}",
        )


def character_exists(name: str) -> bool:
    """Return ``True`` when a character with this name exists in any world."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM characters WHERE name = ?", (name,))
            row = cursor.fetchone()
        return row is not None
    except Exception as exc:
        _raise_read_error("characters.character_exists", exc, details=f"name={name!r}")


def get_character_by_name(name: str) -> dict[str, Any] | None:
    """Return a character row by name, or ``None`` when missing."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, name, world_id, inventory, is_guest_created, created_at, updated_at
                FROM characters
                WHERE name = ?
                """,
                (name,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": int(row[0]),
            "user_id": row[1],
            "name": row[2],
            "world_id": row[3],
            "inventory": row[4],
            "is_guest_created": bool(row[5]),
            "created_at": row[6],
            "updated_at": row[7],
        }
    except Exception as exc:
        _raise_read_error("characters.get_character_by_name", exc, details=f"name={name!r}")


def get_character_by_id(character_id: int) -> dict[str, Any] | None:
    """Return a character row by id, or ``None`` when missing."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, name, world_id, inventory, is_guest_created, created_at, updated_at
                FROM characters
                WHERE id = ?
                """,
                (character_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": int(row[0]),
            "user_id": row[1],
            "name": row[2],
            "world_id": row[3],
            "inventory": row[4],
            "is_guest_created": bool(row[5]),
            "created_at": row[6],
            "updated_at": row[7],
        }
    except Exception as exc:
        _raise_read_error(
            "characters.get_character_by_id",
            exc,
            details=f"character_id={character_id}",
        )


def get_character_name_by_id(character_id: int) -> str | None:
    """Return the character name for an id, or ``None`` when missing."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM characters WHERE id = ?", (character_id,))
            row = cursor.fetchone()
        return row[0] if row else None
    except Exception as exc:
        _raise_read_error(
            "characters.get_character_name_by_id",
            exc,
            details=f"character_id={character_id}",
        )


def get_user_characters(user_id: int, *, world_id: str) -> list[dict[str, Any]]:
    """Return ordered character rows owned by a user in one explicit world."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, world_id, is_guest_created, created_at, updated_at
                FROM characters
                WHERE user_id = ? AND world_id = ?
                ORDER BY created_at ASC
                """,
                (user_id, world_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row[0]),
                "name": row[1],
                "world_id": row[2],
                "is_guest_created": bool(row[3]),
                "created_at": row[4],
                "updated_at": row[5],
            }
            for row in rows
        ]
    except Exception as exc:
        _raise_read_error(
            "characters.get_user_characters",
            exc,
            details=f"user_id={user_id}, world_id={world_id!r}",
        )


def tombstone_character(character_id: int) -> bool:
    """Soft-delete a character by unlinking owner and renaming tombstone row."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM characters WHERE id = ?", (character_id,))
            row = cursor.fetchone()
            if row is None:
                return False

            original_name = str(row[0] or "character")
            tombstone_name = f"tombstone_{character_id}_{original_name}"
            cursor.execute(
                """
                UPDATE characters
                SET user_id = NULL,
                    name = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (tombstone_name, character_id),
            )
            return True
    except Exception as exc:
        _raise_write_error(
            "characters.tombstone_character",
            exc,
            details=f"character_id={character_id}",
        )


def delete_character(character_id: int) -> bool:
    """Permanently delete a character row and return whether one row changed."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM characters WHERE id = ?", (character_id,))
            deleted = cursor.rowcount > 0
            return deleted
    except Exception as exc:
        _raise_write_error(
            "characters.delete_character",
            exc,
            details=f"character_id={character_id}",
        )


def get_character_room(name: str, *, world_id: str) -> str | None:
    """Return the character's current room in the requested world."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            resolved_name = _resolve_character_name(cursor, name, world_id=world_id)
            if not resolved_name:
                return None

            cursor.execute("SELECT id FROM characters WHERE name = ?", (resolved_name,))
            row = cursor.fetchone()
            if not row:
                return None

            character_id = int(row[0])
            cursor.execute(
                "SELECT room_id FROM character_locations WHERE character_id = ? AND world_id = ?",
                (character_id, world_id),
            )
            row = cursor.fetchone()
        return row[0] if row else None
    except Exception as exc:
        _raise_read_error(
            "characters.get_character_room",
            exc,
            details=f"name={name!r}, world_id={world_id!r}",
        )


def set_character_room(name: str, room: str, *, world_id: str) -> bool:
    """Set the character room for a world-scoped character identity."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            resolved_name = _resolve_character_name(cursor, name, world_id=world_id)
            if not resolved_name:
                return False

            cursor.execute("SELECT id FROM characters WHERE name = ?", (resolved_name,))
            row = cursor.fetchone()
            if not row:
                return False

            character_id = int(row[0])
            cursor.execute(
                """
                INSERT INTO character_locations (character_id, world_id, room_id, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(character_id) DO UPDATE
                    SET world_id = excluded.world_id,
                        room_id = excluded.room_id,
                        updated_at = CURRENT_TIMESTAMP
                """,
                (character_id, world_id, room),
            )
            return True
    except Exception as exc:
        _raise_write_error(
            "characters.set_character_room",
            exc,
            details=f"name={name!r}, room={room!r}, world_id={world_id!r}",
        )


def get_characters_in_room(room: str, *, world_id: str) -> list[str]:
    """Return active character names in a room for the selected world."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT c.name
                FROM characters c
                JOIN character_locations l ON c.id = l.character_id
                JOIN sessions s ON s.character_id = c.id
                WHERE l.world_id = ?
                  AND l.room_id = ?
                  AND (s.world_id IS NULL OR s.world_id = ?)
                  AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
                """,
                (world_id, room, world_id),
            )
            rows = cursor.fetchall()
        return [row[0] for row in rows]
    except Exception as exc:
        _raise_read_error(
            "characters.get_characters_in_room",
            exc,
            details=f"room={room!r}, world_id={world_id!r}",
        )


def get_character_inventory(name: str, *, world_id: str) -> list[str]:
    """Return character inventory as a JSON-decoded list for an explicit world."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            resolved_name = _resolve_character_name(cursor, name, world_id=world_id)
            if not resolved_name:
                return []

            cursor.execute("SELECT inventory FROM characters WHERE name = ?", (resolved_name,))
            row = cursor.fetchone()
    except Exception as exc:
        _raise_read_error(
            "characters.get_character_inventory",
            exc,
            details=f"name={name!r}, world_id={world_id!r}",
        )

    if not row:
        return []
    inventory: list[str] = json.loads(row[0])
    return inventory


def set_character_inventory(name: str, inventory: list[str], *, world_id: str) -> bool:
    """Persist character inventory as JSON for a world-scoped character identity."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            resolved_name = _resolve_character_name(cursor, name, world_id=world_id)
            if not resolved_name:
                return False

            cursor.execute(
                "UPDATE characters SET inventory = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                (json.dumps(inventory), resolved_name),
            )
            return True
    except Exception as exc:
        _raise_write_error(
            "characters.set_character_inventory",
            exc,
            details=f"name={name!r}, world_id={world_id!r}",
        )
