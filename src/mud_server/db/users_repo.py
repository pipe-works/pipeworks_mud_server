"""User account repository operations for the SQLite backend.

This module isolates account and guest-lifecycle persistence logic from the
monolithic compatibility facade in ``database.py``.
"""

from __future__ import annotations

import sqlite3
from typing import NoReturn

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


def create_user_with_password(
    username: str,
    password: str,
    *,
    role: str = "player",
    account_origin: str = "legacy",
    email_hash: str | None = None,
    is_guest: bool = False,
    guest_expires_at: str | None = None,
) -> bool:
    """Create an account row without provisioning characters.

    Args:
        username: Unique account username.
        password: Plain text password (hashed before persistence).
        role: Role label for authorization policy.
        account_origin: Provenance marker for auditing and cleanup.
        email_hash: Optional hashed email value.
        is_guest: Whether the account is guest-scoped.
        guest_expires_at: Optional guest expiry timestamp.

    Returns:
        ``True`` when the account is created, otherwise ``False`` for
        uniqueness/integrity conflicts.
    """
    from mud_server.api.password import hash_password

    try:
        with connection_scope(write=True) as conn:
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
        return True
    except sqlite3.IntegrityError:
        # Username uniqueness collisions are a normal domain outcome.
        return False
    except Exception as exc:
        _raise_write_error(
            "users.create_user_with_password",
            exc,
            details=f"username={username!r}, role={role!r}, is_guest={int(is_guest)}",
        )


def user_exists(username: str) -> bool:
    """Return ``True`` when a user account exists."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
        return result is not None
    except Exception as exc:
        _raise_read_error("users.user_exists", exc, details=f"username={username!r}")


def get_user_id(username: str) -> int | None:
    """Return user id for ``username`` or ``None`` if missing."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
        return int(row[0]) if row else None
    except Exception as exc:
        _raise_read_error("users.get_user_id", exc, details=f"username={username!r}")


def get_username_by_id(user_id: int) -> str | None:
    """Return username for ``user_id`` or ``None`` if missing."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
        return row[0] if row else None
    except Exception as exc:
        _raise_read_error("users.get_username_by_id", exc, details=f"user_id={user_id}")


def get_user_role(username: str) -> str | None:
    """Return role for ``username`` or ``None`` if missing."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
        return row[0] if row else None
    except Exception as exc:
        _raise_read_error("users.get_user_role", exc, details=f"username={username!r}")


def get_user_account_origin(username: str) -> str | None:
    """Return account origin label for ``username``."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT account_origin FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
        return row[0] if row else None
    except Exception as exc:
        _raise_read_error("users.get_user_account_origin", exc, details=f"username={username!r}")


def set_user_role(username: str, role: str) -> bool:
    """Update user role.

    Returns:
        ``True`` on successful SQL update, otherwise ``False``.
    """
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
        return True
    except Exception as exc:
        _raise_write_error(
            "users.set_user_role",
            exc,
            details=f"username={username!r}, role={role!r}",
        )


def verify_password_for_user(username: str, password: str) -> bool:
    """Verify password against bcrypt hash.

    Uses a dummy hash when user lookup fails to preserve timing behavior.
    """
    from mud_server.api.password import verify_password

    dummy_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G5j1L3tDPZ3q4q"  # nosec B105

    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
    except Exception as exc:
        _raise_read_error(
            "users.verify_password_for_user",
            exc,
            details=f"username={username!r}",
        )

    if not row:
        verify_password(password, dummy_hash)
        return False

    return verify_password(password, row[0])


def is_user_active(username: str) -> bool:
    """Return ``True`` when the account is active."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
        return bool(row[0]) if row else False
    except Exception as exc:
        _raise_read_error("users.is_user_active", exc, details=f"username={username!r}")


def deactivate_user(username: str) -> bool:
    """Deactivate user account."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_active = 0 WHERE username = ?", (username,))
        return True
    except Exception as exc:
        _raise_write_error("users.deactivate_user", exc, details=f"username={username!r}")


def activate_user(username: str) -> bool:
    """Activate user account."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_active = 1 WHERE username = ?", (username,))
        return True
    except Exception as exc:
        _raise_write_error("users.activate_user", exc, details=f"username={username!r}")


def change_password_for_user(username: str, new_password: str) -> bool:
    """Change user password using bcrypt hash."""
    from mud_server.api.password import hash_password

    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            password_hash = hash_password(new_password)
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (password_hash, username),
            )
        return True
    except Exception as exc:
        _raise_write_error(
            "users.change_password_for_user",
            exc,
            details=f"username={username!r}",
        )


def tombstone_user(user_id: int) -> None:
    """Soft-delete account row by marking tombstone fields."""
    try:
        with connection_scope(write=True) as conn:
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
    except Exception as exc:
        _raise_write_error("users.tombstone_user", exc, details=f"user_id={user_id}")


def delete_user(username: str) -> bool:
    """Soft-delete user after detaching characters and removing sessions."""
    user_id = get_user_id(username)
    if not user_id:
        return False

    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE characters SET user_id = NULL WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            cursor.execute(
                "UPDATE users SET is_active = 0, tombstoned_at = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id,),
            )
        return True
    except Exception as exc:
        _raise_write_error("users.delete_user", exc, details=f"username={username!r}")


def unlink_characters_for_user(user_id: int) -> None:
    """Detach all characters from a user id."""
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE characters SET user_id = NULL WHERE user_id = ?", (user_id,))
    except Exception as exc:
        _raise_write_error(
            "users.unlink_characters_for_user",
            exc,
            details=f"user_id={user_id}",
        )


def cleanup_expired_guest_accounts() -> int:
    """Delete expired guest accounts and detach their character ownership.

    Returns:
        Number of user rows removed.
    """
    try:
        with connection_scope(write=True) as conn:
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
            return len(user_ids)
    except Exception as exc:
        _raise_write_error("users.cleanup_expired_guest_accounts", exc)
