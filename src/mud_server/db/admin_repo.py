"""Admin inspector repository operations for SQLite backend.

This module groups schema/table inspection and admin dashboard aggregate queries
that were previously implemented directly in ``mud_server.db.database``.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _get_connection() -> sqlite3.Connection:
    """Return a DB connection via the compatibility facade."""
    from mud_server.db import database

    return database.get_connection()


def _quote_identifier(identifier: str) -> str:
    """Safely quote an SQLite identifier.

    This escaping strategy is intentionally strict and only supports regular
    table/column identifiers used by admin inspection queries.
    """
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def get_table_names() -> list[str]:
    """Return sorted user-defined table names (excluding ``sqlite_*`` internals)."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """)
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def list_tables() -> list[dict[str, Any]]:
    """Return table metadata for admin database browsing UIs."""
    conn = _get_connection()
    cursor = conn.cursor()

    tables: list[dict[str, Any]] = []
    for table_name in get_table_names():
        quoted_table = _quote_identifier(table_name)
        cursor.execute(f"PRAGMA table_info({quoted_table})")
        columns = [row[1] for row in cursor.fetchall()]

        cursor.execute(f"SELECT COUNT(*) FROM {quoted_table}")  # nosec B608
        row_count = int(cursor.fetchone()[0])

        tables.append(
            {
                "name": table_name,
                "columns": columns,
                "row_count": row_count,
            }
        )

    conn.close()
    return tables


def get_schema_map() -> list[dict[str, Any]]:
    """Return table schemas and foreign key relationships for admin tooling."""
    conn = _get_connection()
    cursor = conn.cursor()

    schema: list[dict[str, Any]] = []
    for table_name in get_table_names():
        quoted_table = _quote_identifier(table_name)
        cursor.execute(f"PRAGMA table_info({quoted_table})")
        columns = [row[1] for row in cursor.fetchall()]

        cursor.execute(f"PRAGMA foreign_key_list({quoted_table})")
        foreign_keys = [
            {
                "from_column": row[3],
                "ref_table": row[2],
                "ref_column": row[4],
                "on_update": row[5],
                "on_delete": row[6],
            }
            for row in cursor.fetchall()
        ]

        schema.append(
            {
                "name": table_name,
                "columns": columns,
                "foreign_keys": foreign_keys,
            }
        )

    conn.close()
    return schema


def get_table_rows(table_name: str, limit: int = 100) -> tuple[list[str], list[list[Any]]]:
    """Return column names and row values for a table.

    Raises:
        ValueError: If ``table_name`` does not exist in the user-visible schema.
    """
    table_names = set(get_table_names())
    if table_name not in table_names:
        raise ValueError(f"Table '{table_name}' does not exist")

    conn = _get_connection()
    cursor = conn.cursor()

    quoted_table = _quote_identifier(table_name)
    cursor.execute(f"PRAGMA table_info({quoted_table})")
    columns = [row[1] for row in cursor.fetchall()]

    cursor.execute(f"SELECT * FROM {quoted_table} LIMIT ?", (limit,))  # nosec B608
    rows = [list(row) for row in cursor.fetchall()]

    conn.close()
    return columns, rows


def get_all_users_detailed() -> list[dict[str, Any]]:
    """Return detailed, non-tombstoned account rows for the Active Users card."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id,
               u.username,
               u.password_hash,
               u.role,
               u.account_origin,
               u.is_guest,
               u.guest_expires_at,
               u.created_at,
               u.last_login,
               u.is_active,
               u.tombstoned_at,
               COUNT(c.id) AS character_count,
               EXISTS(
                   SELECT 1
                   FROM sessions s
                   WHERE s.user_id = u.id
                     AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
               ) AS is_online_account,
               EXISTS(
                   SELECT 1
                   FROM sessions s
                   WHERE s.user_id = u.id
                     AND s.character_id IS NOT NULL
                     AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
               ) AS is_online_in_world,
               (
                   SELECT GROUP_CONCAT(world_id)
                   FROM (
                       SELECT DISTINCT s.world_id AS world_id
                       FROM sessions s
                       WHERE s.user_id = u.id
                         AND s.character_id IS NOT NULL
                         AND s.world_id IS NOT NULL
                         AND (
                           s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now')
                         )
                       ORDER BY s.world_id
                   )
               ) AS online_world_ids_csv
        FROM users u
        LEFT JOIN characters c ON c.user_id = u.id
        WHERE u.tombstoned_at IS NULL
        GROUP BY u.id
        ORDER BY u.created_at DESC
        """)
    rows = cursor.fetchall()
    conn.close()

    users: list[dict[str, Any]] = []
    for row in rows:
        online_world_ids_csv = row[14]
        online_world_ids = (
            [world_id for world_id in str(online_world_ids_csv).split(",") if world_id]
            if online_world_ids_csv
            else []
        )
        users.append(
            {
                "id": row[0],
                "username": row[1],
                "password_hash": row[2][:20] + "..." if len(row[2]) > 20 else row[2],
                "role": row[3],
                "account_origin": row[4],
                "is_guest": bool(row[5]),
                "guest_expires_at": row[6],
                "created_at": row[7],
                "last_login": row[8],
                "is_active": bool(row[9]),
                "tombstoned_at": row[10],
                "character_count": row[11],
                "is_online_account": bool(row[12]),
                "is_online_in_world": bool(row[13]),
                "online_world_ids": online_world_ids,
            }
        )
    return users


def get_all_users() -> list[dict[str, Any]]:
    """Return basic account rows for admin summaries."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT username, role, created_at, last_login, is_active
        FROM users
        ORDER BY created_at DESC
        """)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "username": row[0],
            "role": row[1],
            "created_at": row[2],
            "last_login": row[3],
            "is_active": bool(row[4]),
        }
        for row in rows
    ]


def get_character_locations(*, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return character location rows with names for admin displays."""
    conn = _get_connection()
    cursor = conn.cursor()
    if world_id is None:
        cursor.execute("""
            SELECT c.id,
                   c.name,
                   l.world_id,
                   l.room_id,
                   l.updated_at
            FROM character_locations l
            JOIN characters c ON c.id = l.character_id
            ORDER BY c.id
            """)
    else:
        cursor.execute(
            """
            SELECT c.id,
                   c.name,
                   l.world_id,
                   l.room_id,
                   l.updated_at
            FROM character_locations l
            JOIN characters c ON c.id = l.character_id
            WHERE l.world_id = ?
            ORDER BY c.id
            """,
            (world_id,),
        )
    rows = cursor.fetchall()
    conn.close()

    locations: list[dict[str, Any]] = []
    for row in rows:
        locations.append(
            {
                "character_id": row[0],
                "character_name": row[1],
                "world_id": row[2],
                "room_id": row[3],
                "updated_at": row[4],
            }
        )
    return locations


def get_all_sessions(*, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return all active (non-expired) sessions for optional world scope."""
    conn = _get_connection()
    cursor = conn.cursor()
    if world_id is None:
        cursor.execute("""
            SELECT s.id,
                   u.username,
                   c.name,
                   s.world_id,
                   s.session_id,
                   s.created_at,
                   s.last_activity,
                   s.expires_at,
                   s.client_type
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN characters c ON c.id = s.character_id
            WHERE s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now')
            ORDER BY s.created_at DESC
            """)
    else:
        cursor.execute(
            """
            SELECT s.id,
                   u.username,
                   c.name,
                   s.world_id,
                   s.session_id,
                   s.created_at,
                   s.last_activity,
                   s.expires_at,
                   s.client_type
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN characters c ON c.id = s.character_id
            WHERE (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
              AND s.world_id = ?
            ORDER BY s.created_at DESC
            """,
            (world_id,),
        )
    rows = cursor.fetchall()
    conn.close()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        sessions.append(
            {
                "id": row[0],
                "username": row[1],
                "character_name": row[2],
                "world_id": row[3],
                "session_id": row[4],
                "created_at": row[5],
                "last_activity": row[6],
                "expires_at": row[7],
                "client_type": row[8],
            }
        )
    return sessions


def get_active_connections(*, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return active session rows including derived activity age seconds."""
    from mud_server.config import config

    conn = _get_connection()
    cursor = conn.cursor()

    where_clauses = ["(s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))"]
    params: list[str] = []
    if config.session.active_window_minutes > 0:
        where_clauses.append("datetime(s.last_activity) >= datetime('now', ?)")
        params.append(f"-{config.session.active_window_minutes} minutes")

    sql = f"""
        SELECT s.id,
               u.username,
               c.name,
               s.world_id,
               s.session_id,
               s.created_at,
               s.last_activity,
               s.expires_at,
               s.client_type,
               CAST(strftime('%s','now') - strftime('%s', s.last_activity) AS INTEGER) AS age_seconds
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN characters c ON c.id = s.character_id
        WHERE {" AND ".join(where_clauses)} {"" if world_id is None else "AND s.world_id = ?"}
        ORDER BY s.last_activity DESC
    """  # nosec B608
    if world_id is None:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql, [*params, world_id])
    rows = cursor.fetchall()
    conn.close()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        sessions.append(
            {
                "id": row[0],
                "username": row[1],
                "character_name": row[2],
                "world_id": row[3],
                "session_id": row[4],
                "created_at": row[5],
                "last_activity": row[6],
                "expires_at": row[7],
                "client_type": row[8],
                "age_seconds": row[9],
            }
        )
    return sessions


def get_all_chat_messages(limit: int = 100, *, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return recent chat messages across all rooms for optional world scope."""
    conn = _get_connection()
    cursor = conn.cursor()
    if world_id is None:
        cursor.execute(
            """
            SELECT m.id,
                   c.name,
                   m.message,
                   m.world_id,
                   m.room,
                   m.timestamp
            FROM chat_messages m
            JOIN characters c ON c.id = m.character_id
            ORDER BY m.timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
    else:
        cursor.execute(
            """
            SELECT m.id,
                   c.name,
                   m.message,
                   m.world_id,
                   m.room,
                   m.timestamp
            FROM chat_messages m
            JOIN characters c ON c.id = m.character_id
            WHERE m.world_id = ?
            ORDER BY m.timestamp DESC
            LIMIT ?
            """,
            (world_id, limit),
        )
    rows = cursor.fetchall()
    conn.close()

    messages: list[dict[str, Any]] = []
    for row in rows:
        messages.append(
            {
                "id": row[0],
                "username": row[1],
                "message": row[2],
                "world_id": row[3],
                "room": row[4],
                "timestamp": row[5],
            }
        )
    return messages
