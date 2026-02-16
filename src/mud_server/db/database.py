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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import randbelow
from typing import Any, cast

# ==========================================================================
# CONFIGURATION
# ==========================================================================

DEFAULT_WORLD_ID = "pipeworks_web"
DEFAULT_AXIS_SCORE = 0.5
# Default world identifier used for legacy code paths that do not yet provide
# an explicit world_id. This keeps the server functional during migration and
# will be replaced by config-driven defaults in a later phase.


def _generate_state_seed() -> int:
    """
    Generate a non-zero seed for character state snapshots.

    We use ``secrets.randbelow`` instead of the global ``random`` module so
    snapshot seeding has zero interaction with any deterministic RNG usage in
    gameplay systems. This keeps "seed randomization" isolated and prevents
    accidental RNG state pollution.

    Returns:
        Positive integer in the inclusive range [1, 2_147_483_647].
    """
    return randbelow(2_147_483_647) + 1


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
            world_id TEXT NOT NULL,
            inventory TEXT NOT NULL DEFAULT '[]',
            is_guest_created INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            base_state_json TEXT,
            current_state_json TEXT,
            state_seed INTEGER DEFAULT 0,
            state_version TEXT,
            state_updated_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    # Ensure newly added state snapshot columns exist for legacy databases.
    _ensure_character_state_columns(cursor)

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
        "CREATE INDEX IF NOT EXISTS idx_character_locations_room_id "
        "ON character_locations(room_id)"
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
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_world_room "
        "ON chat_messages(world_id, room)"
    )

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS world_permissions (
            user_id INTEGER NOT NULL,
            world_id TEXT NOT NULL,
            can_access INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, world_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(world_id) REFERENCES worlds(id) ON DELETE CASCADE
        )
    """)

    # Ensure the default world exists in the catalog.
    cursor.execute(
        """
        INSERT OR IGNORE INTO worlds (id, name, description, is_active, config_json)
        VALUES (?, ?, '', 1, '{}')
        """,
        (DEFAULT_WORLD_ID, DEFAULT_WORLD_ID),
    )

    _create_character_limit_triggers(conn, max_slots=config.characters.max_slots)
    _create_session_invariant_triggers(conn)

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


def _ensure_character_state_columns(cursor: sqlite3.Cursor) -> None:
    """
    Ensure state snapshot columns exist on the characters table.

    SQLite does not support adding columns via CREATE TABLE for existing
    databases, so we use ALTER TABLE when new columns are introduced.
    """
    cursor.execute("PRAGMA table_info(characters)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    columns_to_add = {
        "base_state_json": "TEXT",
        "current_state_json": "TEXT",
        "state_seed": "INTEGER DEFAULT 0",
        "state_version": "TEXT",
        "state_updated_at": "TIMESTAMP",
    }

    for column_name, column_def in columns_to_add.items():
        if column_name in existing_columns:
            continue
        cursor.execute(f"ALTER TABLE characters ADD COLUMN {column_name} {column_def}")

    if "state_seed" in existing_columns or "state_seed" in columns_to_add:
        cursor.execute("UPDATE characters SET state_seed = 0 WHERE state_seed IS NULL")


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


def _create_session_invariant_triggers(conn: sqlite3.Connection) -> None:
    """
    Create triggers that enforce account-first session invariants.

    Invariant model:
    - Account-only session:
        character_id IS NULL and world_id IS NULL
    - In-world character session:
        character_id IS NOT NULL and world_id IS NOT NULL
        character must belong to session user
        world_id must match the character's world

    Why triggers:
    - They protect integrity even when callers bypass Python helpers and write
      directly via SQL.
    - They apply consistently for both INSERT and UPDATE operations.
    """
    cursor = conn.cursor()
    cursor.execute("DROP TRIGGER IF EXISTS enforce_session_invariants_insert")
    cursor.execute("DROP TRIGGER IF EXISTS enforce_session_invariants_update")

    cursor.execute("""
        CREATE TRIGGER enforce_session_invariants_insert
        BEFORE INSERT ON sessions
        BEGIN
            -- Account-only sessions must never carry world bindings.
            SELECT
                CASE
                    WHEN NEW.character_id IS NULL AND NEW.world_id IS NOT NULL
                    THEN RAISE(ABORT, 'session invariant violated: account session has world_id')
                END;

            -- Character-bound sessions must always carry world bindings.
            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL AND NEW.world_id IS NULL
                    THEN RAISE(ABORT, 'session invariant violated: character session missing world_id')
                END;

            -- Character binding must reference an existing character row.
            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL
                     AND (SELECT id FROM characters WHERE id = NEW.character_id) IS NULL
                    THEN RAISE(ABORT, 'session invariant violated: character does not exist')
                END;

            -- Character binding must belong to the same user.
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

            -- Session world must mirror the character's world.
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
            -- Account-only sessions must never carry world bindings.
            SELECT
                CASE
                    WHEN NEW.character_id IS NULL AND NEW.world_id IS NOT NULL
                    THEN RAISE(ABORT, 'session invariant violated: account session has world_id')
                END;

            -- Character-bound sessions must always carry world bindings.
            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL AND NEW.world_id IS NULL
                    THEN RAISE(ABORT, 'session invariant violated: character session missing world_id')
                END;

            -- Character binding must reference an existing character row.
            SELECT
                CASE
                    WHEN NEW.character_id IS NOT NULL
                     AND (SELECT id FROM characters WHERE id = NEW.character_id) IS NULL
                    THEN RAISE(ABORT, 'session invariant violated: character does not exist')
                END;

            -- Character binding must belong to the same user.
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

            -- Session world must mirror the character's world.
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


def _create_default_character(
    cursor: Any, user_id: int, username: str, *, world_id: str = DEFAULT_WORLD_ID
) -> int:
    """
    Create a default character for a user during bootstrap flows.

    Returns:
        The newly created character id.
    """
    character_name = _generate_default_character_name(cursor, username)
    cursor.execute(
        """
        INSERT INTO characters (user_id, name, world_id, is_guest_created)
        VALUES (?, ?, ?, 0)
    """,
        (user_id, character_name, world_id),
    )
    character_id = cursor.lastrowid
    if character_id is None:
        raise ValueError("Failed to create default character.")
    character_id_int = int(character_id)

    # Seed axis scores + snapshots so new characters have baseline state.
    _seed_character_axis_scores(cursor, character_id=character_id_int, world_id=world_id)
    _seed_character_state_snapshot(cursor, character_id=character_id_int, world_id=world_id)

    return character_id_int


def _seed_character_location(
    cursor: Any, character_id: int, *, world_id: str = DEFAULT_WORLD_ID
) -> None:
    """Seed a new character's location to the spawn room for the given world."""
    cursor.execute(
        """
        INSERT INTO character_locations (character_id, world_id, room_id)
        VALUES (?, ?, ?)
    """,
        (character_id, world_id, "spawn"),
    )


def _resolve_character_name(cursor: Any, name: str, *, world_id: str | None = None) -> str | None:
    """
    Resolve a character name from either a character name or a username.

    This preserves compatibility with legacy callers that pass usernames
    into character-facing functions by mapping them to the user's first
    character (oldest by created_at).
    """
    if world_id is None:
        world_id = DEFAULT_WORLD_ID

    cursor.execute(
        "SELECT name FROM characters WHERE name = ? AND world_id = ? LIMIT 1",
        (name, world_id),
    )
    row = cursor.fetchone()
    if row:
        return cast(str, row[0])

    cursor.execute("SELECT id FROM users WHERE username = ? LIMIT 1", (name,))
    user_row = cursor.fetchone()
    if not user_row:
        return None

    user_id = int(user_row[0])
    cursor.execute(
        "SELECT name FROM characters WHERE user_id = ? AND world_id = ? "
        "ORDER BY created_at ASC LIMIT 1",
        (user_id, world_id),
    )
    char_row = cursor.fetchone()
    return cast(str, char_row[0]) if char_row else None


def resolve_character_name(name: str, *, world_id: str | None = None) -> str | None:
    """
    Public wrapper for resolving character names from usernames or character names.

    This preserves legacy call sites that still supply usernames while the
    character model is being adopted across the codebase.
    """
    conn = get_connection()
    cursor = conn.cursor()
    resolved = _resolve_character_name(cursor, name, world_id=world_id)
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
# AXIS REGISTRY SEEDING
# ==========================================================================


@dataclass(slots=True)
class AxisRegistrySeedStats:
    """
    Summary of axis registry seeding work performed.

    Attributes:
        axes_upserted: Number of axis rows inserted or updated.
        axis_values_inserted: Number of axis_value rows inserted.
        axes_missing_thresholds: Number of axes that had no thresholds entry.
        axis_values_skipped: Number of axis_value rows skipped due to missing data.
    """

    axes_upserted: int
    axis_values_inserted: int
    axes_missing_thresholds: int
    axis_values_skipped: int


def _extract_axis_ordering_values(axis_data: dict[str, Any]) -> list[str]:
    """
    Extract ordering values for an axis from the policy payload.

    Args:
        axis_data: Axis definition from axes.yaml.

    Returns:
        List of ordered axis values if present, otherwise an empty list.
    """
    ordering = (axis_data or {}).get("ordering")
    if not isinstance(ordering, dict):
        return []

    values = ordering.get("values")
    if not isinstance(values, list):
        return []

    return [str(value) for value in values]


def seed_axis_registry(
    *,
    world_id: str,
    axes_payload: dict[str, Any],
    thresholds_payload: dict[str, Any],
) -> AxisRegistrySeedStats:
    """
    Insert or update axis registry rows based on policy payloads.

    This function mirrors world policy files into normalized DB tables:
    - ``axis`` rows (ordering_json + description)
    - ``axis_value`` rows (thresholds + ordinal mapping)

    The registry is treated as derived data. If thresholds are missing for
    an axis, axis_value rows are skipped to avoid overwriting prior data.

    Args:
        world_id: World identifier the policy applies to.
        axes_payload: Parsed ``axes.yaml`` payload (dict).
        thresholds_payload: Parsed ``thresholds.yaml`` payload (dict).

    Returns:
        AxisRegistrySeedStats with counts of inserts and skips.
    """
    axes_definitions = axes_payload.get("axes") or {}
    thresholds_definitions = thresholds_payload.get("axes") or {}

    axes_upserted = 0
    axis_values_inserted = 0
    axes_missing_thresholds = 0
    axis_values_skipped = 0

    conn = get_connection()
    cursor = conn.cursor()

    for axis_name, axis_data in axes_definitions.items():
        axis_data = axis_data or {}

        # Store ordering as JSON so the DB preserves world policy intent.
        ordering = axis_data.get("ordering")
        ordering_json = json.dumps(ordering, sort_keys=True) if ordering else None

        # Persist axis registry row (description/order updates are idempotent).
        cursor.execute(
            """
            INSERT INTO axis (world_id, name, description, ordering_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(world_id, name) DO UPDATE SET
                description = excluded.description,
                ordering_json = excluded.ordering_json
            """,
            (
                world_id,
                axis_name,
                axis_data.get("description"),
                ordering_json,
            ),
        )
        axes_upserted += 1

        cursor.execute(
            "SELECT id FROM axis WHERE world_id = ? AND name = ? LIMIT 1",
            (world_id, axis_name),
        )
        axis_row = cursor.fetchone()
        if not axis_row:
            # Defensive: if row resolution fails, skip axis values rather than crashing.
            axis_values_skipped += 1
            continue
        axis_id = int(axis_row[0])

        thresholds = thresholds_definitions.get(axis_name)
        if not isinstance(thresholds, dict):
            axes_missing_thresholds += 1
            continue

        values = thresholds.get("values") or {}
        if not isinstance(values, dict):
            axis_values_skipped += 1
            continue

        # Use ordering values for ordinals when available.
        ordering_values = _extract_axis_ordering_values(axis_data)
        ordinal_map = {value: index for index, value in enumerate(ordering_values)}

        # Remove existing axis values so registry always reflects policy.
        cursor.execute("DELETE FROM axis_value WHERE axis_id = ?", (axis_id,))

        for value_name, value_bounds in values.items():
            value_bounds = value_bounds or {}
            min_score = value_bounds.get("min")
            max_score = value_bounds.get("max")

            # Normalize numeric bounds where possible (None preserves unknowns).
            min_score = float(min_score) if min_score is not None else None
            max_score = float(max_score) if max_score is not None else None

            cursor.execute(
                """
                INSERT INTO axis_value (axis_id, value, min_score, max_score, ordinal)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    axis_id,
                    str(value_name),
                    min_score,
                    max_score,
                    ordinal_map.get(str(value_name)),
                ),
            )
            axis_values_inserted += 1

    conn.commit()
    conn.close()

    return AxisRegistrySeedStats(
        axes_upserted=axes_upserted,
        axis_values_inserted=axis_values_inserted,
        axes_missing_thresholds=axes_missing_thresholds,
        axis_values_skipped=axis_values_skipped,
    )


# ==========================================================================
# CHARACTER STATE SNAPSHOTS
# ==========================================================================


def _get_axis_policy_hash(world_id: str) -> str | None:
    """
    Return the policy hash for a world, if the policy loader is available.

    The hash is derived from the on-disk policy files, keeping state snapshots
    tied to a specific policy version.
    """
    from pathlib import Path

    from mud_server.config import config
    from mud_server.policies import AxisPolicyLoader

    loader = AxisPolicyLoader(worlds_root=Path(config.worlds.worlds_root))
    _payload, report = loader.load(world_id)
    return report.policy_hash


def _resolve_axis_label_for_score(cursor: sqlite3.Cursor, axis_id: int, score: float) -> str | None:
    """
    Resolve an axis score to its label via the axis_value table.

    The axis_value table is treated as a derived cache of policy thresholds.
    If no range matches, the label resolves to None.
    """
    cursor.execute(
        """
        SELECT value
        FROM axis_value
        WHERE axis_id = ?
          AND (? >= min_score OR min_score IS NULL)
          AND (? <= max_score OR max_score IS NULL)
        ORDER BY
          CASE WHEN ordinal IS NULL THEN 1 ELSE 0 END,
          ordinal,
          min_score
        LIMIT 1
        """,
        (axis_id, score, score),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def _resolve_axis_score_for_label(
    cursor: sqlite3.Cursor, *, world_id: str, axis_name: str, axis_label: str
) -> float | None:
    """
    Resolve a policy label into a numeric score for a world axis.

    This performs the inverse of ``_resolve_axis_label_for_score`` by reading
    the threshold bounds stored in ``axis_value`` and producing a representative
    score. Midpoint values are used when both bounds are present.

    Args:
        cursor: Active cursor inside a transaction/connection.
        world_id: World identifier.
        axis_name: Axis name (for example ``wealth``).
        axis_label: Axis label (for example ``well-kept``).

    Returns:
        Numeric score for the label, or ``None`` when no mapping exists.
    """
    cursor.execute(
        """
        SELECT av.min_score, av.max_score
        FROM axis_value av
        JOIN axis a ON a.id = av.axis_id
        WHERE a.world_id = ? AND a.name = ? AND av.value = ?
        LIMIT 1
        """,
        (world_id, axis_name, axis_label),
    )
    row = cursor.fetchone()
    if not row:
        return None

    min_score = float(row[0]) if row[0] is not None else None
    max_score = float(row[1]) if row[1] is not None else None
    if min_score is not None and max_score is not None:
        return (min_score + max_score) / 2.0
    if min_score is not None:
        return min_score
    if max_score is not None:
        return max_score
    return DEFAULT_AXIS_SCORE


def _flatten_entity_axis_labels(entity_state: dict[str, Any]) -> dict[str, str]:
    """
    Flatten entity payload axis labels into ``axis_name -> label`` mappings.

    Supported shapes:
    - ``{"character": {...}, "occupation": {...}}`` from the entity API.
    - ``{"axes": {"wealth": {"label": "well-kept"}}}`` snapshot-like payloads.

    Args:
        entity_state: Raw entity-state payload.

    Returns:
        Flat mapping of axis names to label strings.
    """
    labels: dict[str, str] = {}

    for group in ("character", "occupation"):
        group_payload = entity_state.get(group)
        if isinstance(group_payload, dict):
            for axis_name, axis_value in group_payload.items():
                if isinstance(axis_value, str) and axis_value.strip():
                    labels[str(axis_name)] = axis_value.strip()

    axes_payload = entity_state.get("axes")
    if isinstance(axes_payload, dict):
        for axis_name, axis_value in axes_payload.items():
            if isinstance(axis_value, dict):
                label = axis_value.get("label")
                if isinstance(label, str) and label.strip():
                    labels[str(axis_name)] = label.strip()
            elif isinstance(axis_value, str) and axis_value.strip():
                labels[str(axis_name)] = axis_value.strip()

    return labels


def apply_entity_state_to_character(
    *,
    character_id: int,
    world_id: str,
    entity_state: dict[str, Any],
    seed: int | None = None,
    event_type_name: str = "entity_profile_seeded",
) -> int | None:
    """
    Apply entity-state labels to a character through the axis event ledger.

    The entity payload is converted into target score labels, then transformed
    into numeric deltas against the character's current axis scores. The final
    mutation is persisted through ``apply_axis_event`` so snapshots and ledger
    records stay in sync.

    Args:
        character_id: Character receiving seeded axis values.
        world_id: Character world id.
        entity_state: Entity payload containing character/occupation axis labels.
        seed: Optional generation seed recorded in event metadata.
        event_type_name: Ledger event type name.

    Returns:
        Event id when deltas were applied, otherwise ``None`` when no axis
        mappings were resolvable from the payload.
    """
    axis_labels = _flatten_entity_axis_labels(entity_state)
    if not axis_labels:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    try:
        current_scores = {
            row["axis_name"]: float(row["axis_score"])
            for row in _fetch_character_axis_scores(cursor, character_id, world_id)
        }

        deltas: dict[str, float] = {}
        for axis_name, axis_label in axis_labels.items():
            target_score = _resolve_axis_score_for_label(
                cursor,
                world_id=world_id,
                axis_name=axis_name,
                axis_label=axis_label,
            )
            if target_score is None:
                continue

            old_score = current_scores.get(axis_name, DEFAULT_AXIS_SCORE)
            delta = target_score - old_score
            if abs(delta) < 1e-9:
                continue
            deltas[axis_name] = delta
    finally:
        conn.close()

    if not deltas:
        return None

    metadata: dict[str, str] = {
        "source": "entity_state_api",
        "axis_count": str(len(deltas)),
    }
    if seed is not None:
        metadata["seed"] = str(seed)

    return apply_axis_event(
        world_id=world_id,
        character_id=character_id,
        event_type_name=event_type_name,
        event_type_description=(
            "Initial axis profile generated from external entity-state integration."
        ),
        deltas=deltas,
        metadata=metadata,
    )


def _fetch_character_axis_scores(
    cursor: sqlite3.Cursor, character_id: int, world_id: str
) -> list[dict[str, Any]]:
    """
    Return axis scores for a character joined with axis metadata.

    Returns:
        List of dicts with keys: axis_id, axis_name, axis_score.
    """
    cursor.execute(
        """
        SELECT a.id, a.name, s.axis_score
        FROM character_axis_score s
        JOIN axis a ON a.id = s.axis_id
        WHERE s.character_id = ? AND s.world_id = ?
        ORDER BY a.name
        """,
        (character_id, world_id),
    )
    return [
        {
            "axis_id": int(row[0]),
            "axis_name": row[1],
            "axis_score": float(row[2]),
        }
        for row in cursor.fetchall()
    ]


def _seed_character_axis_scores(
    cursor: sqlite3.Cursor,
    *,
    character_id: int,
    world_id: str,
    default_score: float = DEFAULT_AXIS_SCORE,
) -> None:
    """
    Seed axis score rows for a new character.

    Args:
        cursor: Active SQLite cursor within an open transaction.
        character_id: Character id to seed.
        world_id: World identifier for the character.
        default_score: Default numeric score for each axis.
    """
    cursor.execute(
        """
        SELECT id, name
        FROM axis
        WHERE world_id = ?
        ORDER BY name
        """,
        (world_id,),
    )
    for axis_id, _axis_name in cursor.fetchall():
        cursor.execute(
            """
            INSERT OR IGNORE INTO character_axis_score
                (character_id, world_id, axis_id, axis_score)
            VALUES (?, ?, ?, ?)
            """,
            (character_id, world_id, int(axis_id), float(default_score)),
        )


def _build_character_state_snapshot(
    cursor: sqlite3.Cursor,
    *,
    character_id: int,
    world_id: str,
    seed: int,
    policy_hash: str | None,
) -> dict[str, Any]:
    """
    Build a character snapshot from axis scores + policy thresholds.

    Snapshot contract (current canonical shape):
        {
            "world_id": <str>,
            "seed": <int>,
            "policy_hash": <str|None>,
            "axes": {
                "<axis_name>": {"score": <float>, "label": <str|None>}
            }
        }

    Forward-compatibility note:
        We intentionally keep ``axes`` flat so existing API/UI consumers do not
        break. Group projections such as ``axis_groups`` or ``axes_by_group``
        should be introduced as additive fields in a future non-breaking change.

    Returns:
        Snapshot payload suitable for JSON serialization.
    """
    axes_payload: dict[str, Any] = {}
    for axis_row in _fetch_character_axis_scores(cursor, character_id, world_id):
        label = _resolve_axis_label_for_score(cursor, axis_row["axis_id"], axis_row["axis_score"])
        axes_payload[axis_row["axis_name"]] = {
            "score": axis_row["axis_score"],
            "label": label,
        }

    return {
        "world_id": world_id,
        "seed": seed,
        "policy_hash": policy_hash,
        "axes": axes_payload,
    }


def _seed_character_state_snapshot(
    cursor: sqlite3.Cursor,
    *,
    character_id: int,
    world_id: str,
    seed: int | None = None,
) -> None:
    """
    Seed base/current state snapshots for a character.

    Base snapshots are immutable; current snapshots are updated whenever
    axis scores change. For now, this is only called at creation time.

    Notes:
        - When ``seed`` is omitted, a non-zero random seed is generated.
        - Existing non-zero ``state_seed`` values are preserved.
        - Snapshot JSON and persisted ``state_seed`` are kept aligned.
    """
    # Resolve the effective seed before building JSON so the serialized
    # snapshot seed always matches the stored state_seed column.
    cursor.execute("SELECT state_seed FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    existing_seed = int(row[0]) if row and row[0] is not None else 0
    effective_seed = existing_seed if existing_seed > 0 else (seed or _generate_state_seed())

    policy_hash = _get_axis_policy_hash(world_id)
    snapshot = _build_character_state_snapshot(
        cursor,
        character_id=character_id,
        world_id=world_id,
        seed=effective_seed,
        policy_hash=policy_hash,
    )
    snapshot_json = json.dumps(snapshot, sort_keys=True)
    state_updated_at = datetime.now(UTC).isoformat()

    cursor.execute(
        """
        UPDATE characters
        SET base_state_json = COALESCE(base_state_json, ?),
            current_state_json = ?,
            state_seed = CASE
                WHEN state_seed IS NULL OR state_seed = 0 THEN ?
                ELSE state_seed
            END,
            state_version = ?,
            state_updated_at = ?
        WHERE id = ?
        """,
        (
            snapshot_json,
            snapshot_json,
            effective_seed,
            policy_hash,
            state_updated_at,
            character_id,
        ),
    )


def _refresh_character_current_snapshot(
    cursor: sqlite3.Cursor,
    *,
    character_id: int,
    world_id: str,
    seed_increment: int = 1,
) -> None:
    """
    Refresh the current snapshot for a character after axis score updates.

    Args:
        cursor: Active SQLite cursor within an open transaction.
        character_id: Target character id.
        world_id: World identifier for the character.
        seed_increment: Amount to increment the stored state_seed.
    """
    cursor.execute("SELECT state_seed FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    current_seed = int(row[0]) if row and row[0] is not None else 0
    new_seed = current_seed + seed_increment

    policy_hash = _get_axis_policy_hash(world_id)
    snapshot = _build_character_state_snapshot(
        cursor,
        character_id=character_id,
        world_id=world_id,
        seed=new_seed,
        policy_hash=policy_hash,
    )
    snapshot_json = json.dumps(snapshot, sort_keys=True)
    state_updated_at = datetime.now(UTC).isoformat()

    cursor.execute(
        """
        UPDATE characters
        SET current_state_json = ?,
            state_seed = ?,
            state_version = ?,
            state_updated_at = ?
        WHERE id = ?
        """,
        (
            snapshot_json,
            new_seed,
            policy_hash,
            state_updated_at,
            character_id,
        ),
    )


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
    create_default_character: bool = False,
    world_id: str = DEFAULT_WORLD_ID,
) -> bool:
    """
    Create a new user account only (character provisioning is explicit).

    Args:
        username: Unique account username.
        password: Plain text password (hashed with bcrypt).
        role: Role string.
        account_origin: Provenance marker for cleanup/auditing.
        email_hash: Hashed email value (nullable during development).
        is_guest: Whether this is a guest account.
        guest_expires_at: Expiration timestamp for guest accounts.
        create_default_character: Deprecated compatibility flag. Automatic
            character creation has been removed and this must remain False.
        world_id: Deprecated compatibility argument retained for legacy call
            signatures; ignored because account creation no longer provisions
            characters.

    Returns:
        True if created successfully, False if username already exists.
    """
    from mud_server.api.password import hash_password

    # Breaking change (Option A):
    # account creation and character creation are now always separate flows.
    if create_default_character:
        raise ValueError(
            "Automatic character creation is removed. "
            "Call create_character_for_user() explicitly."
        )
    _ = world_id

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
    world_id: str = DEFAULT_WORLD_ID,
    state_seed: int | None = None,
) -> bool:
    """
    Create a character for an existing user.

    Args:
        user_id: Owning user id.
        name: Character name (globally unique for now).
        is_guest_created: Marks characters created from guest flow.
        room_id: Initial room id.
        world_id: World the character belongs to.
        state_seed: Optional explicit seed for initial snapshot state.

    Returns:
        True if character created, False on constraint violation.
    """
    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO characters (user_id, name, world_id, is_guest_created)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, name, world_id, int(is_guest_created)),
        )
        character_id = cursor.lastrowid
        if character_id is None:
            raise ValueError("Failed to create character.")
        character_id = int(character_id)
        _seed_character_location(cursor, character_id, world_id=world_id)
        _seed_character_axis_scores(cursor, character_id=character_id, world_id=world_id)
        _seed_character_state_snapshot(
            cursor,
            character_id=character_id,
            world_id=world_id,
            seed=state_seed,
        )
        if room_id != "spawn":
            cursor.execute(
                """
                UPDATE character_locations
                SET room_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE character_id = ?
            """,
                (room_id, character_id),
            )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # Important: close the connection on constraint errors to avoid
        # leaving SQLite write locks behind during retry loops.
        if conn is not None:
            conn.close()
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
# EVENT LEDGER MUTATIONS
# ==========================================================================


def _get_or_create_event_type_id(
    cursor: sqlite3.Cursor,
    *,
    world_id: str,
    event_type_name: str,
    description: str | None = None,
) -> int:
    """
    Return event_type id for a world, creating it if missing.
    """
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
    """
    Resolve an axis id from name + world.
    """
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
    """
    Apply an axis event to a character and record it in the ledger.

    This is the authoritative mutation path for axis scores. It:
    - inserts an event row
    - records per-axis deltas
    - updates character_axis_score
    - refreshes the current snapshot

    The entire operation is atomic. If any axis is invalid, no changes are written.

    Args:
        world_id: World identifier for the event.
        character_id: Character receiving the deltas.
        event_type_name: Registry name for the event type.
        deltas: Mapping of axis_name -> delta.
        metadata: Optional event metadata to store as key/value pairs.
        event_type_description: Optional description if event_type must be created.

    Returns:
        Newly created event id.
    """
    if not deltas:
        raise ValueError("Event deltas must not be empty.")

    conn = get_connection()
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

        _refresh_character_current_snapshot(
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
        SELECT id, user_id, name, world_id, inventory, is_guest_created, created_at, updated_at
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
        "world_id": row[3],
        "inventory": row[4],
        "is_guest_created": bool(row[5]),
        "created_at": row[6],
        "updated_at": row[7],
    }


def get_character_by_id(character_id: int) -> dict[str, Any] | None:
    """Return character row by id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, name, world_id, inventory, is_guest_created, created_at, updated_at
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
        "world_id": row[3],
        "inventory": row[4],
        "is_guest_created": bool(row[5]),
        "created_at": row[6],
        "updated_at": row[7],
    }


def get_character_name_by_id(character_id: int) -> str | None:
    """Return character name for the given id, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_user_characters(user_id: int, *, world_id: str | None = None) -> list[dict[str, Any]]:
    """
    Return all characters owned by the given user for a world.

    When world_id is omitted, the default world is used to keep legacy code
    paths functional during the migration.
    """
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, world_id, is_guest_created, created_at, updated_at
        FROM characters
        WHERE user_id = ? AND world_id = ?
        ORDER BY created_at ASC
    """,
        (user_id, world_id),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": int(row[0]),
            "name": row[1],
            "world_id": row[2],
            "is_guest_created": bool(row[3]),
            "created_at": row[4],
            "updated_at": row[5],
        }
        for row in rows
    ]


def get_user_character_world_ids(user_id: int) -> set[str]:
    """
    Return the set of world ids in which the user has characters.

    This is used to enforce allow_multi_world_characters when creating
    new characters.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT world_id
        FROM characters
        WHERE user_id = ?
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return {row[0] for row in rows}


def tombstone_character(character_id: int) -> bool:
    """
    Tombstone a character without deleting historical rows.

    Tombstoning performs a soft removal by:
    - unlinking ownership (``user_id = NULL``)
    - renaming to a unique tombstone marker so the original name can be reused
    - updating ``updated_at`` to preserve auditability

    Args:
        character_id: Character id to tombstone.

    Returns:
        True when tombstoned, False when character does not exist.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return False

    original_name = str(row[0] or "character")
    tombstone_name = f"tombstone_{character_id}_{original_name}"
    cursor.execute(
        """
        UPDATE characters
        SET user_id = NULL,
            name = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (tombstone_name, character_id),
    )
    conn.commit()
    conn.close()
    return True


def delete_character(character_id: int) -> bool:
    """
    Permanently delete a character and cascade dependent rows.

    This removes the character row itself; configured foreign-key actions handle
    related tables (for example, locations and axis scores cascade, session/chat
    references are set to NULL where applicable).

    Args:
        character_id: Character id to remove.

    Returns:
        True when a row was deleted, otherwise False.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM characters WHERE id = ?", (character_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


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


def get_character_room(name: str, *, world_id: str | None = None) -> str | None:
    """Return the current room for a character by name within a world."""
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    conn = get_connection()
    cursor = conn.cursor()
    resolved_name = _resolve_character_name(cursor, name, world_id=world_id)
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
        "SELECT room_id FROM character_locations WHERE character_id = ? AND world_id = ?",
        (character_id, world_id),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def set_character_room(name: str, room: str, *, world_id: str | None = None) -> bool:
    """Set the current room for a character by name within a world."""
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    try:
        conn = get_connection()
        cursor = conn.cursor()
        resolved_name = _resolve_character_name(cursor, name, world_id=world_id)
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
            INSERT INTO character_locations (character_id, world_id, room_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(character_id) DO UPDATE
                SET world_id = excluded.world_id,
                    room_id = excluded.room_id,
                    updated_at = CURRENT_TIMESTAMP
        """,
            (character_id, world_id, room),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_characters_in_room(room: str, *, world_id: str | None = None) -> list[str]:
    """Return character names in a room with active sessions for a world."""
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT c.name
        FROM characters c
        JOIN character_locations l ON c.id = l.character_id
        JOIN sessions s ON s.character_id = c.id
        WHERE l.world_id = ?
          AND l.room_id = ?
          AND (s.world_id IS NULL OR s.world_id = ?)
          AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
    """,
        (world_id, room, world_id),
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
    *,
    world_id: str | None = None,
) -> bool:
    """
    Add a chat message for a character.

    Supports optional whisper recipient and uses world scoping. If world_id
    is omitted, the default world is used during migration.
    """
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    try:
        conn = get_connection()
        cursor = conn.cursor()

        resolved_sender = _resolve_character_name(cursor, character_name, world_id=world_id)
        if not resolved_sender:
            conn.close()
            return False

        cursor.execute(
            "SELECT id, user_id FROM characters WHERE name = ? AND world_id = ?",
            (resolved_sender, world_id),
        )
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
            resolved_recipient = _resolve_character_name(
                cursor, recipient_character_name, world_id=world_id
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
    world_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Get recent messages from a room. Filters whispers based on character.

    Messages are scoped to the provided world_id; default world is used when
    omitted to preserve legacy code paths during migration.
    """
    if world_id is None:
        world_id = DEFAULT_WORLD_ID
    conn = get_connection()
    cursor = conn.cursor()

    if character_name is None and username is not None:
        character_name = username

    if character_name:
        resolved_name = _resolve_character_name(cursor, character_name, world_id=world_id)
        if resolved_name is None and username is not None:
            resolved_name = _resolve_character_name(cursor, username, world_id=world_id)
        if not resolved_name:
            conn.close()
            return []

        cursor.execute(
            "SELECT id FROM characters WHERE name = ? AND world_id = ?",
            (resolved_name, world_id),
        )
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
    world_id: str | None = None,
) -> bool:
    """
    Create a new session record for a user.

    Session model invariant (account-first authentication):
      - Account-only session (default login):
          character_id = NULL, world_id = NULL
      - In-world session (after explicit selection):
          character_id != NULL, world_id != NULL

    Behavior depends on configuration:
      - allow_multiple_sessions = False: remove existing sessions for the user
      - allow_multiple_sessions = True: keep existing sessions

    Important:
      - This function never auto-selects a character.
      - Character/world binding must be explicit via ``set_session_character``
        (or by passing both ``character_id`` and ``world_id`` directly).
    """
    from mud_server.config import config

    try:
        if isinstance(user_id, str):
            resolved = get_user_id(user_id)
            if not resolved:
                return False
            user_id = resolved

        # Derive world binding only when the caller explicitly binds a
        # character but omits world_id.
        if character_id is not None and world_id is None:
            character = get_character_by_id(int(character_id))
            if not character:
                return False
            character_world_id = character.get("world_id")
            if not character_world_id:
                return False
            world_id = str(character_world_id)

        # Enforce account-only invariant: sessions without a bound character
        # must not carry a world binding.
        if character_id is None:
            world_id = None

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
                    world_id,
                    session_id,
                    created_at,
                    last_activity,
                    expires_at,
                    client_type
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, datetime('now', ?), ?)
            """,
                (
                    user_id,
                    character_id,
                    world_id,
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
                    world_id,
                    session_id,
                    created_at,
                    last_activity,
                    expires_at,
                    client_type
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, ?)
            """,
                (user_id, character_id, world_id, session_id, client_type),
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


def set_session_character(
    session_id: str, character_id: int, *, world_id: str | None = None
) -> bool:
    """
    Attach a character + world to an existing account session.

    Args:
        session_id: Existing session identifier.
        character_id: Character id to bind.
        world_id: Optional world id override.

    Returns:
        True when the session update succeeds; otherwise False.

    Behavior:
      - When ``world_id`` is omitted, we resolve it from the character row.
      - We do not assume a default world for character binding.
    """
    try:
        if world_id is None:
            character = get_character_by_id(character_id)
            if not character:
                return False
            character_world_id = character.get("world_id")
            if not character_world_id:
                return False
            world_id = str(character_world_id)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET character_id = ?, world_id = ? WHERE session_id = ?",
            (character_id, world_id, session_id),
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


def remove_sessions_for_character(character_id: int) -> bool:
    """
    Remove all sessions currently bound to a specific character.

    This is used before destructive character-management actions so no active
    session remains attached to a character that is being tombstoned/deleted.

    Args:
        character_id: Character id whose sessions should be removed.

    Returns:
        True when at least one session was removed; otherwise False.
    """
    return remove_sessions_for_character_count(character_id) > 0


def remove_sessions_for_character_count(character_id: int) -> int:
    """
    Remove all sessions bound to a specific character and return removal count.

    This is useful for moderation flows where callers need deterministic
    feedback (for example, "0 sessions removed" vs "3 sessions removed") for
    UI messaging and audit trails.

    Args:
        character_id: Character id whose sessions should be removed.

    Returns:
        Number of removed session rows. Returns ``0`` on failure.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE character_id = ?", (character_id,))
        removed = int(cursor.rowcount or 0)
        conn.commit()
        conn.close()
        return removed
    except Exception:
        return 0


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
        SELECT user_id, character_id, world_id, session_id, created_at, last_activity, expires_at,
               client_type
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
        "world_id": row[2],
        "session_id": row[3],
        "created_at": row[4],
        "last_activity": row[5],
        "expires_at": row[6],
        "client_type": row[7],
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


def get_active_characters(*, world_id: str | None = None) -> list[str]:
    """
    Return active in-world character names.

    Args:
        world_id: Optional world scope. When provided, only sessions bound to
            that world are included. Account-only sessions are excluded.
    """
    conn = get_connection()
    cursor = conn.cursor()
    if world_id is None:
        cursor.execute("""
            SELECT DISTINCT c.name
            FROM sessions s
            JOIN characters c ON c.id = s.character_id
            WHERE s.character_id IS NOT NULL
              AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
            """)
    else:
        cursor.execute(
            """
            SELECT DISTINCT c.name
            FROM sessions s
            JOIN characters c ON c.id = s.character_id
            WHERE s.character_id IS NOT NULL
              AND s.world_id = ?
              AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
            """,
            (world_id,),
        )
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


# ==========================================================================
# GUEST ACCOUNT CLEANUP
# ==========================================================================


def cleanup_expired_guest_accounts() -> int:
    """
    Delete expired guest accounts and unlink their characters.

    Returns:
        Number of guest users deleted.
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
        f"DELETE FROM sessions WHERE user_id IN ({placeholders})",  # nosec B608
        user_ids,
    )
    cursor.execute(
        f"DELETE FROM users WHERE id IN ({placeholders})",  # nosec B608
        user_ids,
    )

    conn.commit()
    conn.close()
    return len(user_ids)


# ==========================================================================
# AXIS STATE QUERIES
# ==========================================================================


def get_character_axis_state(character_id: int) -> dict[str, Any] | None:
    """
    Return axis scores and snapshot data for a character.

    Args:
        character_id: Character identifier.

    Returns:
        Dict containing character state info or None if character is missing.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id,
               world_id,
               base_state_json,
               current_state_json,
               state_seed,
               state_version,
               state_updated_at
        FROM characters
        WHERE id = ?
        """,
        (character_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    world_id = row[1]
    base_state_json = row[2]
    current_state_json = row[3]
    state_seed = row[4]
    state_version = row[5]
    state_updated_at = row[6]

    def _safe_load(payload: str | None) -> dict[str, Any] | None:
        if not payload:
            return None
        try:
            return cast(dict[str, Any], json.loads(payload))
        except json.JSONDecodeError:
            return None

    axes = []
    for axis_row in _fetch_character_axis_scores(cursor, character_id, world_id):
        label = _resolve_axis_label_for_score(cursor, axis_row["axis_id"], axis_row["axis_score"])
        axes.append(
            {
                "axis_id": axis_row["axis_id"],
                "axis_name": axis_row["axis_name"],
                "axis_score": axis_row["axis_score"],
                "axis_label": label,
            }
        )

    conn.close()

    return {
        "character_id": int(row[0]),
        "world_id": world_id,
        "state_seed": state_seed,
        "state_version": state_version,
        "state_updated_at": state_updated_at,
        "base_state": _safe_load(base_state_json),
        "current_state": _safe_load(current_state_json),
        "axes": axes,
    }


def get_character_axis_events(character_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    """
    Return recent axis events for a character.

    Args:
        character_id: Character identifier.
        limit: Maximum number of events to return.

    Returns:
        List of events with deltas and metadata.
    """
    conn = get_connection()
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

    ordered_events = [events[int(event_id)] for event_id in event_ids if int(event_id) in events]
    return ordered_events


# ==========================================================================
# ADMIN QUERIES
# ==========================================================================


def get_world_by_id(world_id: str) -> dict[str, Any] | None:
    """
    Return a world catalog entry by id.

    Args:
        world_id: World identifier (primary key).

    Returns:
        Dict with world fields or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, description, is_active, config_json, created_at
        FROM worlds
        WHERE id = ?
        """,
        (world_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "is_active": bool(row[3]),
        "config_json": row[4],
        "created_at": row[5],
    }


def list_worlds(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    """
    Return all worlds in the catalog.

    Args:
        include_inactive: When False, only active worlds are returned.
    """
    conn = get_connection()
    cursor = conn.cursor()
    if include_inactive:
        cursor.execute("""
            SELECT id, name, description, is_active, config_json, created_at
            FROM worlds
            ORDER BY id
            """)
    else:
        cursor.execute("""
            SELECT id, name, description, is_active, config_json, created_at
            FROM worlds
            WHERE is_active = 1
            ORDER BY id
            """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "is_active": bool(row[3]),
            "config_json": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]


def get_world_admin_rows() -> list[dict[str, Any]]:
    """
    Return world-level operational rows for admin/superuser tooling.

    This API view is intentionally richer than ``list_worlds``. It combines:
    - static world catalog metadata (id/name/description/is_active)
    - live session activity (session counts, character counts, last activity)
    - kickable in-world character session rows for operations UI

    "Online" semantics:
    - ``is_online`` is True when at least one active session in the world has
      a bound character (in-world presence), not merely an account login.

    Returns:
        List of world dictionaries sorted by world id.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT w.id,
               w.name,
               w.description,
               w.is_active,
               w.config_json,
               w.created_at,
               s.session_id,
               s.last_activity,
               s.client_type,
               c.id,
               c.name,
               u.username
        FROM worlds w
        LEFT JOIN sessions s
               ON s.world_id = w.id
              AND s.character_id IS NOT NULL
              AND (s.expires_at IS NULL OR datetime(s.expires_at) > datetime('now'))
        LEFT JOIN characters c ON c.id = s.character_id
        LEFT JOIN users u ON u.id = s.user_id
        ORDER BY w.id ASC, datetime(s.last_activity) DESC
        """)
    rows = cursor.fetchall()
    conn.close()

    worlds_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        world_id = cast(str, row[0])
        world = worlds_by_id.get(world_id)
        if world is None:
            world = {
                "world_id": world_id,
                "name": row[1],
                "description": row[2],
                "is_active": bool(row[3]),
                "config_json": row[4],
                "created_at": row[5],
                "active_session_count": 0,
                "active_character_count": 0,
                "is_online": False,
                "last_activity": None,
                "active_characters": [],
                "_session_ids": set(),
                "_character_ids": set(),
            }
            worlds_by_id[world_id] = world

        session_id = row[6]
        if session_id:
            session_ids = cast(set[str], world["_session_ids"])
            if session_id not in session_ids:
                session_ids.add(session_id)
                world["active_session_count"] = int(world["active_session_count"]) + 1

            if world["last_activity"] is None and row[7] is not None:
                world["last_activity"] = row[7]

        character_id = row[9]
        if character_id is None:
            continue

        character_ids = cast(set[int], world["_character_ids"])
        if int(character_id) not in character_ids:
            character_ids.add(int(character_id))
            world["active_character_count"] = int(world["active_character_count"]) + 1

        world["is_online"] = True
        world["active_characters"].append(
            {
                "character_id": int(character_id),
                "character_name": row[10],
                "username": row[11],
                "session_id": session_id,
                "last_activity": row[7],
                "client_type": row[8] or "unknown",
            }
        )

    result: list[dict[str, Any]] = []
    for world_id in sorted(worlds_by_id):
        world = worlds_by_id[world_id]
        world.pop("_session_ids", None)
        world.pop("_character_ids", None)
        result.append(world)
    return result


def list_worlds_for_user(
    user_id: int,
    *,
    role: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """
    Return worlds accessible to the given user.

    Admins and superusers have implicit access to all worlds. Other roles
    must have a world_permissions row with can_access=1.
    """
    if role is None:
        username = get_username_by_id(user_id)
        if username:
            role = get_user_role(username)

    if role in {"admin", "superuser"}:
        return list_worlds(include_inactive=include_inactive)

    conn = get_connection()
    cursor = conn.cursor()
    if include_inactive:
        cursor.execute(
            """
            SELECT w.id, w.name, w.description, w.is_active, w.config_json, w.created_at
            FROM worlds w
            JOIN world_permissions p ON p.world_id = w.id
            WHERE p.user_id = ? AND p.can_access = 1
            ORDER BY w.id
            """,
            (user_id,),
        )
    else:
        cursor.execute(
            """
            SELECT w.id, w.name, w.description, w.is_active, w.config_json, w.created_at
            FROM worlds w
            JOIN world_permissions p ON p.world_id = w.id
            WHERE p.user_id = ? AND p.can_access = 1 AND w.is_active = 1
            ORDER BY w.id
            """,
            (user_id,),
        )
    rows = cursor.fetchall()
    if rows:
        conn.close()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "is_active": bool(row[3]),
                "config_json": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]

    # Fallback: allow worlds where the user already has characters.
    cursor.execute(
        """
        SELECT DISTINCT w.id, w.name, w.description, w.is_active, w.config_json, w.created_at
        FROM worlds w
        JOIN characters c ON c.world_id = w.id
        WHERE c.user_id = ?
        ORDER BY w.id
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "is_active": bool(row[3]),
            "config_json": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]


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


def get_schema_map() -> list[dict[str, Any]]:
    """Return table schemas with foreign key relationships for admin tooling."""
    conn = get_connection()
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
    """
    Return detailed, active-account user rows for the admin Active Users view.

    Tombstoned accounts are intentionally excluded from this query. The Active
    Users card is the operational surface for live/managed accounts; historical
    tombstone audit remains available via character tombstone data and raw table
    inspection endpoints.

    Online semantics:
    - ``is_online_account`` is true when any active session exists.
    - ``is_online_in_world`` is true when any active session is bound to a
      character.
    - ``online_world_ids`` lists worlds where the user currently has active
      in-world presence (character-bound sessions only).
    """
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

    users = []
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


def get_character_locations(*, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return character location rows with names for admin display."""
    conn = get_connection()
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
    """Return all active (non-expired) sessions."""
    conn = get_connection()
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

    sessions = []
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
    """Return recent chat messages across all rooms."""
    conn = get_connection()
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

    messages = []
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
    """
    Backward-compatible alias for create_user_with_password().

    Important:
        This helper creates account rows only. Character provisioning must be
        performed separately via create_character_for_user().
    """
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
