"""Character repository operations for the SQLite backend.

This module isolates character persistence and room/inventory state operations
from the compatibility facade in ``mud_server.db.database``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from mud_server.db.constants import DEFAULT_WORLD_ID


def _get_connection() -> sqlite3.Connection:
    """Return a DB connection via the compatibility facade.

    Delegating through ``mud_server.db.database.get_connection`` preserves the
    existing patch points used by tests while the DB layer is incrementally
    split into focused repository modules.
    """
    from mud_server.db import database

    return database.get_connection()


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


def _resolve_character_name(cursor: Any, name: str, *, world_id: str | None = None) -> str | None:
    """Resolve a character name from a direct character name or a username.

    Compatibility behavior:
    - If ``name`` matches a character in the requested world, return it.
    - Otherwise, if ``name`` matches a username, return the oldest character
      for that user in the requested world.
    """
    if world_id is None:
        world_id = DEFAULT_WORLD_ID

    cursor.execute(
        "SELECT name FROM characters WHERE name = ? AND world_id = ? LIMIT 1",
        (name, world_id),
    )
    row = cursor.fetchone()
    if row:
        return cast(str, row[0])

    cursor.execute("SELECT id FROM users WHERE username = ? LIMIT 1", (name,))
    user_row = cursor.fetchone()
    if not user_row:
        return None

    user_id = int(user_row[0])
    cursor.execute(
        "SELECT name FROM characters WHERE user_id = ? AND world_id = ? "
        "ORDER BY created_at ASC LIMIT 1",
        (user_id, world_id),
    )
    char_row = cursor.fetchone()
    return cast(str, char_row[0]) if char_row else None


def resolve_character_name(name: str, *, world_id: str | None = None) -> str | None:
    """Public wrapper that resolves a character name using compatibility rules."""
    conn = _get_connection()
    cursor = conn.cursor()
    resolved = _resolve_character_name(cursor, name, world_id=world_id)
    conn.close()
    return resolved


def create_character_for_user(
    user_id: int,
    name: str,
    *,
    is_guest_created: bool = False,
    room_id: str = "spawn",
    world_id: str = DEFAULT_WORLD_ID,
    state_seed: int | None = None,
) -> bool:
    """Create a character for an existing account.

    The function enforces world-scoped slot limits and seeds both location and
    axis/snapshot state in the same transaction.
    """
    conn: sqlite3.Connection | None = None
    try:
        from mud_server.config import config
        from mud_server.db import database

        conn = _get_connection()
        cursor = conn.cursor()

        # Slot enforcement is world-specific and policy-driven.
        world_policy = config.resolve_world_character_policy(world_id)
        slot_limit = max(0, int(world_policy.slot_limit_per_account))
        existing_count = _count_user_characters_in_world(cursor, user_id=user_id, world_id=world_id)
        if existing_count >= slot_limit:
            conn.close()
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

        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # Close explicit connection handle on constraint failures so callers do
        # not inherit a locked database during retry scenarios.
        if conn is not None:
            conn.close()
        return False


def character_exists(name: str) -> bool:
    """Return ``True`` when a character with this name exists in any world."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM characters WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_character_by_name(name: str) -> dict[str, Any] | None:
    """Return a character row by name, or ``None`` when missing."""
    conn = _get_connection()
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
    conn.close()
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


def get_character_by_id(character_id: int) -> dict[str, Any] | None:
    """Return a character row by id, or ``None`` when missing."""
    conn = _get_connection()
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
    conn.close()
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


def get_character_name_by_id(character_id: int) -> str | None:
    """Return the character name for an id, or ``None`` when missing."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_user_characters(user_id: int, *, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return ordered character rows owned by a user in a specific world."""
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    conn = _get_connection()
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
    conn.close()
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


def get_user_character_world_ids(user_id: int) -> set[str]:
    """Return the set of world ids in which a user owns characters."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT world_id
        FROM characters
        WHERE user_id = ?
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return {row[0] for row in rows}


def tombstone_character(character_id: int) -> bool:
    """Soft-delete a character by unlinking owner and renaming tombstone row."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
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
    conn.commit()
    conn.close()
    return True


def delete_character(character_id: int) -> bool:
    """Permanently delete a character row and return whether one row changed."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM characters WHERE id = ?", (character_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_character_room(name: str, *, world_id: str | None = None) -> str | None:
    """Return the character's current room in the requested world."""
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    conn = _get_connection()
    cursor = conn.cursor()
    resolved_name = _resolve_character_name(cursor, name, world_id=world_id)
    if not resolved_name:
        conn.close()
        return None

    cursor.execute("SELECT id FROM characters WHERE name = ?", (resolved_name,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    character_id = int(row[0])
    cursor.execute(
        "SELECT room_id FROM character_locations WHERE character_id = ? AND world_id = ?",
        (character_id, world_id),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def set_character_room(name: str, room: str, *, world_id: str | None = None) -> bool:
    """Set the character room for a world-scoped character identity."""
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        resolved_name = _resolve_character_name(cursor, name, world_id=world_id)
        if not resolved_name:
            conn.close()
            return False

        cursor.execute("SELECT id FROM characters WHERE name = ?", (resolved_name,))
        row = cursor.fetchone()
        if not row:
            conn.close()
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
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_characters_in_room(room: str, *, world_id: str | None = None) -> list[str]:
    """Return active character names in a room for the selected world."""
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    conn = _get_connection()
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
    conn.close()
    return [row[0] for row in rows]


def get_character_inventory(name: str) -> list[str]:
    """Return character inventory as a JSON-decoded list."""
    conn = _get_connection()
    cursor = conn.cursor()
    resolved_name = _resolve_character_name(cursor, name)
    if not resolved_name:
        conn.close()
        return []

    cursor.execute("SELECT inventory FROM characters WHERE name = ?", (resolved_name,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return []
    inventory: list[str] = json.loads(row[0])
    return inventory


def set_character_inventory(name: str, inventory: list[str]) -> bool:
    """Persist character inventory as JSON for the resolved character name."""
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        resolved_name = _resolve_character_name(cursor, name)
        if not resolved_name:
            conn.close()
            return False

        cursor.execute(
            "UPDATE characters SET inventory = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
            (json.dumps(inventory), resolved_name),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False
