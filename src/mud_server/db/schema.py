"""Schema creation and invariant trigger wiring for the SQLite backend.

The schema layer is intentionally isolated from gameplay/query code so schema
changes are reviewable without wading through unrelated repository logic.
"""

from __future__ import annotations

import os
import sqlite3

from mud_server.api.password import hash_password
from mud_server.db.connection import get_connection
from mud_server.db.constants import DEFAULT_WORLD_ID

# Hot-path index rationale:
# 1. sessions user/world activity predicates are used repeatedly for auth,
#    online-status, admin dashboards, and cleanup operations.
# 2. character ownership counts are user+world scoped for slot checks.
# 3. character list and session dashboards sort by activity/created-at often.
# 4. room chat history is always world+room scoped and frequently ordered by time.
HOT_PATH_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_characters_user_world ON characters(user_id, world_id)",
    (
        "CREATE INDEX IF NOT EXISTS idx_characters_user_world_created_at "
        "ON characters(user_id, world_id, created_at)"
    ),
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_character_id ON sessions(character_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_world_id ON sessions(world_id)",
    (
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_activity "
        "ON sessions(user_id, expires_at, last_activity)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_sessions_world_activity "
        "ON sessions(world_id, character_id, expires_at, last_activity)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_sessions_world_last_activity "
        "ON sessions(world_id, last_activity DESC)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_world_room_timestamp "
        "ON chat_messages(world_id, room, timestamp)"
    ),
)


def ensure_character_state_columns(cursor: sqlite3.Cursor) -> None:
    """Ensure state snapshot columns exist on the ``characters`` table.

    SQLite cannot alter table definitions declaratively inside ``CREATE TABLE``
    for pre-existing databases. We therefore perform additive ``ALTER TABLE``
    operations for each required column.
    """
    cursor.execute("PRAGMA table_info(characters)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    columns_to_add = {
        "base_state_json": "TEXT",
        "current_state_json": "TEXT",
        "state_seed": "INTEGER DEFAULT 0 CHECK (state_seed >= 0)",
        "state_version": "TEXT",
        "state_updated_at": "TIMESTAMP",
    }

    for column_name, column_def in columns_to_add.items():
        if column_name in existing_columns:
            continue
        cursor.execute(f"ALTER TABLE characters ADD COLUMN {column_name} {column_def}")

    # Keep null safety for legacy rows that pre-date state snapshot seeding.
    cursor.execute("UPDATE characters SET state_seed = 0 WHERE state_seed IS NULL")


def create_session_invariant_triggers(conn: sqlite3.Connection) -> None:
    """Create triggers that enforce account-first session invariants.

    Invariant model:
    - Account-only session: ``character_id IS NULL`` and ``world_id IS NULL``
    - In-world session: ``character_id IS NOT NULL`` and ``world_id IS NOT NULL``
      with character ownership and world consistency constraints.

    These triggers intentionally protect integrity for both Python helper paths
    and direct SQL writes.
    """
    cursor = conn.cursor()
    cursor.execute("DROP TRIGGER IF EXISTS enforce_session_invariants_insert")
    cursor.execute("DROP TRIGGER IF EXISTS enforce_session_invariants_update")

    cursor.execute("""
        CREATE TRIGGER enforce_session_invariants_insert
        BEFORE INSERT ON sessions
        BEGIN
            SELECT
                CASE
                    WHEN NEW.character_id IS NULL AND NEW.world_id IS NOT NULL
                    THEN RAISE(ABORT, 'session invariant violated: account session has world_id')
                END;

            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL AND NEW.world_id IS NULL
                    THEN RAISE(ABORT, 'session invariant violated: character session missing world_id')
                END;

            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL
                     AND (SELECT id FROM characters WHERE id = NEW.character_id) IS NULL
                    THEN RAISE(ABORT, 'session invariant violated: character does not exist')
                END;

            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL
                     AND (
                        SELECT user_id
                        FROM characters
                        WHERE id = NEW.character_id
                     ) != NEW.user_id
                    THEN RAISE(ABORT, 'session invariant violated: character does not belong to user')
                END;

            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL
                     AND NEW.world_id != (
                        SELECT world_id
                        FROM characters
                        WHERE id = NEW.character_id
                     )
                    THEN RAISE(ABORT, 'session invariant violated: world mismatch for character')
                END;
        END;
    """)

    cursor.execute("""
        CREATE TRIGGER enforce_session_invariants_update
        BEFORE UPDATE OF user_id, character_id, world_id ON sessions
        BEGIN
            SELECT
                CASE
                    WHEN NEW.character_id IS NULL AND NEW.world_id IS NOT NULL
                    THEN RAISE(ABORT, 'session invariant violated: account session has world_id')
                END;

            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL AND NEW.world_id IS NULL
                    THEN RAISE(ABORT, 'session invariant violated: character session missing world_id')
                END;

            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL
                     AND (SELECT id FROM characters WHERE id = NEW.character_id) IS NULL
                    THEN RAISE(ABORT, 'session invariant violated: character does not exist')
                END;

            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL
                     AND (
                        SELECT user_id
                        FROM characters
                        WHERE id = NEW.character_id
                     ) != NEW.user_id
                    THEN RAISE(ABORT, 'session invariant violated: character does not belong to user')
                END;

            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL
                     AND NEW.world_id != (
                        SELECT world_id
                        FROM characters
                        WHERE id = NEW.character_id
                     )
                    THEN RAISE(ABORT, 'session invariant violated: world mismatch for character')
                END;
        END;
    """)


def init_database(*, skip_superuser: bool = False) -> None:
    """Initialize the SQLite database schema and baseline triggers.

    Behavior:
    - Creates required tables and indexes if missing.
    - Seeds the default world row when absent.
    - Ensures character snapshot columns are present.
    - Installs session invariant triggers.
    - Optionally creates a bootstrap superuser from environment variables.

    Args:
        skip_superuser: When True, skip bootstrap superuser creation.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email_hash TEXT UNIQUE,
            role TEXT NOT NULL DEFAULT 'player',
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            is_guest INTEGER NOT NULL DEFAULT 0 CHECK (is_guest IN (0, 1)),
            guest_expires_at TIMESTAMP,
            account_origin TEXT NOT NULL DEFAULT 'legacy',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            tombstoned_at TIMESTAMP
        )
    """)

    # 0.3.10 breaking change:
    # Character names are now unique per world, not globally.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            world_id TEXT NOT NULL,
            inventory TEXT NOT NULL DEFAULT '[]',
            is_guest_created INTEGER NOT NULL DEFAULT 0 CHECK (is_guest_created IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            base_state_json TEXT,
            current_state_json TEXT,
            state_seed INTEGER DEFAULT 0 CHECK (state_seed >= 0),
            state_version TEXT,
            state_updated_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
            UNIQUE(world_id, name)
        )
    """)

    ensure_character_state_columns(cursor)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS axis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            world_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            ordering_json TEXT,
            UNIQUE(world_id, name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS axis_value (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            axis_id INTEGER NOT NULL REFERENCES axis(id) ON DELETE CASCADE,
            value TEXT NOT NULL,
            min_score REAL,
            max_score REAL,
            ordinal INTEGER,
            UNIQUE(axis_id, value)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_type (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            world_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            UNIQUE(world_id, name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS character_axis_score (
            character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            world_id TEXT NOT NULL,
            axis_id INTEGER NOT NULL REFERENCES axis(id) ON DELETE CASCADE,
            axis_score REAL NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (character_id, axis_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS character_locations (
            character_id INTEGER PRIMARY KEY,
            world_id TEXT NOT NULL,
            room_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE CASCADE
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_locations_room_id ON character_locations(room_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_character_locations_world_room "
        "ON character_locations(world_id, room_id)"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            character_id INTEGER,
            world_id TEXT,
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
        CREATE TABLE IF NOT EXISTS event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            world_id TEXT NOT NULL,
            event_type_id INTEGER NOT NULL REFERENCES event_type(id) ON DELETE RESTRICT,
            timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_entity_axis_delta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES event(id) ON DELETE CASCADE,
            character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            axis_id INTEGER NOT NULL REFERENCES axis(id) ON DELETE CASCADE,
            old_score REAL NOT NULL,
            new_score REAL NOT NULL,
            delta REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES event(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER,
            user_id INTEGER,
            message TEXT NOT NULL,
            world_id TEXT NOT NULL,
            room TEXT NOT NULL,
            recipient_character_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE SET NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(recipient_character_id) REFERENCES characters(id) ON DELETE SET NULL
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_world_room ON chat_messages(world_id, room)"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worlds (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS world_permissions (
            user_id INTEGER NOT NULL,
            world_id TEXT NOT NULL,
            can_access INTEGER NOT NULL DEFAULT 1 CHECK (can_access IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, world_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(world_id) REFERENCES worlds(id) ON DELETE CASCADE
        )
    """)

    cursor.execute(
        """
        INSERT OR IGNORE INTO worlds (id, name, description, is_active, config_json)
        VALUES (?, ?, '', 1, '{}')
        """,
        (DEFAULT_WORLD_ID, DEFAULT_WORLD_ID),
    )

    for statement in HOT_PATH_INDEX_STATEMENTS:
        cursor.execute(statement)

    create_session_invariant_triggers(conn)
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
