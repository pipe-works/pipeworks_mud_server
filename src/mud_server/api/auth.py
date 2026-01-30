"""
Session management and authentication.

This module handles session-based authentication for the MUD server. It provides:
1. In-memory session storage mapping session IDs to (username, role) tuples
2. Session validation functions that verify session IDs and check permissions
3. Integration with the database for session activity tracking

Session Lifecycle:
1. Login: New UUID session ID created, stored in both memory and database
2. Requests: Each API call validates session and updates activity timestamp
3. Logout: Session removed from both memory and database
4. Server Restart: All sessions lost (memory-based, not persisted)

Security Considerations:
- Sessions use UUIDs (hard to guess, 128-bit random)
- No session expiration time (TODO: implement timeout)
- Sessions stored in memory (lost on restart)
- Database also tracks sessions but memory is source of truth
- Session validation updates activity timestamp to track last action

Future Improvements:
- Add session expiration (timeout after inactivity)
- Persist sessions across server restarts
- Add session refresh/renewal mechanism
- Implement "remember me" functionality
"""

from fastapi import HTTPException

from mud_server.api.permissions import Permission, has_permission
from mud_server.db import database

# ============================================================================
# SESSION STORAGE
# ============================================================================

# In-memory dictionary storing active sessions
# Key: session_id (UUID string)
# Value: (username, role) tuple
#
# This is the authoritative source for active sessions. The database also
# stores sessions, but this in-memory dict is used for fast lookups.
#
# IMPORTANT: All sessions are lost when the server restarts since this is
# not persisted to disk. Users will need to log in again after a restart.
active_sessions: dict[str, tuple[str, str]] = {}


# ============================================================================
# SESSION LIFECYCLE MANAGEMENT
# ============================================================================


def clear_all_sessions() -> int:
    """
    Clear all sessions from both memory and database.

    This is the primary function for complete session cleanup. It handles
    both the in-memory active_sessions dictionary AND the database sessions
    table, ensuring consistency between the two storage layers.

    This should be called:
        1. On server startup (via lifespan context manager in server.py)
        2. When performing emergency session resets
        3. In test fixtures to ensure clean state

    The function first clears the in-memory dict (which is authoritative for
    fast lookups during request handling), then clears the database table
    (which provides persistence and audit trail).

    Returns:
        Number of sessions removed from the database. Note that the in-memory
        count may differ if sessions were inconsistent between memory and DB.

    Side Effects:
        - Clears active_sessions dict (immediate effect)
        - Deletes all rows from sessions table (committed to database)

    Thread Safety:
        This function modifies global state (active_sessions dict). In a
        multi-threaded environment, consider adding locking if concurrent
        access is expected.

    Example:
        >>> # On server startup
        >>> from mud_server.api.auth import clear_all_sessions
        >>> removed = clear_all_sessions()
        >>> print(f"Cleared {removed} orphaned session(s)")
    """
    # Clear memory sessions first - this is the authoritative source
    # for active session lookups during API request handling
    active_sessions.clear()

    # Clear database sessions and return the count
    # This ensures the persistent storage matches in-memory state
    return database.clear_all_sessions()


def remove_session(session_id: str) -> bool:
    """
    Remove a specific session from both memory and database.

    This function handles targeted session removal, typically used when:
        1. A user explicitly logs out (via logout endpoint)
        2. An admin force-disconnects a user
        3. A session is detected as invalid and needs cleanup

    The function first removes from in-memory storage (which is checked
    during request validation), then removes from database (which provides
    the persistent record). The session is identified by session_id in
    memory but by username in the database (since username is unique
    in the sessions table).

    Args:
        session_id: The UUID session identifier to remove. This is the
            key used in the active_sessions dict.

    Returns:
        True if the session was found in memory and removed from both
        memory and database. False if the session_id was not found in
        the active_sessions dict (in which case no database operation
        is performed).

    Side Effects:
        - Removes entry from active_sessions dict
        - Deletes row from sessions table (if session existed)

    Note:
        If a session exists in the database but not in memory (e.g., after
        a server restart), this function will return False. Use
        database.remove_session(username) directly for database-only cleanup.

    Example:
        >>> # User logs out
        >>> from mud_server.api.auth import remove_session
        >>> if remove_session(request.session_id):
        ...     return {"message": "Logged out successfully"}
    """
    # Pop from memory - returns None if not found
    # This atomically removes and returns the value
    session_data = active_sessions.pop(session_id, None)

    if session_data:
        # Session existed in memory - extract username and remove from DB
        # session_data is a (username, role) tuple
        username = session_data[0]
        database.remove_session(username)
        return True

    # Session not found in memory
    return False


def get_active_session_count() -> int:
    """
    Get the count of active sessions currently in memory.

    This provides a quick way to check how many users are logged in without
    querying the database. Since the in-memory active_sessions dict is the
    authoritative source for session validation, this count reflects the
    actual number of valid sessions.

    This is useful for:
        1. Health check endpoints (reporting active_players)
        2. Admin dashboards showing current load
        3. Rate limiting decisions based on server load
        4. Logging and monitoring

    Returns:
        Number of active sessions in the in-memory dict. This represents
        the count of currently authenticated users.

    Note:
        This counts sessions in memory only. If you need the database
        count (which may differ after server restart), query the
        sessions table directly.

    Example:
        >>> from mud_server.api.auth import get_active_session_count
        >>> print(f"Active players: {get_active_session_count()}")
        Active players: 42
    """
    return len(active_sessions)


# ============================================================================
# SESSION LOOKUP FUNCTIONS
# ============================================================================


def get_username_from_session(session_id: str) -> str | None:
    """
    Get username from session ID (backward compatibility function).

    This function returns only the username for code that doesn't need
    the role information. New code should use get_username_and_role_from_session()
    or validate_session() instead.

    Args:
        session_id: UUID session identifier from login response

    Returns:
        Username if session exists, None if session not found

    Example:
        >>> get_username_from_session("550e8400-e29b-41d4-a716-446655440000")
        'player1'
        >>> get_username_from_session("invalid")
        None
    """
    session_data = active_sessions.get(session_id)
    if session_data:
        return session_data[0]  # Return username from (username, role) tuple
    return None


def get_username_and_role_from_session(session_id: str) -> tuple[str, str] | None:
    """
    Get both username and role from session ID.

    Args:
        session_id: UUID session identifier from login response

    Returns:
        (username, role) tuple if session exists, None if not found

    Example:
        >>> get_username_and_role_from_session("550e8400-e29b-41d4-a716-446655440000")
        ('player1', 'player')
        >>> get_username_and_role_from_session("invalid")
        None
    """
    return active_sessions.get(session_id)


# ============================================================================
# SESSION VALIDATION FUNCTIONS
# ============================================================================


def validate_session(session_id: str) -> tuple[str, str]:
    """
    Validate session and return user information.

    This is the primary function used by API endpoints to authenticate
    requests. It verifies the session exists and updates the activity
    timestamp in the database.

    Args:
        session_id: UUID session identifier to validate

    Returns:
        (username, role) tuple for the authenticated user

    Raises:
        HTTPException(401): If session_id is invalid, expired, or not found

    Side Effects:
        Updates the last_activity timestamp in the database sessions table

    Usage:
        Called at the beginning of every protected API endpoint to ensure
        the request is from a logged-in user.

    Example:
        @app.post("/command")
        async def execute_command(request: CommandRequest):
            username, role = validate_session(request.session_id)
            # Now we know the user is authenticated
            ...
    """
    # Look up session in memory
    session_data = get_username_and_role_from_session(session_id)
    if not session_data:
        # Session not found - either never existed, expired, or user logged out
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    username, role = session_data

    # Update the last activity timestamp in database to track when user was last active
    # This helps identify stale sessions and provides audit trail
    database.update_session_activity(username)

    return username, role


def validate_session_with_permission(session_id: str, permission: Permission) -> tuple[str, str]:
    """
    Validate session and check if user has required permission.

    This function combines session validation with permission checking,
    ensuring the user is both logged in AND has the necessary permission
    for the requested action. Used for admin endpoints and restricted features.

    Args:
        session_id: UUID session identifier to validate
        permission: Required permission (e.g., Permission.VIEW_LOGS, Permission.MANAGE_USERS)

    Returns:
        (username, role) tuple if session valid and permission granted

    Raises:
        HTTPException(401): If session is invalid or expired
        HTTPException(403): If session valid but user lacks required permission

    Permission Hierarchy:
        - Player: Basic gameplay permissions
        - WorldBuilder: Player permissions + world editing
        - Admin: WorldBuilder permissions + user management, logs, server control
        - Superuser: All permissions

    Example:
        @app.post("/admin/user/manage")
        async def manage_user(request: UserManagementRequest):
            username, role = validate_session_with_permission(
                request.session_id, Permission.MANAGE_USERS
            )
            # User is authenticated AND has MANAGE_USERS permission
            ...
    """
    # First validate the session (raises 401 if invalid)
    username, role = validate_session(session_id)

    # Then check if the user's role has the required permission
    if not has_permission(role, permission):
        # User is logged in but doesn't have permission for this action
        raise HTTPException(
            status_code=403,  # 403 Forbidden (authenticated but not authorized)
            detail=f"Insufficient permissions. Required: {permission.value}",
        )

    return username, role
