"""
Database initialization and management for the MUD server.

This module provides all database operations for the MUD server using SQLite.
It handles:
- Database schema initialization
- User account management (create, authentication, roles)
- Character management (creation, locations, inventory)
- Session tracking (login/logout, active users)
- Chat message storage and retrieval

Database Design:
    Tables:
    - users: Account identities (login, role, status)
    - characters: World-facing personas owned by users
    - character_locations: Per-character room state
    - sessions: Active login sessions with activity tracking
    - chat_messages: All chat messages with room and recipient info

Security Considerations:
    - Passwords hashed with bcrypt (never plain text)
    - Email stored as hashed value only (privacy-first)
    - SQL injection prevented using parameterized queries
    - Session IDs are UUIDs (hard to guess)

Performance Notes:
    - SQLite handles basic concurrency (~50-100 players)
    - No connection pooling (single file database)
    - Suitable for small-medium deployments
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, cast

# ==========================================================================
# CONFIGURATION
# ==========================================================================


def _get_db_path() -> Path:
    """
    Get the database path from configuration.

    Returns:
        Absolute path to the SQLite database file.
    """
    from mud_server.config import config

    return config.database.absolute_path


# ==========================================================================
# DATABASE INITIALIZATION
# ==========================================================================


def init_database(*, skip_superuser: bool = False) -> None:
    """
    Initialize the SQLite database with required tables.

    Creates all necessary tables if they don't exist. If MUD_ADMIN_USER and
    MUD_ADMIN_PASSWORD environment variables are set and no users exist,
    creates a superuser with those credentials (unless skip_superuser=True).

    Args:
        skip_superuser: If True, skip superuser creation from env vars.

    Side Effects:
        - Creates data/mud.db file if it doesn't exist
        - Creates tables if they don't exist
        - Creates superuser if env vars set and no users exist
    """
    import os

    from mud_server.api.password import hash_password
    from mud_server.config import config

    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email_hash TEXT UNIQUE,
            role TEXT NOT NULL DEFAULT 'player',
            is_active INTEGER NOT NULL DEFAULT 1,
            is_guest INTEGER NOT NULL DEFAULT 0,
            guest_expires_at TIMESTAMP,
            account_origin TEXT NOT NULL DEFAULT 'legacy',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            tombstoned_at TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT UNIQUE NOT NULL,
            inventory TEXT NOT NULL DEFAULT '[]',
            is_guest_created INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS character_locations (
            character_id INTEGER PRIMARY KEY,
            room_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE CASCADE
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_locations_room_id "
        "ON character_locations(room_id)"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            character_id INTEGER,
            session_id TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            client_type TEXT DEFAULT 'unknown',
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER,
            user_id INTEGER,
            message TEXT NOT NULL,
            room TEXT NOT NULL,
            recipient_character_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE SET NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(recipient_character_id) REFERENCES characters(id) ON DELETE SET NULL
        )
    """)

    _create_character_limit_triggers(conn, max_slots=config.characters.max_slots)

    conn.commit()

    if skip_superuser:
        conn.close()
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = int(cursor.fetchone()[0])

    if user_count == 0:
        admin_user = os.environ.get("MUD_ADMIN_USER")
        admin_password = os.environ.get("MUD_ADMIN_PASSWORD")

        if admin_user and admin_password:
            if len(admin_password) < 8:
                print("Warning: MUD_ADMIN_PASSWORD must be at least 8 characters. Skipping.")
            else:
                password_hash = hash_password(admin_password)
                cursor.execute(
                    """
                    INSERT INTO users (username, password_hash, role, account_origin)
                    VALUES (?, ?, ?, ?)
                """,
                    (admin_user, password_hash, "superuser", "system"),
                )
                user_id = cursor.lastrowid
                if user_id is None:
                    raise ValueError("Failed to create superuser.")
                character_id = _create_default_character(cursor, int(user_id), admin_user)
                _seed_character_location(cursor, character_id)
                conn.commit()

                print("\n" + "=" * 60)
                print("SUPERUSER CREATED FROM ENVIRONMENT VARIABLES")
                print("=" * 60)
                print(f"Username: {admin_user}")
                print("=" * 60 + "\n")
        else:
            print("\n" + "=" * 60)
            print("DATABASE INITIALIZED (no superuser created)")
            print("=" * 60)
            print("To create a superuser, either:")
            print("  1. Set MUD_ADMIN_USER and MUD_ADMIN_PASSWORD environment variables")
            print("     and run: mud-server init-db")
            print("  2. Run interactively: mud-server create-superuser")
            print("=" * 60 + "\n")

    conn.close()


def _create_character_limit_triggers(conn: sqlite3.Connection, *, max_slots: int) -> None:
    """
    Create triggers that enforce the per-user character slot limit.

    Note:
        SQLite cannot read config at runtime inside a trigger. We bake the
        configured limit into the trigger at init time.
    """
    cursor = conn.cursor()
    cursor.execute("DROP TRIGGER IF EXISTS enforce_character_limit_insert")
    cursor.execute("DROP TRIGGER IF EXISTS enforce_character_limit_update")

    cursor.execute(f"""
        CREATE TRIGGER enforce_character_limit_insert
        BEFORE INSERT ON characters
        WHEN NEW.user_id IS NOT NULL
        BEGIN
            SELECT
                CASE
                    WHEN (SELECT COUNT(*) FROM characters WHERE user_id = NEW.user_id) >= {int(max_slots)}
                    THEN RAISE(ABORT, 'character limit exceeded')
                END;
        END;
        """)  # nosec B608 - limit is validated and interpolated into DDL

    cursor.execute(f"""
        CREATE TRIGGER enforce_character_limit_update
        BEFORE UPDATE OF user_id ON characters
        WHEN NEW.user_id IS NOT NULL
        BEGIN
            SELECT
                CASE
                    WHEN (SELECT COUNT(*) FROM characters WHERE user_id = NEW.user_id) >= {int(max_slots)}
                    THEN RAISE(ABORT, 'character limit exceeded')
                END;
        END;
        """)  # nosec B608 - limit is validated and interpolated into DDL


def _generate_default_character_name(cursor: Any, username: str) -> str:
    """
    Generate a unique default character name for the given username.

    The name intentionally differs from the account username to reduce
    confusion in admin views (characters vs. users).
    """
    base = f"{username}_char"
    candidate = base
    counter = 1
    while True:
        cursor.execute("SELECT 1 FROM characters WHERE name = ? LIMIT 1", (candidate,))
        if cursor.fetchone() is None:
            return candidate
        counter += 1
        candidate = f"{base}_{counter}"


def _create_default_character(cursor: Any, user_id: int, username: str) -> int:
    """
    Create a default character for a user during bootstrap flows.

    Returns:
        The newly created character id.
    """
    character_name = _generate_default_character_name(cursor, username)
    cursor.execute(
        """
        INSERT INTO characters (user_id, name, is_guest_created)
        VALUES (?, ?, 0)
    """,
        (user_id, character_name),
    )
    character_id = cursor.lastrowid
    if character_id is None:
        raise ValueError("Failed to create default character.")
    return int(character_id)


def _seed_character_location(cursor: Any, character_id: int) -> None:
    """Seed a new character's location to the spawn room."""
    cursor.execute(
        """
        INSERT INTO character_locations (character_id, room_id)
        VALUES (?, ?)
    """,
        (character_id, "spawn"),
    )


def _resolve_character_name(cursor: Any, name: str) -> str | None:
    """
    Resolve a character name from either a character name or a username.

    This preserves compatibility with legacy callers that pass usernames
    into character-facing functions by mapping them to the user's first
    character (oldest by created_at).
    """
    cursor.execute("SELECT name FROM characters WHERE name = ? LIMIT 1", (name,))
    row = cursor.fetchone()
    if row:
        return cast(str, row[0])

    cursor.execute("SELECT id FROM users WHERE username = ? LIMIT 1", (name,))
    user_row = cursor.fetchone()
    if not user_row:
        return None

    user_id = int(user_row[0])
    cursor.execute(
        "SELECT name FROM characters WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
        (user_id,),
    )
    char_row = cursor.fetchone()
    return cast(str, char_row[0]) if char_row else None


def resolve_character_name(name: str) -> str | None:
    """
    Public wrapper for resolving character names from usernames or character names.

    This preserves legacy call sites that still supply usernames while the
    character model is being adopted across the codebase.
    """
    conn = get_connection()
    cursor = conn.cursor()
    resolved = _resolve_character_name(cursor, name)
    conn.close()
    return resolved


# ==========================================================================
# CONNECTION MANAGEMENT
# ==========================================================================


def get_connection() -> sqlite3.Connection:
    """
    Create a new SQLite connection to the database file.

    Returns:
        sqlite3.Connection object
    """
    return sqlite3.connect(str(_get_db_path()))


# ==========================================================================
# USER ACCOUNT MANAGEMENT
# ==========================================================================


def create_user_with_password(
    username: str,
    password: str,
    *,
    role: str = "player",
    account_origin: str = "legacy",
    email_hash: str | None = None,
    is_guest: bool = False,
    guest_expires_at: str | None = None,
    create_default_character: bool = True,
) -> bool:
    """
    Create a new user account and (optionally) a default character.

    Args:
        username: Unique account username.
        password: Plain text password (hashed with bcrypt).
        role: Role string.
        account_origin: Provenance marker for cleanup/auditing.
        email_hash: Hashed email value (nullable during development).
        is_guest: Whether this is a guest account.
        guest_expires_at: Expiration timestamp for guest accounts.
        create_default_character: If True, create a character with the same name.

    Returns:
        True if created successfully, False if username already exists.
    """
    from mud_server.api.password import hash_password

    try:
        conn = get_connection()
        cursor = conn.cursor()
        password_hash = hash_password(password)
        cursor.execute(
            """
            INSERT INTO users (
                username,
                password_hash,
                email_hash,
                role,
                is_guest,
                guest_expires_at,
                account_origin
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                username,
                password_hash,
                email_hash,
                role,
                int(is_guest),
                guest_expires_at,
                account_origin,
            ),
        )
        user_id = cursor.lastrowid
        if user_id is None:
            raise ValueError("Failed to create user.")
        user_id = int(user_id)

        if create_default_character:
            character_id = _create_default_character(cursor, user_id, username)
            _seed_character_location(cursor, character_id)

        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def create_character_for_user(
    user_id: int,
    name: str,
    *,
    is_guest_created: bool = False,
    room_id: str = "spawn",
) -> bool:
    """
    Create a character for an existing user.

    Args:
        user_id: Owning user id.
        name: Character name (globally unique for now).
        is_guest_created: Marks characters created from guest flow.
        room_id: Initial room id.

    Returns:
        True if character created, False on constraint violation.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO characters (user_id, name, is_guest_created)
            VALUES (?, ?, ?)
        """,
            (user_id, name, int(is_guest_created)),
        )
        character_id = cursor.lastrowid
        if character_id is None:
            raise ValueError("Failed to create character.")
        character_id = int(character_id)
        _seed_character_location(cursor, character_id)
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def user_exists(username: str) -> bool:
    """Return True if a user account exists."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_user_id(username: str) -> int | None:
    """Return user id for the given username, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else None


def get_username_by_id(user_id: int) -> str | None:
    """Return username for a user id, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_user_role(username: str) -> str | None:
    """Return the role for a username, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_user_account_origin(username: str) -> str | None:
    """Return account_origin for the given username."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT account_origin FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def set_user_role(username: str, role: str) -> bool:
    """Update a user's role."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def verify_password_for_user(username: str, password: str) -> bool:
    """
    Verify a password against stored bcrypt hash.

    Uses a dummy hash for timing safety when user doesn't exist.
    """
    from mud_server.api.password import verify_password

    DUMMY_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G5j1L3tDPZ3q4q"  # nosec B105

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        verify_password(password, DUMMY_HASH)
        return False

    return verify_password(password, row[0])


def is_user_active(username: str) -> bool:
    """Return True if the user is active (not banned)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False


def deactivate_user(username: str) -> bool:
    """Deactivate (ban) a user account."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0 WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def activate_user(username: str) -> bool:
    """Activate (unban) a user account."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 1 WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def change_password_for_user(username: str, new_password: str) -> bool:
    """Change a user's password (hashes with bcrypt)."""
    from mud_server.api.password import hash_password

    try:
        conn = get_connection()
        cursor = conn.cursor()
        password_hash = hash_password(new_password)
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (password_hash, username),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def tombstone_user(user_id: int) -> None:
    """Tombstone a user account without deleting rows."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET is_active = 0,
            tombstoned_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """,
        (user_id,),
    )
    conn.commit()
    conn.close()


def delete_user(username: str) -> bool:
    """
    Delete a user account while preserving character data.

    This performs:
      - Unlink characters from the user (user_id -> NULL)
      - Remove all sessions
      - Tombstone the user row (soft delete)
    """
    user_id = get_user_id(username)
    if not user_id:
        return False

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE characters SET user_id = NULL WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        cursor.execute(
            "UPDATE users SET is_active = 0, tombstoned_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ==========================================================================
# CHARACTER MANAGEMENT
# ==========================================================================


def character_exists(name: str) -> bool:
    """Return True if a character with this name exists."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM characters WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_character_by_name(name: str) -> dict[str, Any] | None:
    """Return character row by name."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, name, inventory, is_guest_created, created_at, updated_at
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
        "inventory": row[3],
        "is_guest_created": bool(row[4]),
        "created_at": row[5],
        "updated_at": row[6],
    }


def get_character_by_id(character_id: int) -> dict[str, Any] | None:
    """Return character row by id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, name, inventory, is_guest_created, created_at, updated_at
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
        "inventory": row[3],
        "is_guest_created": bool(row[4]),
        "created_at": row[5],
        "updated_at": row[6],
    }


def get_character_name_by_id(character_id: int) -> str | None:
    """Return character name for the given id, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_user_characters(user_id: int) -> list[dict[str, Any]]:
    """Return all characters owned by the given user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, is_guest_created, created_at, updated_at
        FROM characters
        WHERE user_id = ?
        ORDER BY created_at ASC
    """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": int(row[0]),
            "name": row[1],
            "is_guest_created": bool(row[2]),
            "created_at": row[3],
            "updated_at": row[4],
        }
        for row in rows
    ]


def unlink_characters_for_user(user_id: int) -> None:
    """Detach characters from a user (used when tombstoning guest accounts)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE characters SET user_id = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ==========================================================================
# CHARACTER STATE AND LOCATION
# ==========================================================================


def get_character_room(name: str) -> str | None:
    """Return the current room for a character by name."""
    conn = get_connection()
    cursor = conn.cursor()
    resolved_name = _resolve_character_name(cursor, name)
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
        "SELECT room_id FROM character_locations WHERE character_id = ?", (character_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def set_character_room(name: str, room: str) -> bool:
    """Set the current room for a character by name."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        resolved_name = _resolve_character_name(cursor, name)
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
            INSERT INTO character_locations (character_id, room_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(character_id) DO UPDATE
                SET room_id = excluded.room_id,
                    updated_at = CURRENT_TIMESTAMP
        """,
            (character_id, room),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_characters_in_room(room: str) -> list[str]:
    """Return character names in a room with active sessions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT c.name
        FROM characters c
        JOIN character_locations l ON c.id = l.character_id
        JOIN sessions s ON s.character_id = c.id
        WHERE l.room_id = ?
          AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
    """,
        (room,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


# ==========================================================================
# INVENTORY MANAGEMENT
# ==========================================================================


def get_character_inventory(name: str) -> list[str]:
    """Return the character inventory as a list of item ids."""
    conn = get_connection()
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
    """Set the character inventory."""
    try:
        conn = get_connection()
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


# ==========================================================================
# CHAT MESSAGES
# ==========================================================================


def add_chat_message(
    character_name: str,
    message: str,
    room: str,
    recipient_character_name: str | None = None,
    recipient: str | None = None,
) -> bool:
    """Add a chat message for a character. Supports optional whisper recipient."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        resolved_sender = _resolve_character_name(cursor, character_name)
        if not resolved_sender:
            conn.close()
            return False

        cursor.execute("SELECT id, user_id FROM characters WHERE name = ?", (resolved_sender,))
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
            resolved_recipient = _resolve_character_name(cursor, recipient_character_name)
            if resolved_recipient:
                recipient_character_name = resolved_recipient

            cursor.execute("SELECT id FROM characters WHERE name = ?", (recipient_character_name,))
            recipient_row = cursor.fetchone()
            if recipient_row:
                recipient_id = int(recipient_row[0])

        cursor.execute(
            """
            INSERT INTO chat_messages (
                character_id,
                user_id,
                message,
                room,
                recipient_character_id
            )
            VALUES (?, ?, ?, ?, ?)
        """,
            (sender_id, user_id, message, room, recipient_id),
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
) -> list[dict[str, Any]]:
    """
    Get recent messages from a room. Filters whispers based on character.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if character_name is None and username is not None:
        character_name = username

    if character_name:
        resolved_name = _resolve_character_name(cursor, character_name)
        if resolved_name is None and username is not None:
            resolved_name = _resolve_character_name(cursor, username)
        if not resolved_name:
            conn.close()
            return []

        cursor.execute("SELECT id FROM characters WHERE name = ?", (resolved_name,))
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
            WHERE m.room = ? AND (
                m.recipient_character_id IS NULL OR
                m.recipient_character_id = ? OR
                m.character_id = ?
            )
            ORDER BY m.timestamp DESC, m.id DESC
            LIMIT ?
        """,
            (room, character_id, character_id, limit),
        )
    else:
        cursor.execute(
            """
            SELECT c.name, m.message, m.timestamp
            FROM chat_messages m
            JOIN characters c ON c.id = m.character_id
            WHERE m.room = ?
            ORDER BY m.timestamp DESC, m.id DESC
            LIMIT ?
        """,
            (room, limit),
        )

    rows = cursor.fetchall()
    conn.close()

    messages = []
    for name, message, timestamp in reversed(rows):
        messages.append({"username": name, "message": message, "timestamp": timestamp})
    return messages


# ==========================================================================
# SESSION MANAGEMENT
# ==========================================================================


def create_session(
    user_id: int | str,
    session_id: str,
    *,
    client_type: str = "unknown",
    character_id: int | None = None,
) -> bool:
    """
    Create a new session record for a user.

    Behavior depends on configuration:
      - allow_multiple_sessions = False: remove existing sessions for the user
      - allow_multiple_sessions = True: keep existing sessions
    """
    from mud_server.config import config

    try:
        if isinstance(user_id, str):
            resolved = get_user_id(user_id)
            if not resolved:
                return False
            user_id = resolved

        if character_id is None:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM characters WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            )
            rows = cursor.fetchall()
            conn.close()
            if len(rows) == 1:
                character_id = int(rows[0][0])
        conn = get_connection()
        cursor = conn.cursor()

        if not config.session.allow_multiple_sessions:
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

        client_type = client_type.strip().lower() if client_type else "unknown"

        if config.session.ttl_minutes > 0:
            cursor.execute(
                """
                INSERT INTO sessions (
                    user_id,
                    character_id,
                    session_id,
                    created_at,
                    last_activity,
                    expires_at,
                    client_type
                )
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, datetime('now', ?), ?)
            """,
                (
                    user_id,
                    character_id,
                    session_id,
                    f"+{config.session.ttl_minutes} minutes",
                    client_type,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO sessions (
                    user_id,
                    character_id,
                    session_id,
                    created_at,
                    last_activity,
                    expires_at,
                    client_type
                )
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, ?)
            """,
                (user_id, character_id, session_id, client_type),
            )

        cursor.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,),
        )

        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def set_session_character(session_id: str, character_id: int) -> bool:
    """Attach a character to an existing session."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET character_id = ? WHERE session_id = ?",
            (character_id, session_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def remove_session_by_id(session_id: str) -> bool:
    """Remove a specific session by its session_id."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        removed = int(cursor.rowcount or 0)
        conn.commit()
        conn.close()
        return removed > 0
    except Exception:
        return False


def remove_sessions_for_user(user_id: int) -> bool:
    """Remove all sessions for a user (used for forced logout/ban)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        removed = int(cursor.rowcount or 0)
        conn.commit()
        conn.close()
        return removed > 0
    except Exception:
        return False


def update_session_activity(session_id: str) -> bool:
    """
    Update last_activity for a session and extend expiry when sliding is enabled.
    """
    from mud_server.config import config

    try:
        conn = get_connection()
        cursor = conn.cursor()

        if config.session.sliding_expiration and config.session.ttl_minutes > 0:
            cursor.execute(
                """
                UPDATE sessions
                SET last_activity = CURRENT_TIMESTAMP,
                    expires_at = datetime('now', ?)
                WHERE session_id = ?
                """,
                (f"+{config.session.ttl_minutes} minutes", session_id),
            )
        else:
            cursor.execute(
                "UPDATE sessions SET last_activity = CURRENT_TIMESTAMP WHERE session_id = ?",
                (session_id,),
            )

        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_session_by_id(session_id: str) -> dict[str, Any] | None:
    """Return session record by session_id (or None if not found)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, character_id, session_id, created_at, last_activity, expires_at, client_type
        FROM sessions WHERE session_id = ?
        """,
        (session_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "user_id": int(row[0]),
        "character_id": row[1],
        "session_id": row[2],
        "created_at": row[3],
        "last_activity": row[4],
        "expires_at": row[5],
        "client_type": row[6],
    }


def get_active_session_count() -> int:
    """Count active sessions within the configured activity window."""
    from mud_server.config import config

    conn = get_connection()
    cursor = conn.cursor()
    where_clauses = ["(expires_at IS NULL OR datetime(expires_at) > datetime('now'))"]
    params: list[str] = []
    if config.session.active_window_minutes > 0:
        where_clauses.append("datetime(last_activity) >= datetime('now', ?)")
        params.append(f"-{config.session.active_window_minutes} minutes")

    sql = f"""
        SELECT COUNT(*) FROM sessions
        WHERE {" AND ".join(where_clauses)}
    """  # nosec B608
    cursor.execute(sql, params)
    row = cursor.fetchone()
    count = int(row[0]) if row else 0
    conn.close()
    return count


def cleanup_expired_sessions() -> int:
    """Remove expired sessions based on expires_at timestamp."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM sessions
            WHERE expires_at IS NOT NULL AND datetime(expires_at) <= datetime('now')
            """)
        removed_count: int = cursor.rowcount
        conn.commit()
        conn.close()
        return removed_count
    except Exception:
        return 0


def clear_all_sessions() -> int:
    """Remove all sessions from the database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions")
        removed_count: int = cursor.rowcount
        conn.commit()
        conn.close()
        return removed_count
    except Exception:
        return 0


def get_active_characters() -> list[str]:
    """Return character names with active sessions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT c.name
        FROM sessions s
        JOIN characters c ON c.id = s.character_id
        WHERE s.character_id IS NOT NULL
          AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


# ==========================================================================
# GUEST ACCOUNT CLEANUP
# ==========================================================================


def cleanup_expired_guest_accounts() -> int:
    """
    Tombstone expired guest accounts and unlink their characters.

    Returns:
        Number of guest users tombstoned.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM users
        WHERE tombstoned_at IS NULL
          AND (
            (is_guest = 1 AND guest_expires_at IS NOT NULL
             AND datetime(guest_expires_at) <= datetime('now'))
            OR
            (account_origin = 'visitor'
             AND guest_expires_at IS NULL
             AND datetime(created_at) <= datetime('now', '-24 hours'))
          )
        """)
    rows = cursor.fetchall()
    if not rows:
        conn.close()
        return 0

    user_ids = [int(row[0]) for row in rows]

    placeholders = ",".join(["?"] * len(user_ids))
    cursor.execute(
        f"UPDATE characters SET user_id = NULL WHERE user_id IN ({placeholders})",  # nosec B608
        user_ids,
    )
    cursor.execute(
        f"UPDATE users SET is_active = 0, tombstoned_at = CURRENT_TIMESTAMP "
        f"WHERE id IN ({placeholders})",  # nosec B608
        user_ids,
    )

    conn.commit()
    conn.close()
    return len(user_ids)


# ==========================================================================
# ADMIN QUERIES
# ==========================================================================


def _quote_identifier(identifier: str) -> str:
    """Safely quote an SQLite identifier (table/column name)."""
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def get_table_names() -> list[str]:
    """Return a sorted list of user-defined table names (excludes sqlite_*)."""
    conn = get_connection()
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
    """Return table metadata for admin database browsing."""
    conn = get_connection()
    cursor = conn.cursor()

    tables: list[dict[str, Any]] = []
    for table_name in get_table_names():
        quoted_table = _quote_identifier(table_name)
        cursor.execute(f"PRAGMA table_info({quoted_table})")
        columns = [row[1] for row in cursor.fetchall()]

        cursor.execute(f"SELECT COUNT(*) FROM {quoted_table}")  # nosec B608
        row_count = int(cursor.fetchone()[0])

        tables.append({"name": table_name, "columns": columns, "row_count": row_count})

    conn.close()
    return tables


def get_table_rows(table_name: str, limit: int = 100) -> tuple[list[str], list[list[Any]]]:
    """Return column names and rows for a given table."""
    table_names = set(get_table_names())
    if table_name not in table_names:
        raise ValueError(f"Table '{table_name}' does not exist")

    conn = get_connection()
    cursor = conn.cursor()

    quoted_table = _quote_identifier(table_name)
    cursor.execute(f"PRAGMA table_info({quoted_table})")
    columns = [row[1] for row in cursor.fetchall()]

    cursor.execute(f"SELECT * FROM {quoted_table} LIMIT ?", (limit,))  # nosec B608
    rows = [list(row) for row in cursor.fetchall()]

    conn.close()
    return columns, rows


def get_all_users_detailed() -> list[dict[str, Any]]:
    """Return detailed user list for admin database viewer."""
    conn = get_connection()
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
               COUNT(c.id) AS character_count
        FROM users u
        LEFT JOIN characters c ON c.user_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    users = []
    for row in rows:
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
            }
        )
    return users


def get_all_users() -> list[dict[str, Any]]:
    """Return basic user list for admin summaries."""
    conn = get_connection()
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


def get_character_locations() -> list[dict[str, Any]]:
    """Return character location rows with names for admin display."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id,
               c.name,
               l.room_id,
               l.updated_at
        FROM character_locations l
        JOIN characters c ON c.id = l.character_id
        ORDER BY c.id
    """)
    rows = cursor.fetchall()
    conn.close()

    locations: list[dict[str, Any]] = []
    for row in rows:
        locations.append(
            {
                "character_id": row[0],
                "character_name": row[1],
                "room_id": row[2],
                "updated_at": row[3],
            }
        )
    return locations


def get_all_sessions() -> list[dict[str, Any]]:
    """Return all active (non-expired) sessions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id,
               u.username,
               c.name,
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
    rows = cursor.fetchall()
    conn.close()

    sessions = []
    for row in rows:
        sessions.append(
            {
                "id": row[0],
                "username": row[1],
                "character_name": row[2],
                "session_id": row[3],
                "created_at": row[4],
                "last_activity": row[5],
                "expires_at": row[6],
                "client_type": row[7],
            }
        )
    return sessions


def get_active_connections() -> list[dict[str, Any]]:
    """Return active sessions with activity age in seconds."""
    from mud_server.config import config

    conn = get_connection()
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
               s.session_id,
               s.created_at,
               s.last_activity,
               s.expires_at,
               s.client_type,
               CAST(strftime('%s','now') - strftime('%s', s.last_activity) AS INTEGER) AS age_seconds
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN characters c ON c.id = s.character_id
        WHERE {" AND ".join(where_clauses)}
        ORDER BY s.last_activity DESC
    """  # nosec B608
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        sessions.append(
            {
                "id": row[0],
                "username": row[1],
                "character_name": row[2],
                "session_id": row[3],
                "created_at": row[4],
                "last_activity": row[5],
                "expires_at": row[6],
                "client_type": row[7],
                "age_seconds": row[8],
            }
        )
    return sessions


def get_all_chat_messages(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent chat messages across all rooms."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id,
               c.name,
               m.message,
               m.room,
               m.timestamp
        FROM chat_messages m
        JOIN characters c ON c.id = m.character_id
        ORDER BY m.timestamp DESC
        LIMIT ?
    """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        messages.append(
            {
                "id": row[0],
                "username": row[1],
                "message": row[2],
                "room": row[3],
                "timestamp": row[4],
            }
        )
    return messages


# ==========================================================================
# LEGACY COMPATIBILITY SHIMS (BREAKING CHANGE TRANSITION)
# ==========================================================================


def player_exists(username: str) -> bool:
    """Backward-compatible alias for user_exists()."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM users WHERE username = ? AND tombstoned_at IS NULL",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_player_role(username: str) -> str | None:
    """Backward-compatible alias for get_user_role()."""
    return get_user_role(username)


def get_player_account_origin(username: str) -> str | None:
    """Backward-compatible alias for get_user_account_origin()."""
    return get_user_account_origin(username)


def set_player_role(username: str, role: str) -> bool:
    """Backward-compatible alias for set_user_role()."""
    return set_user_role(username, role)


def is_player_active(username: str) -> bool:
    """Backward-compatible alias for is_user_active()."""
    return is_user_active(username)


def deactivate_player(username: str) -> bool:
    """Backward-compatible alias for deactivate_user()."""
    return deactivate_user(username)


def activate_player(username: str) -> bool:
    """Backward-compatible alias for activate_user()."""
    return activate_user(username)


def create_player_with_password(
    username: str,
    password: str,
    role: str = "player",
    account_origin: str = "legacy",
) -> bool:
    """Backward-compatible alias for create_user_with_password()."""
    return create_user_with_password(
        username,
        password,
        role=role,
        account_origin=account_origin,
    )


def get_player_room(username: str) -> str | None:
    """Backward-compatible alias for get_character_room()."""
    return get_character_room(username)


def set_player_room(username: str, room: str) -> bool:
    """Backward-compatible alias for set_character_room()."""
    return set_character_room(username, room)


def get_player_inventory(username: str) -> list[str]:
    """Backward-compatible alias for get_character_inventory()."""
    return get_character_inventory(username)


def set_player_inventory(username: str, inventory: list[str]) -> bool:
    """Backward-compatible alias for set_character_inventory()."""
    return set_character_inventory(username, inventory)


def get_active_players() -> list[str]:
    """Backward-compatible alias for get_active_characters()."""
    return get_active_characters()


def get_players_in_room(room: str) -> list[str]:
    """Backward-compatible alias for get_characters_in_room()."""
    return get_characters_in_room(room)


def get_all_players_detailed() -> list[dict[str, Any]]:
    """Backward-compatible alias for get_all_users_detailed()."""
    return get_all_users_detailed()


def get_all_players() -> list[dict[str, Any]]:
    """Backward-compatible alias for get_all_users()."""
    return get_all_users()


def get_player_locations() -> list[dict[str, Any]]:
    """Backward-compatible alias for get_character_locations()."""
    return get_character_locations()


def delete_player(username: str) -> bool:
    """Backward-compatible alias for delete_user()."""
    return delete_user(username)


def cleanup_temporary_accounts(max_age_hours: int = 24, origin: str = "visitor") -> int:
    """
    Backward-compatible alias for cleanup_expired_guest_accounts().

    Args are ignored because guest expiry is timestamp-driven.
    """
    return cleanup_expired_guest_accounts()


def remove_session(username: str) -> bool:
    """Backward-compatible alias for removing sessions by username."""
    user_id = get_user_id(username)
    if not user_id:
        return False
    return remove_sessions_for_user(user_id)


if __name__ == "__main__":
    init_database()
    print(f"Database initialized at {_get_db_path()}")
