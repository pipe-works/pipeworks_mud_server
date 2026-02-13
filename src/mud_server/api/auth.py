"""
Session management and authentication.

This module handles session-based authentication for the MUD server. It provides:
1. Database-backed session storage (source of truth)
2. Session validation with expiration enforcement
3. Permission checks for admin endpoints

Session Lifecycle:
1. Login: New session ID created and stored in the database
2. Requests: Each API call validates session, enforces expiry, updates activity
3. Logout: Session removed from the database
4. Server Restart: Sessions survive until they expire or are revoked

Security Considerations:
- Sessions use opaque IDs (UUIDs by default)
- Sessions expire using a TTL and (optionally) sliding expiration
- Database is the source of truth (supports restart persistence)
- Session validation updates activity timestamp to track last action

Future Improvements:
- Implement session refresh tokens ("remember me")
- Add device/session management UI
- Add optional IP/User-Agent tracking for session audits
"""

from datetime import UTC, datetime

from fastapi import HTTPException

from mud_server.api.permissions import Permission, has_permission
from mud_server.db import database

# ============================================================================
# SESSION LIFECYCLE MANAGEMENT
# ============================================================================


def clear_all_sessions() -> int:
    """
    Clear all sessions from the database.

    This should be called:
        1. When performing emergency session resets
        2. In test fixtures to ensure clean state

    Returns:
        Number of sessions removed from the database.

    Side Effects:
        - Deletes all rows from sessions table (committed to database)
    """
    return database.clear_all_sessions()


def remove_session(session_id: str) -> bool:
    """
    Remove a specific session from the database.

    This function handles targeted session removal, typically used when:
        1. A user explicitly logs out (via logout endpoint)
        2. An admin force-disconnects a user
        3. A session is detected as invalid and needs cleanup

    Args:
        session_id: The UUID session identifier to remove.

    Returns:
        True if the session was removed, False if it was not found.
    """
    return database.remove_session_by_id(session_id)


def get_active_session_count() -> int:
    """
    Get the count of active (non-expired) sessions.

    This is useful for:
        1. Health check endpoints (reporting active_players)
        2. Admin dashboards showing current load
        3. Rate limiting decisions based on server load
        4. Logging and monitoring
    """
    return database.get_active_session_count()


# ============================================================================
# SESSION LOOKUP FUNCTIONS
# ============================================================================


def get_username_from_session(session_id: str) -> str | None:
    """
    Get username from session ID.

    Returns None if the session is not found or has expired.
    """
    session = _get_valid_session(session_id)
    if not session:
        return None
    return database.get_username_by_id(int(session["user_id"]))


def get_username_and_role_from_session(session_id: str) -> tuple[str, str] | None:
    """
    Get both username and role from session ID.

    Returns None if the session is not found or has expired.
    """
    session = _get_valid_session(session_id)
    if not session:
        return None

    user_id = int(session["user_id"])
    username = database.get_username_by_id(user_id)
    if not username:
        return None

    role = database.get_user_role(username)
    if not role:
        return None

    return username, role


# ============================================================================
# SESSION VALIDATION FUNCTIONS
# ============================================================================


def validate_session(session_id: str) -> tuple[int, str, str]:
    """
    Validate session and return user information.

    Returns:
        (user_id, username, role)

    Raises:
        HTTPException(401): If session_id is invalid or expired
    """
    session = _get_valid_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    database.update_session_activity(session_id)

    user_id = int(session["user_id"])
    username = database.get_username_by_id(user_id)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid session user")

    role = database.get_user_role(username)
    if not role:
        raise HTTPException(status_code=401, detail="Invalid session user")

    return user_id, username, role


def validate_session_for_game(session_id: str) -> tuple[int, str, str, int, str, str]:
    """
    Validate session and ensure a character is selected for gameplay.

    Returns:
        (user_id, username, role, character_id, character_name, world_id)

    Raises:
        HTTPException(401): If session_id is invalid or expired
        HTTPException(409): If no character is selected for this session
    """
    session = _get_valid_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    database.update_session_activity(session_id)

    user_id = int(session["user_id"])
    username = database.get_username_by_id(user_id)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid session user")

    role = database.get_user_role(username)
    if not role:
        raise HTTPException(status_code=401, detail="Invalid session user")

    character_id = session.get("character_id")
    if not character_id:
        characters = database.get_user_characters(user_id)
        if len(characters) == 1:
            character_id = characters[0]["id"]
            database.set_session_character(session_id, int(character_id))
        else:
            raise HTTPException(status_code=409, detail="No character selected for session")

    character_name = database.get_character_name_by_id(int(character_id))
    if not character_name:
        raise HTTPException(status_code=409, detail="Selected character not found")

    character = database.get_character_by_id(int(character_id))
    if not character or not character.get("world_id"):
        raise HTTPException(status_code=409, detail="Character world not found")

    world_id = character["world_id"]
    if session.get("world_id") != world_id:
        database.set_session_character(session_id, int(character_id), world_id=world_id)

    return user_id, username, role, int(character_id), character_name, world_id


def validate_session_with_permission(
    session_id: str, permission: Permission
) -> tuple[int, str, str]:
    """
    Validate session and check if user has required permission.

    Raises:
        HTTPException(401): If session is invalid or expired
        HTTPException(403): If session valid but user lacks required permission
    """
    # First validate the session (raises 401 if invalid)
    user_id, username, role = validate_session(session_id)

    # Then check if the user's role has the required permission
    if not has_permission(role, permission):
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions. Required: {permission.value}",
        )

    return user_id, username, role


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _get_valid_session(session_id: str) -> dict | None:
    """
    Return session record if valid and not expired.

    If the session is expired, it is removed from the database so it cannot
    be reused.
    """
    session = database.get_session_by_id(session_id)
    if not session:
        return None

    expires_at = session.get("expires_at")
    if expires_at and _is_expired(expires_at):
        database.remove_session_by_id(session_id)
        return None

    return session


def _is_expired(expires_at: str) -> bool:
    """
    Check if a stored SQLite timestamp is expired relative to current UTC time.

    SQLite CURRENT_TIMESTAMP format is "YYYY-MM-DD HH:MM:SS".
    """
    try:
        expires_dt = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # If parsing fails, treat as expired for safety.
        return True

    now = datetime.now(UTC).replace(tzinfo=None)
    return expires_dt <= now
