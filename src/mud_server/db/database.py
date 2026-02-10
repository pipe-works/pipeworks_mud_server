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


def _get_db_path() -> Path:
    """
    Get the database path from configuration.

    The path is resolved from config/server.ini with environment variable
    override (MUD_DB_PATH). Tests should set the environment variable or
    patch the config module.

    Returns:
        Path to the SQLite database file (absolute path).
    """
    from mud_server.config import config

    return config.database.absolute_path


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
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # ========================================================================
    # CREATE PLAYERS TABLE
    # Stores user accounts with authentication and identity information.
    # Gameplay state (like room location) is intentionally kept elsewhere to
    # avoid bloating this table and to allow more flexible state management.
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,           -- Unique username (case-sensitive)
            password_hash TEXT NOT NULL,             -- Bcrypt password hash
            role TEXT NOT NULL DEFAULT 'player',     -- User role for permissions
            inventory TEXT DEFAULT '[]',             -- JSON array of item IDs
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1,             -- Account status (1=active, 0=banned)
            account_origin TEXT NOT NULL DEFAULT 'legacy' -- Account provenance for cleanup
        )
    """)

    # ========================================================================
    # CREATE PLAYER_LOCATIONS TABLE
    # Tracks per-player location (room) outside the players table.
    # This keeps dynamic state separate from core identity/auth fields.
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_locations (
            player_id INTEGER PRIMARY KEY,
            room_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)
    # Index to make room lookups efficient (e.g., who is in a room).
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_locations_room_id ON player_locations(room_id)"
    )

    # Ensure newer columns exist on legacy databases.
    _migrate_players_account_origin(conn)

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
            username TEXT NOT NULL,            -- Username owning the session
            session_id TEXT UNIQUE NOT NULL,   -- Opaque session token (unique)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,              -- NULL means no expiry
            client_type TEXT DEFAULT 'unknown' -- Client identifier (tui, browser, api)
        )
    """)

    # Migrate old sessions schema (username UNIQUE, missing expiry columns) if needed.
    _migrate_sessions_schema(conn)
    _migrate_sessions_client_type(conn)
    _migrate_player_locations(conn)

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
                    INSERT INTO players (username, password_hash, role, account_origin)
                    VALUES (?, ?, ?, ?)
                """,
                    (admin_user, password_hash, "superuser", "system"),
                )
                # Initialize location in a separate table to keep players table lean.
                player_id = cursor.lastrowid
                cursor.execute(
                    """
                    INSERT INTO player_locations (player_id, room_id)
                    VALUES (?, ?)
                """,
                    (player_id, "spawn"),
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


def _migrate_sessions_schema(conn: sqlite3.Connection) -> None:
    """
    Migrate legacy sessions schema to the current format.

    Older schema used:
        - username UNIQUE (single session per user)
        - connected_at instead of created_at
        - no expires_at column

    New schema supports:
        - multiple sessions per user (username NOT unique)
        - created_at / last_activity / expires_at

    The migration is idempotent and only runs when the old schema is detected.
    """
    from mud_server.config import config

    cursor = conn.cursor()

    # Read current column names for the sessions table.
    cursor.execute("PRAGMA table_info(sessions)")
    columns = {row[1] for row in cursor.fetchall()}

    # Detect unique index on username (legacy single-session constraint).
    cursor.execute("PRAGMA index_list('sessions')")
    index_rows = cursor.fetchall()
    username_unique = False
    for index_row in index_rows:
        index_name = index_row[1]
        is_unique = bool(index_row[2])
        if not is_unique:
            continue
        cursor.execute(f"PRAGMA index_info('{index_name}')")
        index_cols = [row[2] for row in cursor.fetchall()]
        if "username" in index_cols:
            username_unique = True
            break

    required_columns = {"created_at", "last_activity", "expires_at"}
    needs_migration = not required_columns.issubset(columns) or username_unique

    if not needs_migration:
        return

    # Preserve legacy data by renaming the old table.
    cursor.execute("ALTER TABLE sessions RENAME TO sessions_old")

    # Recreate sessions table with the new schema.
    cursor.execute("""
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            session_id TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            client_type TEXT DEFAULT 'unknown'
        )
    """)

    # Determine which legacy columns exist.
    cursor.execute("PRAGMA table_info(sessions_old)")
    old_columns = {row[1] for row in cursor.fetchall()}

    created_col = "connected_at" if "connected_at" in old_columns else "created_at"
    if created_col not in old_columns:
        created_col = "CURRENT_TIMESTAMP"

    last_col = "last_activity" if "last_activity" in old_columns else created_col

    # Validate column names to prevent unsafe SQL composition.
    allowed_cols = {"connected_at", "created_at", "last_activity", "CURRENT_TIMESTAMP"}
    if created_col not in allowed_cols or last_col not in allowed_cols:
        raise ValueError("Unexpected legacy session column during migration.")

    # Compute expires_at from last_activity for existing sessions.
    if config.session.ttl_minutes > 0:
        expires_expr = f"datetime({last_col}, ?)"
        expires_param = f"+{config.session.ttl_minutes} minutes"
    else:
        expires_expr = "NULL"
        expires_param = None

    insert_sql = f"""
        INSERT INTO sessions (
            username,
            session_id,
            created_at,
            last_activity,
            expires_at,
            client_type
        )
        SELECT username,
               session_id,
               {created_col},
               {last_col},
               {expires_expr},
               'unknown'
        FROM sessions_old
    """  # nosec B608 - column names are validated above

    if expires_param is not None:
        cursor.execute(insert_sql, (expires_param,))
    else:
        cursor.execute(insert_sql)

    cursor.execute("DROP TABLE sessions_old")


def _migrate_sessions_client_type(conn: sqlite3.Connection) -> None:
    """
    Add the client_type column to sessions if missing.

    This lightweight migration keeps existing data intact and is safe to run
    multiple times. Older rows default to "unknown" when the column is added.
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(sessions)")
    columns = {row[1] for row in cursor.fetchall()}
    if "client_type" in columns:
        return

    cursor.execute("ALTER TABLE sessions ADD COLUMN client_type TEXT DEFAULT 'unknown'")
    cursor.execute("UPDATE sessions SET client_type = 'unknown' WHERE client_type IS NULL")


def _migrate_player_locations(conn: sqlite3.Connection) -> None:
    """
    Backfill player_locations from legacy players.current_room if needed.

    This migration is safe to run multiple times. It only inserts location
    rows when none exist yet.
    """
    cursor = conn.cursor()

    # Only backfill when the location table is empty. This avoids overwriting
    # valid data if the migration has already run in prior startups.
    cursor.execute("SELECT COUNT(*) FROM player_locations")
    existing = int(cursor.fetchone()[0])
    if existing > 0:
        return

    # Detect legacy schema where players.current_room was stored inline.
    cursor.execute("PRAGMA table_info(players)")
    columns = [row[1] for row in cursor.fetchall()]
    has_current_room = "current_room" in columns

    if has_current_room:
        # Legacy path: copy room values into player_locations.
        cursor.execute("SELECT id, current_room FROM players")
        rows = cursor.fetchall()
        cursor.executemany(
            """
            INSERT OR IGNORE INTO player_locations (player_id, room_id)
            VALUES (?, ?)
        """,
            [(row[0], row[1] or "spawn") for row in rows],
        )
    else:
        # New schema path: default all players to spawn until gameplay moves them.
        cursor.execute("SELECT id FROM players")
        rows = cursor.fetchall()
        cursor.executemany(
            """
            INSERT OR IGNORE INTO player_locations (player_id, room_id)
            VALUES (?, ?)
        """,
            [(row[0], "spawn") for row in rows],
        )

    conn.commit()


def _migrate_players_account_origin(conn: sqlite3.Connection) -> None:
    """
    Add account_origin column to players if missing.

    Legacy databases predate account_origin tracking. This migration adds the
    column with a safe default ("legacy") so existing accounts are treated as
    non-temporary and are never purged by visitor cleanup.
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(players)")
    columns = {row[1] for row in cursor.fetchall()}

    if "account_origin" not in columns:
        cursor.execute(
            "ALTER TABLE players ADD COLUMN account_origin TEXT NOT NULL DEFAULT 'legacy'"
        )
        conn.commit()
        return

    cursor.execute(
        "UPDATE players SET account_origin = 'legacy' "
        "WHERE account_origin IS NULL OR account_origin = ''"
    )
    conn.commit()


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
    return sqlite3.connect(str(_get_db_path()))


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


def create_player_with_password(
    username: str,
    password: str,
    role: str = "player",
    account_origin: str = "legacy",
) -> bool:
    """
    Create a new player account with hashed password.

    Hashes the password using bcrypt and creates a new player record in
    the database. The player starts at the spawn room with an empty inventory.

    Args:
        username: Unique username (case-sensitive, 2-20 chars recommended)
        password: Plain text password (will be hashed with bcrypt)
        role: User role, one of: "player", "worldbuilder", "admin", "superuser"
              Defaults to "player"
        account_origin: Account provenance marker used for cleanup decisions.
            Common values: "visitor", "admin", "superuser", "system", "legacy"

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
            INSERT INTO players (username, password_hash, role, account_origin)
            VALUES (?, ?, ?, ?)
        """,
            (username, password_hash, role, account_origin),
        )
        # Seed initial location in its own table to keep the players table focused.
        player_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO player_locations (player_id, room_id)
            VALUES (?, ?)
        """,
            (player_id, "spawn"),
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
        prevent timing attacks. Even when the user doesn't exist, a dummy
        bcrypt comparison is performed to ensure consistent response time.

    Example:
        >>> verify_password_for_user("admin", "admin123")
        True
        >>> verify_password_for_user("admin", "wrongpass")
        False
    """
    from mud_server.api.password import verify_password

    # Dummy hash for timing attack prevention - this is a valid bcrypt hash
    # that will never match any real password (hash of random UUID)
    # Using this ensures constant-time response for non-existent users
    DUMMY_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G5j1L3tDPZ3q4q"  # nosec B105

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM players WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        # User doesn't exist - still perform hash comparison for consistent timing
        verify_password(password, DUMMY_HASH)
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


def get_player_account_origin(username: str) -> str | None:
    """
    Return the account_origin marker for a user.

    Args:
        username: Username to look up.

    Returns:
        The account_origin string, or None if the user does not exist.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT account_origin FROM players WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


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
# ACCOUNT DELETION
# ============================================================================


def delete_player(username: str) -> bool:
    """
    Permanently delete a player and related data.

    This removes:
      - Player record from players table
      - Any player_locations row
      - All active sessions for the user
      - Chat messages sent by the user
      - Chat messages where the user was the recipient

    Returns True on success, False on error.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM players WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False

        player_id = row[0]

        cursor.execute("DELETE FROM player_locations WHERE player_id = ?", (player_id,))
        cursor.execute("DELETE FROM sessions WHERE username = ?", (username,))
        cursor.execute(
            "DELETE FROM chat_messages WHERE username = ? OR recipient = ?",
            (username, username),
        )
        cursor.execute("DELETE FROM players WHERE username = ?", (username,))

        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ============================================================================
# TEMPORARY ACCOUNT CLEANUP
# ============================================================================


def cleanup_temporary_accounts(max_age_hours: int = 24, origin: str = "visitor") -> int:
    """
    Delete temporary accounts older than the specified age.

    This is used for visitor/dev accounts that should be purged regularly.
    It removes related sessions, chat messages, and player_locations rows.

    Args:
        max_age_hours: Age threshold in hours. Accounts older than this are deleted.
        origin: account_origin marker to target (default: "visitor").

    Returns:
        Number of player accounts removed.
    """
    if max_age_hours <= 0:
        return 0

    conn = get_connection()
    cursor = conn.cursor()

    cutoff = f"-{int(max_age_hours)} hours"
    cursor.execute(
        """
        SELECT id, username
        FROM players
        WHERE account_origin = ?
          AND created_at <= datetime('now', ?)
        """,
        (origin, cutoff),
    )
    rows = cursor.fetchall()
    if not rows:
        conn.close()
        return 0

    player_ids = [row[0] for row in rows]
    usernames = [row[1] for row in rows]

    player_placeholders = ",".join(["?"] * len(player_ids))
    username_placeholders = ",".join(["?"] * len(usernames))

    # These IN clauses are built from fixed placeholders to avoid injection.
    cursor.execute(
        f"DELETE FROM player_locations WHERE player_id IN ({player_placeholders})",  # nosec B608
        player_ids,
    )
    cursor.execute(
        f"DELETE FROM sessions WHERE username IN ({username_placeholders})",  # nosec B608
        usernames,
    )
    cursor.execute(
        f"DELETE FROM chat_messages WHERE username IN ({username_placeholders}) "  # nosec B608
        f"OR recipient IN ({username_placeholders})",
        usernames + usernames,
    )
    cursor.execute(
        f"DELETE FROM players WHERE id IN ({player_placeholders})",  # nosec B608
        player_ids,
    )

    conn.commit()
    conn.close()
    return len(rows)


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
    # Resolve the player's id first, then join into player_locations.
    cursor.execute("SELECT id FROM players WHERE username = ?", (username,))
    player_row = cursor.fetchone()
    if not player_row:
        conn.close()
        return None

    player_id = player_row[0]
    cursor.execute("SELECT room_id FROM player_locations WHERE player_id = ?", (player_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def set_player_room(username: str, room: str) -> bool:
    """Set the current room of a player."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Look up player id and upsert location for that player.
        cursor.execute("SELECT id FROM players WHERE username = ?", (username,))
        player_row = cursor.fetchone()
        if not player_row:
            conn.close()
            return False

        player_id = player_row[0]
        cursor.execute(
            """
            INSERT INTO player_locations (player_id, room_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(player_id) DO UPDATE
                SET room_id = excluded.room_id,
                    updated_at = CURRENT_TIMESTAMP
        """,
            (player_id, room),
        )
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


def create_session(username: str, session_id: str, client_type: str = "unknown") -> bool:
    """
    Create a new session record for a user.

    Behavior depends on configuration:
      - allow_multiple_sessions = False: all existing sessions for the user
        are removed before inserting the new one (single-session enforcement).
      - allow_multiple_sessions = True: the new session is added without
        removing existing sessions (multi-device support).

    The new session will have created_at/last_activity set to now,
    expires_at calculated using the configured session TTL, and a
    client_type tag for UI/connection tracking.
    """
    from mud_server.config import config

    try:
        conn = get_connection()
        cursor = conn.cursor()

        if not config.session.allow_multiple_sessions:
            # Enforce one-session-per-user by removing existing sessions.
            cursor.execute("DELETE FROM sessions WHERE username = ?", (username,))

        client_type = client_type.strip().lower() if client_type else "unknown"

        if config.session.ttl_minutes > 0:
            cursor.execute(
                """
                INSERT INTO sessions (
                    username,
                    session_id,
                    created_at,
                    last_activity,
                    expires_at,
                    client_type
                )
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, datetime('now', ?), ?)
                """,
                (username, session_id, f"+{config.session.ttl_minutes} minutes", client_type),
            )
        else:
            cursor.execute(
                """
                INSERT INTO sessions (
                    username,
                    session_id,
                    created_at,
                    last_activity,
                    expires_at,
                    client_type
                )
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, ?)
                """,
                (username, session_id, client_type),
            )

        # Update last_login for the user on successful session creation.
        cursor.execute(
            "UPDATE players SET last_login = CURRENT_TIMESTAMP WHERE username = ?",
            (username,),
        )

        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_active_players() -> list[str]:
    """Get list of active players (deduplicated, excludes stale sessions)."""
    from mud_server.config import config

    conn = get_connection()
    cursor = conn.cursor()
    where_clauses = ["(expires_at IS NULL OR datetime(expires_at) > datetime('now'))"]
    params: list[str] = []
    if config.session.active_window_minutes > 0:
        where_clauses.append("datetime(last_activity) >= datetime('now', ?)")
        params.append(f"-{config.session.active_window_minutes} minutes")

    sql = f"""
        SELECT DISTINCT username FROM sessions
        WHERE {" AND ".join(where_clauses)}
    """  # nosec B608 - clauses are built from fixed, internal strings
    cursor.execute(sql, params)
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]


def get_players_in_room(room: str) -> list[str]:
    """Get list of players currently in a room."""
    conn = get_connection()
    cursor = conn.cursor()
    # Join player_locations to find players in the requested room, then
    # filter to active (non-expired) sessions.
    cursor.execute(
        """
        SELECT DISTINCT p.username FROM players p
        JOIN player_locations l ON p.id = l.player_id
        JOIN sessions s ON p.username = s.username
        WHERE l.room_id = ?
          AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
    """,
        (room,),
    )
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]


def get_player_locations() -> list[dict[str, Any]]:
    """
    Get player location rows with usernames for admin display.

    Returns:
        List of dicts with player_id, username, room_id, updated_at.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id,
               p.username,
               l.room_id,
               l.updated_at
        FROM player_locations l
        JOIN players p ON p.id = l.player_id
        ORDER BY p.id
    """)
    results = cursor.fetchall()
    conn.close()

    locations: list[dict[str, Any]] = []
    for row in results:
        locations.append(
            {
                "player_id": row[0],
                "username": row[1],
                "room_id": row[2],
                "updated_at": row[3],
            }
        )
    return locations


def remove_session(username: str) -> bool:
    """Remove all sessions for a user (used for forced logout/ban)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE username = ?", (username,))
        removed = int(cursor.rowcount or 0)
        conn.commit()
        conn.close()
        return removed > 0
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


def update_session_activity(session_id: str) -> bool:
    """
    Update last_activity for a session and extend expiry when sliding is enabled.

    This function is called on every authenticated request. It updates the
    last_activity timestamp and (if configured) bumps expires_at forward to
    maintain a sliding expiration window.
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
        SELECT username, session_id, created_at, last_activity, expires_at, client_type
        FROM sessions WHERE session_id = ?
        """,
        (session_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "username": row[0],
        "session_id": row[1],
        "created_at": row[2],
        "last_activity": row[3],
        "expires_at": row[4],
        "client_type": row[5],
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
    """  # nosec B608 - clauses are built from fixed, internal strings
    cursor.execute(sql, params)
    row = cursor.fetchone()
    count = int(row[0]) if row else 0
    conn.close()
    return count


def cleanup_expired_sessions() -> int:
    """
    Remove expired sessions based on expires_at timestamp.

    Returns the number of sessions removed. This is safe to call on startup
    and periodically to avoid table bloat.
    """
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
        Sessions are database-backed; this operation is authoritative.

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


def _quote_identifier(identifier: str) -> str:
    """
    Safely quote an SQLite identifier (table/column name).

    This prevents injection when identifiers must be interpolated into SQL.
    """
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
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]


def list_tables() -> list[dict[str, Any]]:
    """
    Return table metadata for admin database browsing.

    Each entry includes table name, column list, and row count.
    """
    conn = get_connection()
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


def get_table_rows(table_name: str, limit: int = 100) -> tuple[list[str], list[list[Any]]]:
    """
    Return column names and rows for a given table.

    Raises:
        ValueError: If the table does not exist.
    """
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


def get_all_players_detailed() -> list[dict[str, Any]]:
    """Get detailed player list including password hash prefix (for admin database viewer)."""
    conn = get_connection()
    cursor = conn.cursor()
    # Pull current room from player_locations so admin views stay accurate
    # after moving room state out of the players table.
    cursor.execute("""
        SELECT p.id,
               p.username,
               p.password_hash,
               p.role,
               p.account_origin,
               l.room_id,
               p.inventory,
               p.created_at,
               p.last_login,
               p.is_active
        FROM players p
        LEFT JOIN player_locations l ON p.id = l.player_id
        ORDER BY p.created_at DESC
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
                "account_origin": row[4],
                "current_room": row[5],
                "inventory": row[6],
                "created_at": row[7],
                "last_login": row[8],
                "is_active": bool(row[9]),
            }
        )
    return players


def get_all_sessions() -> list[dict[str, Any]]:
    """Get all active (non-expired) sessions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, session_id, created_at, last_activity, expires_at, client_type
        FROM sessions
        WHERE expires_at IS NULL OR datetime(expires_at) > datetime('now')
        ORDER BY created_at DESC
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
                "created_at": row[3],
                "last_activity": row[4],
                "expires_at": row[5],
                "client_type": row[6],
            }
        )
    return sessions


def get_active_connections() -> list[dict[str, Any]]:
    """
    Get active sessions with activity age in seconds.

    Sessions are filtered by expiry and the configured activity window.
    """
    from mud_server.config import config

    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = ["(expires_at IS NULL OR datetime(expires_at) > datetime('now'))"]
    params: list[str] = []
    if config.session.active_window_minutes > 0:
        where_clauses.append("datetime(last_activity) >= datetime('now', ?)")
        params.append(f"-{config.session.active_window_minutes} minutes")

    sql = f"""
        SELECT id,
               username,
               session_id,
               created_at,
               last_activity,
               expires_at,
               client_type,
               CAST(strftime('%s','now') - strftime('%s', last_activity) AS INTEGER) AS age_seconds
        FROM sessions
        WHERE {" AND ".join(where_clauses)}
        ORDER BY last_activity DESC
    """  # nosec B608 - clauses are built from fixed, internal strings
    cursor.execute(sql, params)
    results = cursor.fetchall()
    conn.close()

    sessions: list[dict[str, Any]] = []
    for row in results:
        sessions.append(
            {
                "id": row[0],
                "username": row[1],
                "session_id": row[2],
                "created_at": row[3],
                "last_activity": row[4],
                "expires_at": row[5],
                "client_type": row[6],
                "age_seconds": row[7],
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
    print(f"Database initialized at {_get_db_path()}")
