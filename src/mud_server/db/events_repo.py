"""Event ledger repository operations for axis score mutations."""

from __future__ import annotations

import sqlite3
from typing import Any

from mud_server.db.constants import DEFAULT_AXIS_SCORE


def _get_connection() -> sqlite3.Connection:
    """Return a DB connection via the compatibility facade."""
    from mud_server.db import database

    return database.get_connection()


def _get_or_create_event_type_id(
    cursor: sqlite3.Cursor,
    *,
    world_id: str,
    event_type_name: str,
    description: str | None = None,
) -> int:
    """Return event_type id for a world, creating it when absent."""
    cursor.execute(
        "SELECT id FROM event_type WHERE world_id = ? AND name = ? LIMIT 1",
        (world_id, event_type_name),
    )
    row = cursor.fetchone()
    if row:
        return int(row[0])

    cursor.execute(
        """
        INSERT INTO event_type (world_id, name, description)
        VALUES (?, ?, ?)
        """,
        (world_id, event_type_name, description),
    )
    event_type_id = cursor.lastrowid
    if event_type_id is None:
        raise ValueError("Failed to create event_type.")
    return int(event_type_id)


def _resolve_axis_id(cursor: sqlite3.Cursor, *, world_id: str, axis_name: str) -> int | None:
    """Resolve axis id from world id + axis name."""
    cursor.execute(
        "SELECT id FROM axis WHERE world_id = ? AND name = ? LIMIT 1",
        (world_id, axis_name),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else None


def apply_axis_event(
    *,
    world_id: str,
    character_id: int,
    event_type_name: str,
    deltas: dict[str, float],
    metadata: dict[str, str] | None = None,
    event_type_description: str | None = None,
) -> int:
    """Apply axis deltas and persist a full event-ledger mutation atomically."""
    from mud_server.db import database

    if not deltas:
        raise ValueError("Event deltas must not be empty.")

    conn = _get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        event_type_id = _get_or_create_event_type_id(
            cursor,
            world_id=world_id,
            event_type_name=event_type_name,
            description=event_type_description,
        )

        cursor.execute(
            """
            INSERT INTO event (world_id, event_type_id)
            VALUES (?, ?)
            """,
            (world_id, event_type_id),
        )
        event_id = cursor.lastrowid
        if event_id is None:
            raise ValueError("Failed to create event.")
        event_id = int(event_id)

        for axis_name, delta in deltas.items():
            axis_id = _resolve_axis_id(cursor, world_id=world_id, axis_name=axis_name)
            if axis_id is None:
                raise ValueError(f"Unknown axis '{axis_name}' for world '{world_id}'.")

            cursor.execute(
                """
                SELECT axis_score
                FROM character_axis_score
                WHERE character_id = ? AND axis_id = ?
                """,
                (character_id, axis_id),
            )
            row = cursor.fetchone()
            if row is None:
                old_score = DEFAULT_AXIS_SCORE
                cursor.execute(
                    """
                    INSERT INTO character_axis_score
                        (character_id, world_id, axis_id, axis_score)
                    VALUES (?, ?, ?, ?)
                    """,
                    (character_id, world_id, axis_id, old_score),
                )
            else:
                old_score = float(row[0])

            new_score = old_score + float(delta)

            cursor.execute(
                """
                UPDATE character_axis_score
                SET axis_score = ?, updated_at = CURRENT_TIMESTAMP
                WHERE character_id = ? AND axis_id = ?
                """,
                (new_score, character_id, axis_id),
            )

            cursor.execute(
                """
                INSERT INTO event_entity_axis_delta
                    (event_id, character_id, axis_id, old_score, new_score, delta)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, character_id, axis_id, old_score, new_score, float(delta)),
            )

        if metadata:
            for key, value in metadata.items():
                cursor.execute(
                    """
                    INSERT INTO event_metadata (event_id, key, value)
                    VALUES (?, ?, ?)
                    """,
                    (event_id, key, value),
                )

        database._refresh_character_current_snapshot(
            cursor,
            character_id=character_id,
            world_id=world_id,
        )

        conn.commit()
        return event_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_character_axis_events(character_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent axis events with deltas and metadata for one character."""
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT DISTINCT e.id
        FROM event_entity_axis_delta d
        JOIN event e ON e.id = d.event_id
        WHERE d.character_id = ?
        ORDER BY e.id DESC
        LIMIT ?
        """,
        (character_id, limit),
    )
    event_ids = [row[0] for row in cursor.fetchall()]
    if not event_ids:
        conn.close()
        return []

    placeholders = ",".join(["?"] * len(event_ids))
    events_query = f"""
        SELECT e.id,
               e.world_id,
               e.timestamp,
               et.name,
               et.description,
               a.name,
               d.old_score,
               d.new_score,
               d.delta
        FROM event_entity_axis_delta d
        JOIN event e ON e.id = d.event_id
        JOIN event_type et ON et.id = e.event_type_id
        JOIN axis a ON a.id = d.axis_id
        WHERE d.character_id = ?
          AND e.id IN ({placeholders})
        ORDER BY e.id DESC, a.name ASC
        """  # nosec B608
    cursor.execute(events_query, [character_id, *event_ids])
    rows = cursor.fetchall()

    metadata_query = f"""
        SELECT event_id, key, value
        FROM event_metadata
        WHERE event_id IN ({placeholders})
        """  # nosec B608
    cursor.execute(metadata_query, event_ids)
    metadata_rows = cursor.fetchall()
    conn.close()

    metadata_map: dict[int, dict[str, str]] = {}
    for event_id, key, value in metadata_rows:
        event_id_int = int(event_id)
        metadata_map.setdefault(event_id_int, {})[key] = value

    events: dict[int, dict[str, Any]] = {}
    for (
        event_id,
        world_id,
        timestamp,
        event_type_name,
        event_type_description,
        axis_name,
        old_score,
        new_score,
        delta,
    ) in rows:
        event_id_int = int(event_id)
        event = events.get(event_id_int)
        if event is None:
            event = {
                "event_id": event_id_int,
                "world_id": world_id,
                "event_type": event_type_name,
                "event_type_description": event_type_description,
                "timestamp": timestamp,
                "metadata": metadata_map.get(event_id_int, {}),
                "deltas": [],
            }
            events[event_id_int] = event
        event["deltas"].append(
            {
                "axis_name": axis_name,
                "old_score": float(old_score),
                "new_score": float(new_score),
                "delta": float(delta),
            }
        )

    return [events[int(event_id)] for event_id in event_ids if int(event_id) in events]
