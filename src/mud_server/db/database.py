"""Database initialization and management for the MUD server."""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# Path to database file
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "mud.db"


def init_database():
    """Initialize the SQLite database with required tables."""
    from mud_server.api.password import hash_password

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Players table with authentication fields
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'player',
            current_room TEXT NOT NULL DEFAULT 'spawn',
            inventory TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)

    # Chat messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            room TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Player sessions table (for tracking active players)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            session_id TEXT UNIQUE NOT NULL,
            connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Create default superuser if no players exist
    cursor.execute("SELECT COUNT(*) FROM players")
    player_count = cursor.fetchone()[0]

    if player_count == 0:
        default_password_hash = hash_password("admin123")
        cursor.execute(
            """
            INSERT INTO players (username, password_hash, role, current_room)
            VALUES (?, ?, ?, ?)
        """,
            ("admin", default_password_hash, "superuser", "spawn"),
        )
        conn.commit()
        print("\n" + "=" * 60)
        print("⚠️  DEFAULT SUPERUSER CREATED")
        print("=" * 60)
        print("Username: admin")
        print("Password: admin123")
        print("\n⚠️  IMPORTANT: Change this password immediately after first login!")
        print("=" * 60 + "\n")

    conn.close()


def get_connection():
    """Get a database connection."""
    return sqlite3.connect(str(DB_PATH))


def create_player(username: str) -> bool:
    """
    DEPRECATED: Use create_player_with_password instead.
    This function is kept for backward compatibility but will fail
    since password_hash is now required.
    """
    return False


def create_player_with_password(username: str, password: str, role: str = "player") -> bool:
    """
    Create a new player account with password.

    Args:
        username: Unique username
        password: Plain text password (will be hashed)
        role: User role (player, worldbuilder, admin, superuser)

    Returns:
        True if player created successfully, False if username exists
    """
    from mud_server.api.password import hash_password

    try:
        conn = get_connection()
        cursor = conn.cursor()
        password_hash = hash_password(password)
        cursor.execute(
            """
            INSERT INTO players (username, password_hash, role, current_room)
            VALUES (?, ?, ?, ?)
        """,
            (username, password_hash, role, "spawn"),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def player_exists(username: str) -> bool:
    """Check if a player exists."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def verify_password_for_user(username: str, password: str) -> bool:
    """
    Verify a password for a user.

    Args:
        username: Username to check
        password: Plain text password to verify

    Returns:
        True if password matches and user is active, False otherwise
    """
    from mud_server.api.password import verify_password

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT password_hash, is_active FROM players WHERE username = ?", (username,)
    )
    result = cursor.fetchone()
    conn.close()

    if not result:
        return False

    password_hash, is_active = result
    if not is_active:
        return False

    return verify_password(password, password_hash)


def get_player_role(username: str) -> Optional[str]:
    """Get the role of a player."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def set_player_role(username: str, role: str) -> bool:
    """Set the role of a player."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE players SET role = ? WHERE username = ?", (role, username)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_all_players() -> List[Dict[str, Any]]:
    """Get list of all players with their details."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT username, role, created_at, last_login, is_active
        FROM players
        ORDER BY created_at DESC
    """
    )
    results = cursor.fetchall()
    conn.close()

    players = []
    for row in results:
        players.append(
            {
                "username": row[0],
                "role": row[1],
                "created_at": row[2],
                "last_login": row[3],
                "is_active": bool(row[4]),
            }
        )
    return players


def deactivate_player(username: str) -> bool:
    """Deactivate a player (ban)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE players SET is_active = 0 WHERE username = ?", (username,)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def activate_player(username: str) -> bool:
    """Activate a player (unban)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE players SET is_active = 1 WHERE username = ?", (username,)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def change_password_for_user(username: str, new_password: str) -> bool:
    """Change a user's password."""
    from mud_server.api.password import hash_password

    try:
        conn = get_connection()
        cursor = conn.cursor()
        password_hash = hash_password(new_password)
        cursor.execute(
            "UPDATE players SET password_hash = ? WHERE username = ?",
            (password_hash, username),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def is_player_active(username: str) -> bool:
    """Check if a player is active (not banned)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return bool(result[0]) if result else False


def get_player_room(username: str) -> Optional[str]:
    """Get the current room of a player."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT current_room FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def set_player_room(username: str, room: str) -> bool:
    """Set the current room of a player."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE players SET current_room = ? WHERE username = ?", (room, username)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_player_inventory(username: str) -> List[str]:
    """Get the inventory of a player."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT inventory FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return json.loads(result[0])
    return []


def set_player_inventory(username: str, inventory: List[str]) -> bool:
    """Set the inventory of a player."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE players SET inventory = ? WHERE username = ?",
            (json.dumps(inventory), username),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def add_chat_message(username: str, message: str, room: str) -> bool:
    """Add a chat message to the database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_messages (username, message, room) VALUES (?, ?, ?)",
            (username, message, room),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_room_messages(room: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent messages from a room."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT username, message, timestamp FROM chat_messages
        WHERE room = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """,
        (room, limit),
    )
    results = cursor.fetchall()
    conn.close()

    messages = []
    for username, message, timestamp in reversed(results):
        messages.append(
            {"username": username, "message": message, "timestamp": timestamp}
        )
    return messages


def create_session(username: str, session_id: str) -> bool:
    """Create a new player session."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Remove old session if exists
        cursor.execute("DELETE FROM sessions WHERE username = ?", (username,))
        cursor.execute(
            "INSERT INTO sessions (username, session_id) VALUES (?, ?)",
            (username, session_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_active_players() -> List[str]:
    """Get list of currently active players."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM sessions")
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]


def get_players_in_room(room: str) -> List[str]:
    """Get list of players currently in a room."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.username FROM players p
        JOIN sessions s ON p.username = s.username
        WHERE p.current_room = ?
    """,
        (room,),
    )
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]


def remove_session(username: str) -> bool:
    """Remove a player session."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def update_session_activity(username: str) -> bool:
    """Update the last activity timestamp for a session."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET last_activity = CURRENT_TIMESTAMP WHERE username = ?",
            (username,),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_all_players_detailed() -> List[Dict[str, Any]]:
    """Get detailed list of all players including password hash prefix."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, username, password_hash, role, current_room, inventory,
               created_at, last_login, is_active
        FROM players
        ORDER BY created_at DESC
    """
    )
    results = cursor.fetchall()
    conn.close()

    players = []
    for row in results:
        players.append(
            {
                "id": row[0],
                "username": row[1],
                "password_hash": row[2][:20] + "..." if len(row[2]) > 20 else row[2],
                "role": row[3],
                "current_room": row[4],
                "inventory": row[5],
                "created_at": row[6],
                "last_login": row[7],
                "is_active": bool(row[8]),
            }
        )
    return players


def get_all_sessions() -> List[Dict[str, Any]]:
    """Get all active sessions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, username, session_id, connected_at, last_activity
        FROM sessions
        ORDER BY connected_at DESC
    """
    )
    results = cursor.fetchall()
    conn.close()

    sessions = []
    for row in results:
        sessions.append(
            {
                "id": row[0],
                "username": row[1],
                "session_id": row[2],
                "connected_at": row[3],
                "last_activity": row[4],
            }
        )
    return sessions


def get_all_chat_messages(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent chat messages across all rooms."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, username, message, room, timestamp
        FROM chat_messages
        ORDER BY timestamp DESC
        LIMIT ?
    """,
        (limit,),
    )
    results = cursor.fetchall()
    conn.close()

    messages = []
    for row in results:
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


if __name__ == "__main__":
    init_database()
    print(f"Database initialized at {DB_PATH}")
