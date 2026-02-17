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

import sqlite3
from pathlib import Path
from typing import Any

from mud_server.db.constants import DEFAULT_AXIS_SCORE, DEFAULT_WORLD_ID
from mud_server.db.types import AxisRegistrySeedStats, WorldAccessDecision

# ==========================================================================
# CONFIGURATION
# ==========================================================================

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
    from mud_server.db.axis_repo import _generate_state_seed as generate_state_seed_impl

    return generate_state_seed_impl()


def _get_db_path() -> Path:
    """
    Get the database path from configuration.

    Returns:
        Absolute path to the SQLite database file.
    """
    # Phase 1 extraction: delegate path resolution to db.connection.
    from mud_server.db.connection import get_db_path

    return get_db_path()


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
    # Phase 1 extraction: the schema source of truth now lives in db.schema.
    from mud_server.db.schema import init_database as init_database_impl

    init_database_impl(skip_superuser=skip_superuser)


def _ensure_character_state_columns(cursor: sqlite3.Cursor) -> None:
    """
    Ensure state snapshot columns exist on the characters table.

    SQLite does not support adding columns via CREATE TABLE for existing
    databases, so we use ALTER TABLE when new columns are introduced.
    """
    # Phase 1 extraction: maintain compatibility through delegated schema helper.
    from mud_server.db.schema import ensure_character_state_columns

    ensure_character_state_columns(cursor)


def _create_character_limit_triggers(conn: sqlite3.Connection, *, max_slots: int) -> None:
    """
    Create triggers that enforce the per-user character slot limit.

    Note:
        SQLite cannot read config at runtime inside a trigger. We bake the
        configured limit into the trigger at init time.
    """
    from mud_server.db.schema import create_character_limit_triggers

    create_character_limit_triggers(conn, max_slots=max_slots)


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
    from mud_server.db.schema import create_session_invariant_triggers

    create_session_invariant_triggers(conn)


def _generate_default_character_name(cursor: Any, username: str) -> str:
    """
    Generate a unique default character name for the given username.

    The name intentionally differs from the account username to reduce
    confusion in admin views (characters vs. users).
    """
    from mud_server.db.characters_repo import (
        _generate_default_character_name as generate_default_character_name_impl,
    )

    return generate_default_character_name_impl(cursor, username)


def _create_default_character(
    cursor: Any, user_id: int, username: str, *, world_id: str = DEFAULT_WORLD_ID
) -> int:
    """
    Create a default character for a user during bootstrap flows.

    Returns:
        The newly created character id.
    """
    from mud_server.db.characters_repo import (
        _create_default_character as create_default_character_impl,
    )

    return create_default_character_impl(cursor, user_id, username, world_id=world_id)


def _seed_character_location(
    cursor: Any, character_id: int, *, world_id: str = DEFAULT_WORLD_ID
) -> None:
    """Seed a new character's location to the spawn room for the given world."""
    from mud_server.db.characters_repo import (
        _seed_character_location as seed_character_location_impl,
    )

    seed_character_location_impl(cursor, character_id, world_id=world_id)


def _resolve_character_name(cursor: Any, name: str, *, world_id: str | None = None) -> str | None:
    """
    Resolve a character name from either a character name or a username.

    This preserves compatibility with legacy callers that pass usernames
    into character-facing functions by mapping them to the user's first
    character (oldest by created_at).
    """
    from mud_server.db.characters_repo import (
        _resolve_character_name as resolve_character_name_impl,
    )

    return resolve_character_name_impl(cursor, name, world_id=world_id)


def resolve_character_name(name: str, *, world_id: str | None = None) -> str | None:
    """
    Public wrapper for resolving character names from usernames or character names.

    This preserves legacy call sites that still supply usernames while the
    character model is being adopted across the codebase.
    """
    from mud_server.db.characters_repo import (
        resolve_character_name as resolve_character_name_impl,
    )

    return resolve_character_name_impl(name, world_id=world_id)


# ==========================================================================
# CONNECTION MANAGEMENT
# ==========================================================================


def get_connection() -> sqlite3.Connection:
    """
    Create a new SQLite connection to the database file.

    Returns:
        sqlite3.Connection object
    """
    # Phase 1 extraction: delegate connection setup to db.connection so pragma
    # configuration and lock behavior are defined in one module.
    from mud_server.db.connection import get_connection as get_connection_impl

    return get_connection_impl()


# ==========================================================================
# AXIS REGISTRY SEEDING
# ==========================================================================


def _extract_axis_ordering_values(axis_data: dict[str, Any]) -> list[str]:
    """
    Extract ordering values for an axis from the policy payload.

    Args:
        axis_data: Axis definition from axes.yaml.

    Returns:
        List of ordered axis values if present, otherwise an empty list.
    """
    from mud_server.db.axis_repo import (
        _extract_axis_ordering_values as extract_axis_ordering_values_impl,
    )

    return extract_axis_ordering_values_impl(axis_data)


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
    from mud_server.db.axis_repo import seed_axis_registry as seed_axis_registry_impl

    return seed_axis_registry_impl(
        world_id=world_id,
        axes_payload=axes_payload,
        thresholds_payload=thresholds_payload,
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
    from mud_server.db.axis_repo import _get_axis_policy_hash as get_axis_policy_hash_impl

    return get_axis_policy_hash_impl(world_id)


def _resolve_axis_label_for_score(cursor: sqlite3.Cursor, axis_id: int, score: float) -> str | None:
    """
    Resolve an axis score to its label via the axis_value table.

    The axis_value table is treated as a derived cache of policy thresholds.
    If no range matches, the label resolves to None.
    """
    from mud_server.db.axis_repo import (
        _resolve_axis_label_for_score as resolve_axis_label_for_score_impl,
    )

    return resolve_axis_label_for_score_impl(cursor, axis_id, score)


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
    from mud_server.db.axis_repo import (
        _resolve_axis_score_for_label as resolve_axis_score_for_label_impl,
    )

    return resolve_axis_score_for_label_impl(
        cursor,
        world_id=world_id,
        axis_name=axis_name,
        axis_label=axis_label,
    )


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
    from mud_server.db.axis_repo import (
        _flatten_entity_axis_labels as flatten_entity_axis_labels_impl,
    )

    return flatten_entity_axis_labels_impl(entity_state)


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
    from mud_server.db.axis_repo import (
        apply_entity_state_to_character as apply_entity_state_to_character_impl,
    )

    return apply_entity_state_to_character_impl(
        character_id=character_id,
        world_id=world_id,
        entity_state=entity_state,
        seed=seed,
        event_type_name=event_type_name,
    )


def _fetch_character_axis_scores(
    cursor: sqlite3.Cursor, character_id: int, world_id: str
) -> list[dict[str, Any]]:
    """
    Return axis scores for a character joined with axis metadata.

    Returns:
        List of dicts with keys: axis_id, axis_name, axis_score.
    """
    from mud_server.db.axis_repo import (
        _fetch_character_axis_scores as fetch_character_axis_scores_impl,
    )

    return fetch_character_axis_scores_impl(cursor, character_id, world_id)


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
    from mud_server.db.axis_repo import (
        _seed_character_axis_scores as seed_character_axis_scores_impl,
    )

    seed_character_axis_scores_impl(
        cursor,
        character_id=character_id,
        world_id=world_id,
        default_score=default_score,
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
    from mud_server.db.axis_repo import (
        _build_character_state_snapshot as build_character_state_snapshot_impl,
    )

    return build_character_state_snapshot_impl(
        cursor,
        character_id=character_id,
        world_id=world_id,
        seed=seed,
        policy_hash=policy_hash,
    )


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
    from mud_server.db.axis_repo import (
        _seed_character_state_snapshot as seed_character_state_snapshot_impl,
    )

    seed_character_state_snapshot_impl(
        cursor,
        character_id=character_id,
        world_id=world_id,
        seed=seed,
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
    from mud_server.db.axis_repo import (
        _refresh_character_current_snapshot as refresh_character_current_snapshot_impl,
    )

    refresh_character_current_snapshot_impl(
        cursor,
        character_id=character_id,
        world_id=world_id,
        seed_increment=seed_increment,
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
    from mud_server.db.users_repo import create_user_with_password as create_user_with_password_impl

    return create_user_with_password_impl(
        username,
        password,
        role=role,
        account_origin=account_origin,
        email_hash=email_hash,
        is_guest=is_guest,
        guest_expires_at=guest_expires_at,
        create_default_character=create_default_character,
        world_id=world_id,
    )


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
        True if character created, False on constraint/policy violation.

    Policy behavior:
        Character slot limits are enforced per ``(user_id, world_id)`` using
        the resolved world policy from configuration.
    """
    from mud_server.db.characters_repo import (
        create_character_for_user as create_character_for_user_impl,
    )

    return create_character_for_user_impl(
        user_id,
        name,
        is_guest_created=is_guest_created,
        room_id=room_id,
        world_id=world_id,
        state_seed=state_seed,
    )


def user_exists(username: str) -> bool:
    """Return True if a user account exists."""
    from mud_server.db.users_repo import user_exists as user_exists_impl

    return user_exists_impl(username)


def get_user_id(username: str) -> int | None:
    """Return user id for the given username, or None if not found."""
    from mud_server.db.users_repo import get_user_id as get_user_id_impl

    return get_user_id_impl(username)


def get_username_by_id(user_id: int) -> str | None:
    """Return username for a user id, or None if not found."""
    from mud_server.db.users_repo import get_username_by_id as get_username_by_id_impl

    return get_username_by_id_impl(user_id)


def get_user_role(username: str) -> str | None:
    """Return the role for a username, or None if not found."""
    from mud_server.db.users_repo import get_user_role as get_user_role_impl

    return get_user_role_impl(username)


def get_user_account_origin(username: str) -> str | None:
    """Return account_origin for the given username."""
    from mud_server.db.users_repo import get_user_account_origin as get_user_account_origin_impl

    return get_user_account_origin_impl(username)


def set_user_role(username: str, role: str) -> bool:
    """Update a user's role."""
    from mud_server.db.users_repo import set_user_role as set_user_role_impl

    return set_user_role_impl(username, role)


def verify_password_for_user(username: str, password: str) -> bool:
    """
    Verify a password against stored bcrypt hash.

    Uses a dummy hash for timing safety when user doesn't exist.
    """
    from mud_server.db.users_repo import verify_password_for_user as verify_password_for_user_impl

    return verify_password_for_user_impl(username, password)


def is_user_active(username: str) -> bool:
    """Return True if the user is active (not banned)."""
    from mud_server.db.users_repo import is_user_active as is_user_active_impl

    return is_user_active_impl(username)


def deactivate_user(username: str) -> bool:
    """Deactivate (ban) a user account."""
    from mud_server.db.users_repo import deactivate_user as deactivate_user_impl

    return deactivate_user_impl(username)


def activate_user(username: str) -> bool:
    """Activate (unban) a user account."""
    from mud_server.db.users_repo import activate_user as activate_user_impl

    return activate_user_impl(username)


def change_password_for_user(username: str, new_password: str) -> bool:
    """Change a user's password (hashes with bcrypt)."""
    from mud_server.db.users_repo import change_password_for_user as change_password_for_user_impl

    return change_password_for_user_impl(username, new_password)


def tombstone_user(user_id: int) -> None:
    """Tombstone a user account without deleting rows."""
    from mud_server.db.users_repo import tombstone_user as tombstone_user_impl

    tombstone_user_impl(user_id)


def delete_user(username: str) -> bool:
    """
    Delete a user account while preserving character data.

    This performs:
      - Unlink characters from the user (user_id -> NULL)
      - Remove all sessions
      - Tombstone the user row (soft delete)
    """
    from mud_server.db.users_repo import delete_user as delete_user_impl

    return delete_user_impl(username)


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
    from mud_server.db.events_repo import (
        _get_or_create_event_type_id as get_or_create_event_type_id_impl,
    )

    return get_or_create_event_type_id_impl(
        cursor,
        world_id=world_id,
        event_type_name=event_type_name,
        description=description,
    )


def _resolve_axis_id(cursor: sqlite3.Cursor, *, world_id: str, axis_name: str) -> int | None:
    """
    Resolve an axis id from name + world.
    """
    from mud_server.db.events_repo import _resolve_axis_id as resolve_axis_id_impl

    return resolve_axis_id_impl(cursor, world_id=world_id, axis_name=axis_name)


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
    from mud_server.db.events_repo import apply_axis_event as apply_axis_event_impl

    return apply_axis_event_impl(
        world_id=world_id,
        character_id=character_id,
        event_type_name=event_type_name,
        deltas=deltas,
        metadata=metadata,
        event_type_description=event_type_description,
    )


# ==========================================================================
# CHARACTER MANAGEMENT
# ==========================================================================


def character_exists(name: str) -> bool:
    """Return True if a character with this name exists."""
    from mud_server.db.characters_repo import character_exists as character_exists_impl

    return character_exists_impl(name)


def get_character_by_name(name: str) -> dict[str, Any] | None:
    """Return character row by name."""
    from mud_server.db.characters_repo import get_character_by_name as get_character_by_name_impl

    return get_character_by_name_impl(name)


def get_character_by_id(character_id: int) -> dict[str, Any] | None:
    """Return character row by id."""
    from mud_server.db.characters_repo import get_character_by_id as get_character_by_id_impl

    return get_character_by_id_impl(character_id)


def get_character_name_by_id(character_id: int) -> str | None:
    """Return character name for the given id, or None if not found."""
    from mud_server.db.characters_repo import (
        get_character_name_by_id as get_character_name_by_id_impl,
    )

    return get_character_name_by_id_impl(character_id)


def get_user_characters(user_id: int, *, world_id: str | None = None) -> list[dict[str, Any]]:
    """
    Return all characters owned by the given user for a world.

    When world_id is omitted, the default world is used to keep legacy code
    paths functional during the migration.
    """
    from mud_server.db.characters_repo import get_user_characters as get_user_characters_impl

    return get_user_characters_impl(user_id, world_id=world_id)


def get_user_character_world_ids(user_id: int) -> set[str]:
    """
    Return the set of world ids in which the user has characters.

    This is used to enforce allow_multi_world_characters when creating
    new characters.
    """
    from mud_server.db.characters_repo import (
        get_user_character_world_ids as get_user_character_world_ids_impl,
    )

    return get_user_character_world_ids_impl(user_id)


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
    from mud_server.db.characters_repo import tombstone_character as tombstone_character_impl

    return tombstone_character_impl(character_id)


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
    from mud_server.db.characters_repo import delete_character as delete_character_impl

    return delete_character_impl(character_id)


def unlink_characters_for_user(user_id: int) -> None:
    """Detach characters from a user (used when tombstoning guest accounts)."""
    from mud_server.db.users_repo import (
        unlink_characters_for_user as unlink_characters_for_user_impl,
    )

    unlink_characters_for_user_impl(user_id)


# ==========================================================================
# CHARACTER STATE AND LOCATION
# ==========================================================================


def get_character_room(name: str, *, world_id: str | None = None) -> str | None:
    """Return the current room for a character by name within a world."""
    from mud_server.db.characters_repo import get_character_room as get_character_room_impl

    return get_character_room_impl(name, world_id=world_id)


def set_character_room(name: str, room: str, *, world_id: str | None = None) -> bool:
    """Set the current room for a character by name within a world."""
    from mud_server.db.characters_repo import set_character_room as set_character_room_impl

    return set_character_room_impl(name, room, world_id=world_id)


def get_characters_in_room(room: str, *, world_id: str | None = None) -> list[str]:
    """Return character names in a room with active sessions for a world."""
    from mud_server.db.characters_repo import (
        get_characters_in_room as get_characters_in_room_impl,
    )

    return get_characters_in_room_impl(room, world_id=world_id)


# ==========================================================================
# INVENTORY MANAGEMENT
# ==========================================================================


def get_character_inventory(name: str) -> list[str]:
    """Return the character inventory as a list of item ids."""
    from mud_server.db.characters_repo import (
        get_character_inventory as get_character_inventory_impl,
    )

    return get_character_inventory_impl(name)


def set_character_inventory(name: str, inventory: list[str]) -> bool:
    """Set the character inventory."""
    from mud_server.db.characters_repo import (
        set_character_inventory as set_character_inventory_impl,
    )

    return set_character_inventory_impl(name, inventory)


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
    from mud_server.db.chat_repo import add_chat_message as add_chat_message_impl

    return add_chat_message_impl(
        character_name,
        message,
        room,
        recipient_character_name=recipient_character_name,
        recipient=recipient,
        world_id=world_id,
    )


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
    from mud_server.db.chat_repo import get_room_messages as get_room_messages_impl

    return get_room_messages_impl(
        room,
        limit=limit,
        character_name=character_name,
        username=username,
        world_id=world_id,
    )


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
    from mud_server.db.sessions_repo import create_session as create_session_impl

    return create_session_impl(
        user_id,
        session_id,
        client_type=client_type,
        character_id=character_id,
        world_id=world_id,
    )


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
    from mud_server.db.sessions_repo import set_session_character as set_session_character_impl

    return set_session_character_impl(session_id, character_id, world_id=world_id)


def remove_session_by_id(session_id: str) -> bool:
    """Remove a specific session by its session_id."""
    from mud_server.db.sessions_repo import remove_session_by_id as remove_session_by_id_impl

    return remove_session_by_id_impl(session_id)


def remove_sessions_for_user(user_id: int) -> bool:
    """Remove all sessions for a user (used for forced logout/ban)."""
    from mud_server.db.sessions_repo import (
        remove_sessions_for_user as remove_sessions_for_user_impl,
    )

    return remove_sessions_for_user_impl(user_id)


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
    from mud_server.db.sessions_repo import (
        remove_sessions_for_character as remove_sessions_for_character_impl,
    )

    return remove_sessions_for_character_impl(character_id)


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
    from mud_server.db.sessions_repo import (
        remove_sessions_for_character_count as remove_sessions_for_character_count_impl,
    )

    return remove_sessions_for_character_count_impl(character_id)


def update_session_activity(session_id: str) -> bool:
    """
    Update last_activity for a session and extend expiry when sliding is enabled.
    """
    from mud_server.db.sessions_repo import update_session_activity as update_session_activity_impl

    return update_session_activity_impl(session_id)


def get_session_by_id(session_id: str) -> dict[str, Any] | None:
    """Return session record by session_id (or None if not found)."""
    from mud_server.db.sessions_repo import get_session_by_id as get_session_by_id_impl

    return get_session_by_id_impl(session_id)


def get_active_session_count() -> int:
    """Count active sessions within the configured activity window."""
    from mud_server.db.sessions_repo import (
        get_active_session_count as get_active_session_count_impl,
    )

    return get_active_session_count_impl()


def cleanup_expired_sessions() -> int:
    """Remove expired sessions based on expires_at timestamp."""
    from mud_server.db.sessions_repo import (
        cleanup_expired_sessions as cleanup_expired_sessions_impl,
    )

    return cleanup_expired_sessions_impl()


def clear_all_sessions() -> int:
    """Remove all sessions from the database."""
    from mud_server.db.sessions_repo import clear_all_sessions as clear_all_sessions_impl

    return clear_all_sessions_impl()


def get_active_characters(*, world_id: str | None = None) -> list[str]:
    """
    Return active in-world character names.

    Args:
        world_id: Optional world scope. When provided, only sessions bound to
            that world are included. Account-only sessions are excluded.
    """
    from mud_server.db.sessions_repo import get_active_characters as get_active_characters_impl

    return get_active_characters_impl(world_id=world_id)


# ==========================================================================
# GUEST ACCOUNT CLEANUP
# ==========================================================================


def cleanup_expired_guest_accounts() -> int:
    """
    Delete expired guest accounts and unlink their characters.

    Returns:
        Number of guest users deleted.
    """
    from mud_server.db.users_repo import (
        cleanup_expired_guest_accounts as cleanup_expired_guest_accounts_impl,
    )

    return cleanup_expired_guest_accounts_impl()


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
    from mud_server.db.axis_repo import get_character_axis_state as get_character_axis_state_impl

    return get_character_axis_state_impl(character_id)


def get_character_axis_events(character_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    """
    Return recent axis events for a character.

    Args:
        character_id: Character identifier.
        limit: Maximum number of events to return.

    Returns:
        List of events with deltas and metadata.
    """
    from mud_server.db.events_repo import (
        get_character_axis_events as get_character_axis_events_impl,
    )

    return get_character_axis_events_impl(character_id, limit=limit)


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
    from mud_server.db.worlds_repo import get_world_by_id as get_world_by_id_impl

    return get_world_by_id_impl(world_id)


def list_worlds(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    """
    Return all worlds in the catalog.

    Args:
        include_inactive: When False, only active worlds are returned.
    """
    from mud_server.db.worlds_repo import list_worlds as list_worlds_impl

    return list_worlds_impl(include_inactive=include_inactive)


def _query_world_rows(
    cursor: sqlite3.Cursor,
    *,
    include_inactive: bool,
) -> list[tuple[Any, ...]]:
    """
    Query world catalog rows with optional inactive filtering.

    Keeping this query in one helper prevents tiny SQL drifts across APIs that
    need world metadata plus policy decoration.
    """
    from mud_server.db.worlds_repo import _query_world_rows as query_world_rows_impl

    return query_world_rows_impl(cursor, include_inactive=include_inactive)


def _user_has_world_permission(
    cursor: sqlite3.Cursor,
    *,
    user_id: int,
    world_id: str,
) -> bool:
    """Return True when an explicit world_permissions grant exists."""
    from mud_server.db.worlds_repo import (
        _user_has_world_permission as user_has_world_permission_impl,
    )

    return user_has_world_permission_impl(cursor, user_id=user_id, world_id=world_id)


def _count_user_characters_in_world(
    cursor: sqlite3.Cursor,
    *,
    user_id: int,
    world_id: str,
) -> int:
    """Count characters owned by ``user_id`` in ``world_id``."""
    from mud_server.db.worlds_repo import (
        _count_user_characters_in_world as count_user_characters_in_world_impl,
    )

    return count_user_characters_in_world_impl(cursor, user_id=user_id, world_id=world_id)


def _resolve_world_access_for_row(
    cursor: sqlite3.Cursor,
    *,
    user_id: int,
    role: str | None,
    world_row: tuple[Any, ...],
) -> WorldAccessDecision:
    """
    Resolve effective access/create capabilities for a world row.

    This is the canonical policy resolver used by:
    - account dashboard world listings
    - API access checks (`/characters`, `/characters/select`)
    - self-service character creation guardrails
    """
    from mud_server.db.worlds_repo import (
        _resolve_world_access_for_row as resolve_world_access_for_row_impl,
    )

    return resolve_world_access_for_row_impl(
        cursor,
        user_id=user_id,
        role=role,
        world_row=world_row,
    )


def get_world_access_decision(
    user_id: int,
    world_id: str,
    *,
    role: str | None = None,
) -> WorldAccessDecision:
    """
    Resolve account access and create capabilities for one world.

    Returns a denial decision with ``reason='world_not_found'`` when the world
    row does not exist.
    """
    from mud_server.db.worlds_repo import (
        get_world_access_decision as get_world_access_decision_impl,
    )

    return get_world_access_decision_impl(user_id, world_id, role=role)


def can_user_access_world(user_id: int, world_id: str, *, role: str | None = None) -> bool:
    """Return True when the user may access/select the world."""
    from mud_server.db.worlds_repo import can_user_access_world as can_user_access_world_impl

    return can_user_access_world_impl(user_id, world_id, role=role)


def get_user_character_count_for_world(user_id: int, world_id: str) -> int:
    """Return how many characters the user owns in the specified world."""
    from mud_server.db.worlds_repo import (
        get_user_character_count_for_world as get_user_character_count_for_world_impl,
    )

    return get_user_character_count_for_world_impl(user_id, world_id)


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
    from mud_server.db.worlds_repo import get_world_admin_rows as get_world_admin_rows_impl

    return get_world_admin_rows_impl()


def list_worlds_for_user(
    user_id: int,
    *,
    role: str | None = None,
    include_inactive: bool = False,
    include_invite_worlds: bool = False,
) -> list[dict[str, Any]]:
    """
    Return worlds accessible to the given user.

    Behavior by role:
    - Admin/superuser: all worlds are visible and accessible.
    - Other roles:
      - ``include_invite_worlds=False``: return accessible worlds only.
      - ``include_invite_worlds=True``: include invite-locked worlds for UI
        visibility, tagged with ``can_access=False``.

    Access for non-admin roles is resolved using world policy + ownership:
    - explicit world_permissions grant, OR
    - already owns a character in the world, OR
    - world policy is ``open``
    """
    from mud_server.db.worlds_repo import list_worlds_for_user as list_worlds_for_user_impl

    return list_worlds_for_user_impl(
        user_id,
        role=role,
        include_inactive=include_inactive,
        include_invite_worlds=include_invite_worlds,
    )


def _quote_identifier(identifier: str) -> str:
    """Safely quote an SQLite identifier (table/column name)."""
    from mud_server.db.admin_repo import _quote_identifier as quote_identifier_impl

    return quote_identifier_impl(identifier)


def get_table_names() -> list[str]:
    """Return a sorted list of user-defined table names (excludes sqlite_*)."""
    from mud_server.db.admin_repo import get_table_names as get_table_names_impl

    return get_table_names_impl()


def list_tables() -> list[dict[str, Any]]:
    """Return table metadata for admin database browsing."""
    from mud_server.db.admin_repo import list_tables as list_tables_impl

    return list_tables_impl()


def get_schema_map() -> list[dict[str, Any]]:
    """Return table schemas with foreign key relationships for admin tooling."""
    from mud_server.db.admin_repo import get_schema_map as get_schema_map_impl

    return get_schema_map_impl()


def get_table_rows(table_name: str, limit: int = 100) -> tuple[list[str], list[list[Any]]]:
    """Return column names and rows for a given table."""
    from mud_server.db.admin_repo import get_table_rows as get_table_rows_impl

    return get_table_rows_impl(table_name, limit=limit)


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
    from mud_server.db.admin_repo import get_all_users_detailed as get_all_users_detailed_impl

    return get_all_users_detailed_impl()


def get_all_users() -> list[dict[str, Any]]:
    """Return basic user list for admin summaries."""
    from mud_server.db.admin_repo import get_all_users as get_all_users_impl

    return get_all_users_impl()


def get_character_locations(*, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return character location rows with names for admin display."""
    from mud_server.db.admin_repo import get_character_locations as get_character_locations_impl

    return get_character_locations_impl(world_id=world_id)


def get_all_sessions(*, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return all active (non-expired) sessions."""
    from mud_server.db.admin_repo import get_all_sessions as get_all_sessions_impl

    return get_all_sessions_impl(world_id=world_id)


def get_active_connections(*, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return active sessions with activity age in seconds."""
    from mud_server.db.admin_repo import get_active_connections as get_active_connections_impl

    return get_active_connections_impl(world_id=world_id)


def get_all_chat_messages(limit: int = 100, *, world_id: str | None = None) -> list[dict[str, Any]]:
    """Return recent chat messages across all rooms."""
    from mud_server.db.admin_repo import get_all_chat_messages as get_all_chat_messages_impl

    return get_all_chat_messages_impl(limit=limit, world_id=world_id)


if __name__ == "__main__":
    init_database()
    print(f"Database initialized at {_get_db_path()}")
