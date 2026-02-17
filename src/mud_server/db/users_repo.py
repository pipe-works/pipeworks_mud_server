"""User account repository operations for the SQLite backend.

This module isolates account and guest-lifecycle persistence logic from the
monolithic compatibility facade in ``database.py``.
"""

from __future__ import annotations

import sqlite3


def _get_connection() -> sqlite3.Connection:
    """Return a DB connection via the compatibility facade.

    Using the facade preserves existing test patch points that monkeypatch
    ``mud_server.db.database.get_connection`` while we incrementally split the
    DB layer into dedicated modules.
    """
    from mud_server.db import database

    return database.get_connection()


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
        conn = _get_connection()
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


def user_exists(username: str) -> bool:
    """Return ``True`` when a user account exists."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_user_id(username: str) -> int | None:
    """Return user id for ``username`` or ``None`` if missing."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else None


def get_username_by_id(user_id: int) -> str | None:
    """Return username for ``user_id`` or ``None`` if missing."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_user_role(username: str) -> str | None:
    """Return role for ``username`` or ``None`` if missing."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_user_account_origin(username: str) -> str | None:
    """Return account origin label for ``username``."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT account_origin FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def set_user_role(username: str, role: str) -> bool:
    """Update user role.

    Returns:
        ``True`` on successful SQL update, otherwise ``False``.
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def verify_password_for_user(username: str, password: str) -> bool:
    """Verify password against bcrypt hash.

    Uses a dummy hash when user lookup fails to preserve timing behavior.
    """
    from mud_server.api.password import verify_password

    dummy_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G5j1L3tDPZ3q4q"  # nosec B105

    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        verify_password(password, dummy_hash)
        return False

    return verify_password(password, row[0])


def is_user_active(username: str) -> bool:
    """Return ``True`` when the account is active."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False


def deactivate_user(username: str) -> bool:
    """Deactivate user account."""
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0 WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def activate_user(username: str) -> bool:
    """Activate user account."""
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 1 WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def change_password_for_user(username: str, new_password: str) -> bool:
    """Change user password using bcrypt hash."""
    from mud_server.api.password import hash_password

    try:
        conn = _get_connection()
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
    """Soft-delete account row by marking tombstone fields."""
    conn = _get_connection()
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
    """Soft-delete user after detaching characters and removing sessions."""
    try:
        user_id = get_user_id(username)
        if not user_id:
            return False

        conn = _get_connection()
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


def unlink_characters_for_user(user_id: int) -> None:
    """Detach all characters from a user id."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE characters SET user_id = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def cleanup_expired_guest_accounts() -> int:
    """Delete expired guest accounts and detach their character ownership.

    Returns:
        Number of user rows removed.
    """
    conn = _get_connection()
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
