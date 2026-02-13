"""
Multi-world migration utility for pipeworks_mud_server.

This script upgrades an existing SQLite database to the new multi-world
schema by adding world_id columns, creating world catalog tables, and
backfilling legacy rows with a default world. It is safe to run multiple
times (idempotent), and it intentionally clears active sessions to avoid
world mismatch during the transition.

Usage:
    python scripts/migrate_to_multiworld.py \
        --default-world daily_undertaking \
        --world daily_undertaking \
        --world pipeworks_web

Notes:
- This script does not require any running server.
- It should be run after pulling the schema changes into the codebase.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from mud_server.db import database


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    """Return True if the given column exists in the table."""
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    """Return True if the given table exists."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,))
    return cursor.fetchone() is not None


def _ensure_column(cursor: sqlite3.Cursor, *, table: str, column: str, definition: str) -> None:
    """
    Ensure a column exists on a table, adding it when missing.

    Args:
        table: Table name.
        column: Column name.
        definition: Column type/constraint fragment (e.g., "TEXT NOT NULL").
    """
    if _column_exists(cursor, table, column):
        return
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _seed_worlds(
    cursor: sqlite3.Cursor, *, world_ids: Iterable[str], default_world_id: str
) -> None:
    """
    Ensure world catalog entries exist for the provided world_ids.

    New rows use the world_id as the name and mark the default world active.
    """
    for world_id in world_ids:
        cursor.execute(
            """
            INSERT OR IGNORE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            (world_id, world_id),
        )
    cursor.execute(
        "UPDATE worlds SET is_active = 1 WHERE id = ?",
        (default_world_id,),
    )


def migrate_database(db_path: Path, *, default_world_id: str, world_ids: list[str]) -> None:
    """
    Apply multi-world schema changes to the database at db_path.

    This function is intentionally verbose and explicit to aid debugging
    during early development.
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Ensure core tables exist before altering them. We fail fast here to avoid
    # accidentally creating partial schemas on a wrong or empty database file.
    required_tables = [
        "users",
        "characters",
        "character_locations",
        "sessions",
        "chat_messages",
    ]
    for table in required_tables:
        if not _table_exists(cursor, table):
            conn.close()
            raise RuntimeError(f"Missing required table: {table}")

    # Add world_id columns to existing tables.
    _ensure_column(
        cursor,
        table="characters",
        column="world_id",
        definition=f"TEXT NOT NULL DEFAULT '{default_world_id}'",
    )
    _ensure_column(
        cursor,
        table="character_locations",
        column="world_id",
        definition=f"TEXT NOT NULL DEFAULT '{default_world_id}'",
    )
    _ensure_column(
        cursor,
        table="sessions",
        column="world_id",
        definition="TEXT",
    )
    _ensure_column(
        cursor,
        table="chat_messages",
        column="world_id",
        definition=f"TEXT NOT NULL DEFAULT '{default_world_id}'",
    )

    # Ensure catalog tables exist.
    if not _table_exists(cursor, "worlds"):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS worlds (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

    if not _table_exists(cursor, "world_permissions"):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS world_permissions (
                user_id INTEGER NOT NULL,
                world_id TEXT NOT NULL,
                can_access INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, world_id)
            )
            """)

    # Backfill world_id for legacy rows.
    cursor.execute(
        "UPDATE characters SET world_id = ? WHERE world_id IS NULL OR world_id = ''",
        (default_world_id,),
    )
    cursor.execute(
        """
        UPDATE character_locations
        SET world_id = ?
        WHERE world_id IS NULL OR world_id = ''
        """,
        (default_world_id,),
    )
    cursor.execute(
        "UPDATE chat_messages SET world_id = ? WHERE world_id IS NULL OR world_id = ''",
        (default_world_id,),
    )

    # Sessions are cleared to avoid cross-world drift during migration.
    cursor.execute("DELETE FROM sessions")

    # Seed world catalog entries.
    _seed_worlds(cursor, world_ids=world_ids, default_world_id=default_world_id)

    conn.commit()
    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate DB to multi-world schema.")
    parser.add_argument(
        "--default-world",
        default=database.DEFAULT_WORLD_ID,
        help="World id used to backfill legacy rows (default: pipeworks_web).",
    )
    parser.add_argument(
        "--world",
        action="append",
        dest="worlds",
        default=[],
        help="World id to seed in the worlds table (repeatable).",
    )
    args = parser.parse_args()

    world_ids = list(dict.fromkeys(args.worlds))
    if args.default_world not in world_ids:
        world_ids.insert(0, args.default_world)

    db_path = database._get_db_path()
    migrate_database(db_path, default_world_id=args.default_world, world_ids=world_ids)
    print(f"Migration complete for {db_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
