"""
Tests for multi-world database migration script.

These tests build a minimal legacy schema and verify that the migration
adds world_id columns, creates catalog tables, and backfills defaults.
"""

import sqlite3

import pytest

from mud_server.db import database
from scripts.migrate_to_multiworld import migrate_database


@pytest.mark.unit
@pytest.mark.db
def test_migrate_adds_world_columns_and_seeds_worlds(tmp_path):
    """Migration should add world_id columns and seed worlds catalog."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Legacy schema (minimal) without world_id columns.
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'player'
        )
        """)
    cursor.execute("""
        CREATE TABLE characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT UNIQUE NOT NULL,
            inventory TEXT NOT NULL DEFAULT '[]',
            is_guest_created INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    cursor.execute("""
        CREATE TABLE character_locations (
            character_id INTEGER PRIMARY KEY,
            room_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    cursor.execute("""
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            character_id INTEGER,
            session_id TEXT UNIQUE NOT NULL
        )
        """)
    cursor.execute("""
        CREATE TABLE chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER,
            user_id INTEGER,
            message TEXT NOT NULL,
            room TEXT NOT NULL,
            recipient_character_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

    cursor.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("legacy", "hash", "player"),
    )
    cursor.execute(
        "INSERT INTO characters (user_id, name) VALUES (?, ?)",
        (1, "legacy_char"),
    )
    cursor.execute(
        "INSERT INTO character_locations (character_id, room_id) VALUES (?, ?)",
        (1, "spawn"),
    )
    cursor.execute(
        "INSERT INTO chat_messages (character_id, user_id, message, room) VALUES (?, ?, ?, ?)",
        (1, 1, "hello", "spawn"),
    )
    cursor.execute(
        "INSERT INTO sessions (user_id, character_id, session_id) VALUES (?, ?, ?)",
        (1, 1, "session-1"),
    )

    conn.commit()
    conn.close()

    migrate_database(
        db_path,
        default_world_id=database.DEFAULT_WORLD_ID,
        world_ids=[database.DEFAULT_WORLD_ID, "pipeworks_web"],
    )

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Verify new tables exist.
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='worlds'")
    assert cursor.fetchone() is not None
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='world_permissions'")
    assert cursor.fetchone() is not None

    # Verify world_id columns were added and backfilled.
    cursor.execute("SELECT world_id FROM characters WHERE id = 1")
    assert cursor.fetchone()[0] == database.DEFAULT_WORLD_ID
    cursor.execute("SELECT world_id FROM character_locations WHERE character_id = 1")
    assert cursor.fetchone()[0] == database.DEFAULT_WORLD_ID
    cursor.execute("SELECT world_id FROM chat_messages WHERE id = 1")
    assert cursor.fetchone()[0] == database.DEFAULT_WORLD_ID

    # Sessions should be cleared by migration.
    cursor.execute("SELECT COUNT(*) FROM sessions")
    assert cursor.fetchone()[0] == 0

    # Worlds should be seeded.
    cursor.execute("SELECT id FROM worlds ORDER BY id")
    world_ids = [row[0] for row in cursor.fetchall()]
    assert database.DEFAULT_WORLD_ID in world_ids
    assert "pipeworks_web" in world_ids

    conn.close()
