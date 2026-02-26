"""Chat repository operations for the SQLite backend.

This module isolates room/whisper chat persistence from the compatibility
facade in ``mud_server.db.database``.
"""

from __future__ import annotations

from typing import Any, NoReturn

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
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()

            resolved_sender = _resolve_character_name(cursor, character_name, world_id=world_id)
            if not resolved_sender:
                return False

            cursor.execute(
                "SELECT id, user_id FROM characters WHERE name = ? AND world_id = ?",
                (resolved_sender, world_id),
            )
            sender_row = cursor.fetchone()
            if not sender_row:
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
            return True
    except Exception as exc:
        _raise_write_error(
            "chat.add_chat_message",
            exc,
            details=f"character_name={character_name!r}, world_id={world_id!r}, room={room!r}",
        )


def prune_chat_messages(
    max_age_hours: int,
    *,
    world_id: str | None = None,
    room: str | None = None,
) -> int:
    """Delete chat messages older than max_age_hours.

    Args:
        max_age_hours: Delete messages with timestamp older than this many hours.
            Must be a positive integer (>= 1).
        world_id: If provided, restrict deletion to this world only.
        room: If provided (requires world_id), restrict to a single room.

    Returns:
        Number of rows deleted.

    Raises:
        ValueError: If max_age_hours < 1 or room is provided without world_id.
        DatabaseWriteError: On SQLite failure.
    """
    if max_age_hours < 1:
        raise ValueError("max_age_hours must be >= 1")
    if room is not None and world_id is None:
        raise ValueError("room filter requires world_id to be specified")

    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()

            if world_id is None:
                cursor.execute(
                    "DELETE FROM chat_messages WHERE datetime(timestamp) <= datetime('now', ? || ' hours')",
                    (f"-{max_age_hours}",),
                )
            elif room is None:
                cursor.execute(
                    "DELETE FROM chat_messages WHERE datetime(timestamp) <= datetime('now', ? || ' hours') AND world_id = ?",
                    (f"-{max_age_hours}", world_id),
                )
            else:
                cursor.execute(
                    "DELETE FROM chat_messages WHERE datetime(timestamp) <= datetime('now', ? || ' hours') AND world_id = ? AND room = ?",
                    (f"-{max_age_hours}", world_id, room),
                )

            return cursor.rowcount
    except Exception as exc:
        _raise_write_error(
            "chat.prune_chat_messages",
            exc,
            details=f"max_age_hours={max_age_hours!r}, world_id={world_id!r}, room={room!r}",
        )


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
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()

            if character_name is None and username is not None:
                character_name = username

            if character_name:
                resolved_name = _resolve_character_name(cursor, character_name, world_id=world_id)
                if resolved_name is None and username is not None:
                    resolved_name = _resolve_character_name(cursor, username, world_id=world_id)
                if not resolved_name:
                    return []

                cursor.execute(
                    "SELECT id FROM characters WHERE name = ? AND world_id = ?",
                    (resolved_name, world_id),
                )
                row = cursor.fetchone()
                if not row:
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

        messages = []
        for name, message, timestamp in reversed(rows):
            messages.append({"username": name, "message": message, "timestamp": timestamp})
        return messages
    except Exception as exc:
        _raise_read_error(
            "chat.get_room_messages",
            exc,
            details=f"world_id={world_id!r}, room={room!r}, limit={limit}",
        )
