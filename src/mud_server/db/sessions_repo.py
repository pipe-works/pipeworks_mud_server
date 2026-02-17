"""Session repository operations for the SQLite backend.

This module owns account/in-world session persistence while preserving current
runtime behavior expected by API, engine, and tests.
"""

from __future__ import annotations

from typing import Any, NoReturn

from mud_server.db.connection import connection_scope
from mud_server.db.errors import (
    DatabaseError,
    DatabaseOperationContext,
    DatabaseReadError,
    DatabaseWriteError,
)


def _raise_read_error(operation: str, exc: Exception, *, details: str | None = None) -> NoReturn:
    """Raise a typed repository read error while preserving chained cause."""
    if isinstance(exc, DatabaseError):
        raise exc
    raise DatabaseReadError(
        context=DatabaseOperationContext(operation=operation, details=details),
        cause=exc,
    ) from exc


def _raise_write_error(operation: str, exc: Exception, *, details: str | None = None) -> NoReturn:
    """Raise a typed repository write error while preserving chained cause."""
    if isinstance(exc, DatabaseError):
        raise exc
    raise DatabaseWriteError(
        context=DatabaseOperationContext(operation=operation, details=details),
        cause=exc,
    ) from exc


def _get_user_id_by_username(username: str) -> int | None:
    """Resolve user id for username directly from SQL."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
        return int(row[0]) if row else None
    except Exception as exc:
        _raise_read_error(
            "sessions.get_user_id_by_username",
            exc,
            details=f"username={username!r}",
        )


def _get_character_world_id(character_id: int) -> str | None:
    """Resolve character world id for a character row."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT world_id FROM characters WHERE id = ?", (character_id,))
            row = cursor.fetchone()
        if not row or not row[0]:
            return None
        return str(row[0])
    except Exception as exc:
        _raise_read_error(
            "sessions.get_character_world_id",
            exc,
            details=f"character_id={character_id}",
        )


def create_session(
    user_id: int | str,
    session_id: str,
    *,
    client_type: str = "unknown",
    character_id: int | None = None,
    world_id: str | None = None,
) -> bool:
    """Create account-only or character-bound session row.

    Behavior mirrors the compatibility facade contract:
    - if ``user_id`` is ``str``, resolve by username;
    - when ``character_id`` is provided and ``world_id`` omitted, world is
      derived from the character row;
    - account-only sessions enforce ``world_id = NULL``.
    """
    from mud_server.config import config

    try:
        if isinstance(user_id, str):
            resolved = _get_user_id_by_username(user_id)
            if not resolved:
                return False
            user_id = resolved

        if character_id is not None and world_id is None:
            character_world_id = _get_character_world_id(int(character_id))
            if not character_world_id:
                return False
            world_id = character_world_id

        if character_id is None:
            world_id = None

        with connection_scope(write=True) as conn:
            cursor = conn.cursor()

            if not config.session.allow_multiple_sessions:
                cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

            normalized_client_type = client_type.strip().lower() if client_type else "unknown"

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
                        normalized_client_type,
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
                    (user_id, character_id, world_id, session_id, normalized_client_type),
                )

            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id,),
            )

        return True
    except Exception as exc:
        _raise_write_error(
            "sessions.create_session",
            exc,
            details=f"session_id={session_id!r}",
        )


def set_session_character(session_id: str, character_id: int, *, world_id: str) -> bool:
    """Bind character and explicit world to an existing session row."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sessions SET character_id = ?, world_id = ? WHERE session_id = ?",
                (character_id, world_id, session_id),
            )
            return int(cursor.rowcount or 0) > 0
    except Exception as exc:
        _raise_write_error(
            "sessions.set_session_character",
            exc,
            details=f"session_id={session_id!r}, character_id={character_id}",
        )


def remove_session_by_id(session_id: str) -> bool:
    """Remove one session by its session token."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            removed = int(cursor.rowcount or 0)
            return removed > 0
    except Exception as exc:
        _raise_write_error(
            "sessions.remove_session_by_id",
            exc,
            details=f"session_id={session_id!r}",
        )


def remove_sessions_for_user(user_id: int) -> bool:
    """Remove all sessions for user id."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            removed = int(cursor.rowcount or 0)
            return removed > 0
    except Exception as exc:
        _raise_write_error(
            "sessions.remove_sessions_for_user",
            exc,
            details=f"user_id={user_id}",
        )


def remove_sessions_for_character(character_id: int) -> bool:
    """Remove all sessions bound to character id."""
    return remove_sessions_for_character_count(character_id) > 0


def remove_sessions_for_character_count(character_id: int) -> int:
    """Remove all sessions for character id and return removed row count."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE character_id = ?", (character_id,))
            removed = int(cursor.rowcount or 0)
            return removed
    except Exception as exc:
        _raise_write_error(
            "sessions.remove_sessions_for_character_count",
            exc,
            details=f"character_id={character_id}",
        )


def update_session_activity(session_id: str) -> bool:
    """Update last activity and apply sliding expiration if configured."""
    from mud_server.config import config

    try:
        with connection_scope(write=True) as conn:
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
            return int(cursor.rowcount or 0) > 0
    except Exception as exc:
        _raise_write_error(
            "sessions.update_session_activity",
            exc,
            details=f"session_id={session_id!r}",
        )


def get_session_by_id(session_id: str) -> dict[str, Any] | None:
    """Return session record by token, or ``None`` if absent."""
    try:
        with connection_scope() as conn:
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
    except Exception as exc:
        _raise_read_error(
            "sessions.get_session_by_id",
            exc,
            details=f"session_id={session_id!r}",
        )


def get_active_session_count() -> int:
    """Count active sessions within the configured activity window."""
    from mud_server.config import config

    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            where_clauses = ["(expires_at IS NULL OR datetime(expires_at) > datetime('now'))"]
            params: list[str] = []
            if config.session.active_window_minutes > 0:
                where_clauses.append("datetime(last_activity) >= datetime('now', ?)")
                params.append(f"-{config.session.active_window_minutes} minutes")

            sql = f"""
                SELECT COUNT(*) FROM sessions
                WHERE {' AND '.join(where_clauses)}
            """  # nosec B608
            cursor.execute(sql, params)
            row = cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception as exc:
        _raise_read_error("sessions.get_active_session_count", exc)


def cleanup_expired_sessions() -> int:
    """Delete expired session rows and return number removed."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM sessions
                WHERE expires_at IS NOT NULL AND datetime(expires_at) <= datetime('now')
                """)
            removed_count = int(cursor.rowcount or 0)
            return removed_count
    except Exception as exc:
        _raise_write_error("sessions.cleanup_expired_sessions", exc)


def clear_all_sessions() -> int:
    """Delete all session rows and return number removed."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions")
            removed_count = int(cursor.rowcount or 0)
            return removed_count
    except Exception as exc:
        _raise_write_error("sessions.clear_all_sessions", exc)


def get_active_characters(*, world_id: str | None = None) -> list[str]:
    """Return active character names for optional world scope."""
    try:
        with connection_scope() as conn:
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
        return [row[0] for row in rows]
    except Exception as exc:
        _raise_read_error(
            "sessions.get_active_characters",
            exc,
            details=f"world_id={world_id!r}",
        )
