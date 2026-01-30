"""
Database initialization and management for the MUD server.

This module provides all database operations for the MUD server using SQLite.
It handles:
- Database schema initialization
- Player account management (create, authentication, roles)
- Session tracking (login/logout, active players)
- Chat message storage and retrieval
- Inventory management
- Player state (location, status)

Database Design:
    Tables:
    - players: User accounts with authentication and game state
    - sessions: Active login sessions with activity tracking
    - chat_messages: All chat messages with room and recipient info

    Schema Management:
    - Tables created automatically on first run
    - Superuser created via env vars (MUD_ADMIN_USER/MUD_ADMIN_PASSWORD) or CLI
    - Password hashes stored using bcrypt (never plain text)
    - JSON used for structured data (inventory)

Security Considerations:
    - Passwords hashed with bcrypt (intentionally slow)
    - SQL injection prevented using parameterized queries
    - Session IDs are UUIDs (hard to guess)
    - Password verification checks account status
    - No hardcoded default credentials

Performance Notes:
    - SQLite handles basic concurrency (~50-100 players)
    - No connection pooling (single file database)
    - Suitable for small-medium deployments
    - Consider PostgreSQL for larger scale
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

# ============================================================================
# CONFIGURATION
# ============================================================================

# Path to the SQLite database file
# Navigates from this file up to project root, then into data/ directory
# The database file is created automatically if it doesn't exist
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "mud.db"


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================


def init_database(*, skip_superuser: bool = False):
    """
    Initialize the SQLite database with required tables.

    Creates all necessary tables if they don't exist. If MUD_ADMIN_USER and
    MUD_ADMIN_PASSWORD environment variables are set and no players exist,
    creates a superuser with those credentials (unless skip_superuser=True).

    Args:
        skip_superuser: If True, skip superuser creation from env vars.
            Used by create-superuser command to avoid duplicate creation.

    Tables Created:
        players: User accounts with authentication, role, state, and inventory
        chat_messages: All chat messages with room and recipient filtering
        sessions: Active login sessions with activity tracking

    Environment Variables:
        MUD_ADMIN_USER: Username for initial superuser (optional)
        MUD_ADMIN_PASSWORD: Password for initial superuser (optional)

    Side Effects:
        - Creates data/mud.db file if it doesn't exist
        - Creates tables if they don't exist
        - Creates superuser if env vars set and no players exist (unless skip_superuser)
        - Commits all changes to database

    Example:
        # With environment variables:
        MUD_ADMIN_USER=myadmin MUD_ADMIN_PASSWORD=secret123 mud-server init-db

        # Without environment variables (no superuser created):
        mud-server init-db
        mud-server create-superuser  # Create interactively after
    """
    import os

    from mud_server.api.password import hash_password

    # Connect to database (creates file if doesn't exist)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # ========================================================================
    # CREATE PLAYERS TABLE
    # Stores user accounts with authentication and game state
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,           -- Unique username (case-sensitive)
            password_hash TEXT NOT NULL,             -- Bcrypt password hash
            role TEXT NOT NULL DEFAULT 'player',     -- User role for permissions
            current_room TEXT NOT NULL DEFAULT 'spawn', -- Current location
            inventory TEXT DEFAULT '[]',             -- JSON array of item IDs
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1              -- Account status (1=active, 0=banned)
        )
    """)

    # ========================================================================
    # CREATE CHAT_MESSAGES TABLE
    # Stores all chat messages with room and optional recipient (for whispers)
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,        -- Message sender
            message TEXT NOT NULL,         -- Message content (includes [YELL], [WHISPER] prefixes)
            room TEXT NOT NULL,            -- Room where message was sent
            recipient TEXT,                -- NULL for public, username for whispers
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ========================================================================
    # CREATE SESSIONS TABLE
    # Tracks active login sessions with activity timestamps
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,  -- One session per player (enforced by UNIQUE)
            session_id TEXT UNIQUE NOT NULL, -- UUID session identifier
            connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Commit table creation
    conn.commit()

    # ========================================================================
    # CREATE SUPERUSER FROM ENVIRONMENT VARIABLES (if no players exist)
    # ========================================================================
    if skip_superuser:
        conn.close()
        return

    cursor.execute("SELECT COUNT(*) FROM players")
    player_count = cursor.fetchone()[0]

    if player_count == 0:
        admin_user = os.environ.get("MUD_ADMIN_USER")
        admin_password = os.environ.get("MUD_ADMIN_PASSWORD")

        if admin_user and admin_password:
            # Validate password length
            if len(admin_password) < 8:
                print("Warning: MUD_ADMIN_PASSWORD must be at least 8 characters. Skipping.")
            else:
                # Create superuser from environment variables
                password_hash = hash_password(admin_password)
                cursor.execute(
                    """
                    INSERT INTO players (username, password_hash, role, current_room)
                    VALUES (?, ?, ?, ?)
                """,
                    (admin_user, password_hash, "superuser", "spawn"),
                )
                conn.commit()

                print("\n" + "=" * 60)
                print("SUPERUSER CREATED FROM ENVIRONMENT VARIABLES")
                print("=" * 60)
                print(f"Username: {admin_user}")
                print("=" * 60 + "\n")
        else:
            # No environment variables - print instructions
            print("\n" + "=" * 60)
            print("DATABASE INITIALIZED (no superuser created)")
            print("=" * 60)
            print("To create a superuser, either:")
            print("  1. Set MUD_ADMIN_USER and MUD_ADMIN_PASSWORD environment variables")
            print("     and run: mud-server init-db")
            print("  2. Run interactively: mud-server create-superuser")
            print("=" * 60 + "\n")

    conn.close()


# ============================================================================
# CONNECTION MANAGEMENT
# ============================================================================


def get_connection():
    """
    Get a database connection.

    Creates a new SQLite connection to the database file. Each connection
    should be closed after use to prevent resource leaks.

    Returns:
        sqlite3.Connection object

    Note:
        This function does not use connection pooling. Each call creates
        a new connection. For high-concurrency applications, consider
        implementing connection pooling.

    Example:
        >>> conn = get_connection()
        >>> cursor = conn.cursor()
        >>> # ... do database operations ...
        >>> conn.close()
    """
    return sqlite3.connect(str(DB_PATH))


# ============================================================================
# PLAYER ACCOUNT MANAGEMENT
# ============================================================================


def create_player(username: str) -> bool:
    """
    DEPRECATED: Use create_player_with_password instead.

    This function is kept for backward compatibility but will always fail
    since password_hash is now a required field in the players table.

    Returns:
        False (always fails)

    Note:
        This function exists only to prevent breaking old code that might
        call it. All new code should use create_player_with_password().
    """
    return False


def create_player_with_password(username: str, password: str, role: str = "player") -> bool:
    """
    Create a new player account with hashed password.

    Hashes the password using bcrypt and creates a new player record in
    the database. The player starts at the spawn room with an empty inventory.

    Args:
        username: Unique username (case-sensitive, 2-20 chars recommended)
        password: Plain text password (will be hashed with bcrypt)
        role: User role, one of: "player", "worldbuilder", "admin", "superuser"
              Defaults to "player"

    Returns:
        True if player created successfully
        False if username already exists

    Side Effects:
        - Inserts new row into players table
        - Password is hashed with bcrypt before storage
        - Player spawns at "spawn" room
        - Inventory initialized as empty JSON array

    Example:
        >>> create_player_with_password("newuser", "secret123", "player")
        True
        >>> create_player_with_password("newuser", "password", "player")
        False  # Username already exists
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
    """
    Check if a player account exists in the database.

    Args:
        username: Username to check (case-sensitive)

    Returns:
        True if player exists, False otherwise

    Example:
        >>> player_exists("admin")
        True
        >>> player_exists("nonexistent")
        False
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def verify_password_for_user(username: str, password: str) -> bool:
    """
    Verify a password for a user against their stored bcrypt hash.

    Note: This function only checks password validity, not account status.
    Callers should separately check is_active status to provide specific
    error messages for deactivated accounts.

    Args:
        username: Username to check (case-sensitive)
        password: Plain text password to verify

    Returns:
        True if password matches
        False if user doesn't exist or password wrong

    Security Note:
        This function uses constant-time comparison through bcrypt to
        prevent timing attacks.

    Example:
        >>> verify_password_for_user("admin", "admin123")
        True
        >>> verify_password_for_user("admin", "wrongpass")
        False
    """
    from mud_server.api.password import verify_password

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        return False

    password_hash = result[0]
    return verify_password(password, password_hash)


# ============================================================================
# ROLE MANAGEMENT
# ============================================================================


def get_player_role(username: str) -> str | None:
    """
    Get the role of a player.

    Args:
        username: Player username

    Returns:
        Role string ("player", "worldbuilder", "admin", "superuser")
        None if player doesn't exist
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def set_player_role(username: str, role: str) -> bool:
    """
    Set/change the role of a player.

    Args:
        username: Player username
        role: New role ("player", "worldbuilder", "admin", "superuser")

    Returns:
        True if role updated successfully, False on error
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE players SET role = ? WHERE username = ?", (role, username))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ============================================================================
# PLAYER QUERIES
# ============================================================================


def get_all_players() -> list[dict[str, Any]]:
    """
    Get list of all players with their basic details.

    Returns:
        List of player dictionaries with username, role, created_at,
        last_login, and is_active fields
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT username, role, created_at, last_login, is_active
        FROM players
        ORDER BY created_at DESC
    """)
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


# ============================================================================
# ACCOUNT STATUS MANAGEMENT
# ============================================================================


def deactivate_player(username: str) -> bool:
    """
    Deactivate (ban) a player account.
    Prevents login even with correct password.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE players SET is_active = 0 WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def activate_player(username: str) -> bool:
    """
    Activate (unban) a player account.
    Allows login with correct password.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE players SET is_active = 1 WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ============================================================================
# PASSWORD MANAGEMENT
# ============================================================================


def change_password_for_user(username: str, new_password: str) -> bool:
    """
    Change a user's password (hashes with bcrypt).
    Returns True on success, False on error.
    """
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


# ============================================================================
# PLAYER STATE AND LOCATION
# ============================================================================


def is_player_active(username: str) -> bool:
    """Check if player is active (not banned). Returns False if player doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return bool(result[0]) if result else False


def get_player_room(username: str) -> str | None:
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
        cursor.execute("UPDATE players SET current_room = ? WHERE username = ?", (room, username))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ============================================================================
# INVENTORY MANAGEMENT
# ============================================================================


def get_player_inventory(username: str) -> list[str]:
    """Get player's inventory as list of item IDs. Returns empty list if player doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT inventory FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    if result:
        inventory: list[str] = json.loads(result[0])
        return inventory
    return []


def set_player_inventory(username: str, inventory: list[str]) -> bool:
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


# ============================================================================
# CHAT MESSAGES
# ============================================================================


def add_chat_message(username: str, message: str, room: str, recipient: str | None = None) -> bool:
    """Add chat message. If recipient is None: public. If set: private whisper visible only to sender/recipient."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_messages (username, message, room, recipient) VALUES (?, ?, ?, ?)",
            (username, message, room, recipient),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_room_messages(
    room: str, limit: int = 50, username: str | None = None
) -> list[dict[str, Any]]:
    """Get recent messages from a room. Filters whispers based on username."""
    conn = get_connection()
    cursor = conn.cursor()

    if username:
        # Filter messages: public messages OR whispers to/from this user
        cursor.execute(
            """
            SELECT username, message, timestamp FROM chat_messages
            WHERE room = ? AND (
                recipient IS NULL OR
                recipient = ? OR
                username = ?
            )
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
        """,
            (room, username, username, limit),
        )
    else:
        # No filtering, show all messages
        cursor.execute(
            """
            SELECT username, message, timestamp FROM chat_messages
            WHERE room = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
        """,
            (room, limit),
        )

    results = cursor.fetchall()
    conn.close()

    messages = []
    for user, message, timestamp in reversed(results):
        messages.append({"username": user, "message": message, "timestamp": timestamp})
    return messages


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================


def create_session(username: str, session_id: str) -> bool:
    """Create new session (removes old session for same user). Returns True on success."""
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


def get_active_players() -> list[str]:
    """Get list of currently active players."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM sessions")
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]


def get_players_in_room(room: str) -> list[str]:
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


def cleanup_stale_sessions(max_inactive_minutes: int = 30) -> int:
    """
    Remove sessions that have been inactive for longer than the specified time.

    This function cleans up orphaned sessions that may have been left behind
    when clients crash or disconnect without properly logging out. It's designed
    to be called periodically (e.g., via a scheduled task) to prevent session
    table bloat and ensure accurate active player counts.

    The function uses SQLite's datetime functions to compare the last_activity
    timestamp against the current time minus the threshold. Sessions older than
    the threshold are deleted in a single SQL operation for efficiency.

    Args:
        max_inactive_minutes: Maximum time in minutes since last activity before
            a session is considered stale. Defaults to 30 minutes. A session
            is stale if: now - last_activity > max_inactive_minutes

    Returns:
        Number of sessions removed. Returns 0 if no sessions were removed or
        if an error occurred during the operation.

    Note:
        This function only cleans up the database sessions table. The in-memory
        active_sessions dict in auth.py is NOT updated by this function. For
        full cleanup, use auth.clear_all_sessions() which handles both.

    Example:
        >>> # Remove sessions inactive for more than 30 minutes
        >>> cleanup_stale_sessions(30)
        3  # Removed 3 stale sessions

        >>> # More aggressive cleanup (10 minute threshold)
        >>> cleanup_stale_sessions(10)
        5
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Delete sessions where last_activity is older than max_inactive_minutes
        # The negative sign creates a time offset in the past
        # e.g., '-30 minutes' subtracts 30 minutes from 'now'
        cursor.execute(
            """
            DELETE FROM sessions
            WHERE datetime(last_activity) < datetime('now', ? || ' minutes')
            """,
            (f"-{max_inactive_minutes}",),
        )

        # Get the count of deleted rows before committing
        removed_count: int = cursor.rowcount
        conn.commit()
        conn.close()
        return removed_count
    except Exception:
        # Silently fail and return 0 - this is a cleanup operation that
        # shouldn't crash the server if it fails
        return 0


def clear_all_sessions() -> int:
    """
    Remove all sessions from the database.

    This function performs a complete wipe of the sessions table, removing
    all active sessions regardless of their last_activity timestamp. It is
    designed to be called during server startup to ensure a clean slate.

    Use Cases:
        1. Server startup: Clear orphaned sessions from previous run
        2. Emergency reset: Force all users to re-authenticate
        3. Testing: Reset session state between tests

    The function deletes all rows from the sessions table in a single SQL
    DELETE operation. This is more efficient than iterating through sessions
    individually.

    Returns:
        Number of sessions removed from the database. Returns 0 if no
        sessions existed or if an error occurred.

    Note:
        This function only cleans up the database sessions table. For
        complete session cleanup including in-memory state, use
        auth.clear_all_sessions() which calls this function AND clears
        the active_sessions dict.

    Warning:
        Calling this function will force all connected clients to re-login
        on their next API request. Use with caution in production.

    Example:
        >>> # On server startup
        >>> removed = clear_all_sessions()
        >>> if removed > 0:
        ...     print(f"Cleared {removed} orphaned sessions")
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Delete all sessions - no WHERE clause means all rows
        cursor.execute("DELETE FROM sessions")

        # Get the count of deleted rows before committing
        removed_count: int = cursor.rowcount
        conn.commit()
        conn.close()
        return removed_count
    except Exception:
        # Silently fail and return 0 - startup cleanup shouldn't
        # prevent the server from starting
        return 0


# ============================================================================
# ADMIN QUERIES (Detailed Information)
# ============================================================================


def get_all_players_detailed() -> list[dict[str, Any]]:
    """Get detailed player list including password hash prefix (for admin database viewer)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, password_hash, role, current_room, inventory,
               created_at, last_login, is_active
        FROM players
        ORDER BY created_at DESC
    """)
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


def get_all_sessions() -> list[dict[str, Any]]:
    """Get all active sessions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, session_id, connected_at, last_activity
        FROM sessions
        ORDER BY connected_at DESC
    """)
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


def get_all_chat_messages(limit: int = 100) -> list[dict[str, Any]]:
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
