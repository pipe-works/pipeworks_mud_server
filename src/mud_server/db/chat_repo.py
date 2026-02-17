"""Chat repository operations for the SQLite backend.

This module isolates room/whisper chat persistence from the compatibility
facade in ``mud_server.db.database``.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _get_connection() -> sqlite3.Connection:
    """Return a DB connection from the shared connection module."""
    from mud_server.db.connection import get_connection as get_connection_impl

    return get_connection_impl()


def _resolve_character_name(cursor: Any, name: str, *, world_id: str) -> str | None:
    """Resolve a character name using strict world-scoped character identity."""
    from mud_server.db.characters_repo import _resolve_character_name as resolve_character_name_impl

    return resolve_character_name_impl(cursor, name, world_id=world_id)


def add_chat_message(
    character_name: str,
    message: str,
    room: str,
    recipient_character_name: str | None = None,
    recipient: str | None = None,
    *,
    world_id: str,
) -> bool:
    """Insert a chat message row for room chat or whispers.

    Compatibility behavior:
    - ``recipient`` alias is still accepted and mapped to
      ``recipient_character_name``.
    - Sender and recipient names require explicit character identities.
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()

        resolved_sender = _resolve_character_name(cursor, character_name, world_id=world_id)
        if not resolved_sender:
            conn.close()
            return False

        cursor.execute(
            "SELECT id, user_id FROM characters WHERE name = ? AND world_id = ?",
            (resolved_sender, world_id),
        )
        sender_row = cursor.fetchone()
        if not sender_row:
            conn.close()
            return False

        sender_id = int(sender_row[0])
        user_id = sender_row[1]

        recipient_id: int | None = None
        if recipient_character_name is None and recipient is not None:
            recipient_character_name = recipient

        if recipient_character_name:
            resolved_recipient = _resolve_character_name(
                cursor,
                recipient_character_name,
                world_id=world_id,
            )
            if resolved_recipient:
                recipient_character_name = resolved_recipient

            cursor.execute(
                "SELECT id FROM characters WHERE name = ? AND world_id = ?",
                (recipient_character_name, world_id),
            )
            recipient_row = cursor.fetchone()
            if recipient_row:
                recipient_id = int(recipient_row[0])

        cursor.execute(
            """
            INSERT INTO chat_messages (
                character_id,
                user_id,
                message,
                world_id,
                room,
                recipient_character_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sender_id, user_id, message, world_id, room, recipient_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_room_messages(
    room: str,
    *,
    limit: int = 50,
    character_name: str | None = None,
    username: str | None = None,
    world_id: str,
) -> list[dict[str, Any]]:
    """Return recent room messages with whisper visibility filtering.

    When a character identity is provided, this returns:
    - public messages in the room,
    - whispers to that character,
    - whispers sent by that character.
    """
    conn = _get_connection()
    cursor = conn.cursor()

    if character_name is None and username is not None:
        character_name = username

    if character_name:
        resolved_name = _resolve_character_name(cursor, character_name, world_id=world_id)
        if resolved_name is None and username is not None:
            resolved_name = _resolve_character_name(cursor, username, world_id=world_id)
        if not resolved_name:
            conn.close()
            return []

        cursor.execute(
            "SELECT id FROM characters WHERE name = ? AND world_id = ?",
            (resolved_name, world_id),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return []
        character_id = int(row[0])

        cursor.execute(
            """
            SELECT c.name, m.message, m.timestamp
            FROM chat_messages m
            JOIN characters c ON c.id = m.character_id
            WHERE m.world_id = ? AND m.room = ? AND (
                m.recipient_character_id IS NULL OR
                m.recipient_character_id = ? OR
                m.character_id = ?
            )
            ORDER BY m.timestamp DESC, m.id DESC
            LIMIT ?
            """,
            (world_id, room, character_id, character_id, limit),
        )
    else:
        cursor.execute(
            """
            SELECT c.name, m.message, m.timestamp
            FROM chat_messages m
            JOIN characters c ON c.id = m.character_id
            WHERE m.world_id = ? AND m.room = ?
            ORDER BY m.timestamp DESC, m.id DESC
            LIMIT ?
            """,
            (world_id, room, limit),
        )

    rows = cursor.fetchall()
    conn.close()

    messages = []
    for name, message, timestamp in reversed(rows):
        messages.append({"username": name, "message": message, "timestamp": timestamp})
    return messages
