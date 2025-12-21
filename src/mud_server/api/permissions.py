"""
Role-based permission system (RBAC).

This module implements a Role-Based Access Control (RBAC) system for the MUD
server. It defines:
1. User roles with different privilege levels
2. Specific permissions that can be checked
3. Mapping of which roles have which permissions
4. Helper functions to check permissions and role hierarchy

Role Hierarchy (lowest to highest):
    Player → World Builder → Admin → Superuser

Permission Design:
- Each role has an explicit set of permissions
- Roles DO NOT automatically inherit lower role permissions (must be explicit)
- Superuser has a special FULL_ACCESS permission that grants everything
- Permissions are granular to allow fine-grained access control

Usage in API Routes:
1. Use validate_session_with_permission() to check specific permissions
2. Use require_permission() decorator for route-level protection
3. Use require_role() decorator for minimum role requirements
4. Use can_manage_role() to prevent privilege escalation

Security Considerations:
- Never allow users to elevate their own privileges
- Always check role hierarchy for user management operations
- Superusers can manage everyone, admins can manage lower roles
- Players and World Builders cannot manage other users
"""

from enum import Enum
from functools import wraps

from fastapi import HTTPException

# ============================================================================
# ROLE DEFINITIONS
# ============================================================================


class Role(Enum):
    """
    User roles in the system, ordered by privilege level.

    Each role represents a different level of access and trust in the system.
    Roles are stored as lowercase strings in the database but represented as
    enum values in code for type safety.

    Roles (in order of privilege):
        PLAYER: Standard game player (lowest privilege)
        WORLDBUILDER: Player with world editing capabilities
        ADMIN: Administrator with user management powers
        SUPERUSER: Super administrator with full system access (highest privilege)
    """

    PLAYER = "player"
    WORLDBUILDER = "worldbuilder"
    ADMIN = "admin"
    SUPERUSER = "superuser"


# ============================================================================
# PERMISSION DEFINITIONS
# ============================================================================


class Permission(Enum):
    """
    Specific permissions that can be granted to roles.

    Permissions are organized by category and represent specific actions
    that users can perform. Each permission should be as granular as possible
    to allow fine-grained access control.

    Permission Categories:
        - Player: Basic gameplay actions
        - World Builder: Content creation and editing
        - Admin: User management and system administration
        - Superuser: Full unrestricted access
    """

    # ========================================================================
    # PLAYER PERMISSIONS
    # Basic gameplay permissions available to all users
    # ========================================================================
    PLAY_GAME = "play_game"  # Can play the game (move, inventory, etc.)
    CHAT = "chat"  # Can send chat messages, whispers, yells

    # ========================================================================
    # WORLDBUILDER PERMISSIONS
    # Content creation and world editing (future features)
    # ========================================================================
    EDIT_WORLD = "edit_world"  # Can edit existing world content
    CREATE_ROOMS = "create_rooms"  # Can create new rooms
    CREATE_ITEMS = "create_items"  # Can create new items

    # ========================================================================
    # ADMIN PERMISSIONS
    # User management and server administration
    # ========================================================================
    KICK_USERS = "kick_users"  # Can kick users from the server (future)
    BAN_USERS = "ban_users"  # Can ban/unban user accounts
    VIEW_LOGS = "view_logs"  # Can view system logs and player activity
    STOP_SERVER = "stop_server"  # Can shutdown the server

    # ========================================================================
    # SUPERUSER PERMISSIONS
    # Highest level permissions for full system access
    # ========================================================================
    MANAGE_USERS = "manage_users"  # Can change user roles and permissions
    CHANGE_ROLES = "change_roles"  # Can promote/demote users
    FULL_ACCESS = "full_access"  # Has all permissions (superuser only)


# ============================================================================
# ROLE-PERMISSION MAPPING
# ============================================================================

# Maps each role to the set of permissions it has
# NOTE: Permissions are NOT inherited - each role's permissions must be
# explicitly listed. This makes the permission system clear and prevents
# accidental permission grants.
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    # PLAYER: Basic game access
    # Can play the game and chat with other players
    Role.PLAYER: {
        Permission.PLAY_GAME,
        Permission.CHAT,
    },
    # WORLDBUILDER: Player permissions + content creation
    # Can play the game AND create/edit world content
    # Note: Must explicitly include PLAY_GAME and CHAT (no inheritance)
    Role.WORLDBUILDER: {
        Permission.PLAY_GAME,
        Permission.CHAT,
        Permission.EDIT_WORLD,
        Permission.CREATE_ROOMS,
        Permission.CREATE_ITEMS,
    },
    # ADMIN: Player permissions + user management + server control
    # Can play, manage users, view logs, and control server
    # Note: Does not inherit WorldBuilder permissions (cannot create content)
    Role.ADMIN: {
        Permission.PLAY_GAME,
        Permission.CHAT,
        Permission.KICK_USERS,
        Permission.BAN_USERS,
        Permission.VIEW_LOGS,
        Permission.EDIT_WORLD,  # Admins can edit but not create
        Permission.STOP_SERVER,
    },
    # SUPERUSER: Full unrestricted access
    # The FULL_ACCESS permission is checked specially - grants all permissions
    Role.SUPERUSER: {
        Permission.FULL_ACCESS,  # Superuser has all permissions
    },
}


# ============================================================================
# PERMISSION CHECKING FUNCTIONS
# ============================================================================


def has_permission(role: str, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.

    This is the core permission checking function used throughout the application.
    It converts the role string to an enum, looks up the role's permissions,
    and checks if the requested permission is granted.

    Special Case:
        Superusers automatically have ALL permissions due to the FULL_ACCESS
        permission. This is checked first before looking up specific permissions.

    Args:
        role: Role string (case-insensitive: "player", "worldbuilder", "admin", "superuser")
        permission: Permission enum value to check (e.g., Permission.MANAGE_USERS)

    Returns:
        True if the role has the permission, False if not or if role is invalid

    Example:
        >>> has_permission("admin", Permission.VIEW_LOGS)
        True
        >>> has_permission("player", Permission.MANAGE_USERS)
        False
        >>> has_permission("superuser", Permission.ANYTHING)
        True  # Superuser has all permissions
    """
    # Try to convert role string to enum
    try:
        role_enum = Role(role.lower())
    except ValueError:
        # Invalid role string - deny permission
        return False

    # Special case: Superuser has all permissions
    if role_enum == Role.SUPERUSER:
        return True

    # Look up the role's permission set
    permissions = ROLE_PERMISSIONS.get(role_enum, set())

    # Check if the requested permission is in the set
    return permission in permissions


# ============================================================================
# ROLE HIERARCHY FUNCTIONS
# ============================================================================


def get_role_hierarchy_level(role: str) -> int:
    """
    Get the numeric hierarchy level of a role.

    The hierarchy level is used to determine which users can manage other users.
    Higher numbers indicate more privilege. This prevents lower-privileged users
    from managing higher-privileged users.

    Hierarchy Levels:
        0 = Player (lowest privilege)
        1 = World Builder
        2 = Admin
        3 = Superuser (highest privilege)

    Args:
        role: Role string (case-insensitive)

    Returns:
        Integer hierarchy level (0-3)
        Returns 0 for invalid/unknown roles (treated as lowest privilege)

    Example:
        >>> get_role_hierarchy_level("admin")
        2
        >>> get_role_hierarchy_level("player")
        0
        >>> get_role_hierarchy_level("invalid")
        0
    """
    hierarchy = {
        "player": 0,
        "worldbuilder": 1,
        "admin": 2,
        "superuser": 3,
    }
    return hierarchy.get(role.lower(), 0)


def can_manage_role(manager_role: str, target_role: str) -> bool:
    """
    Check if a manager can manage (promote/demote/ban) a target user.

    This function enforces the rule that you can only manage users with
    a lower hierarchy level than yourself. This prevents privilege escalation
    and ensures proper administrative boundaries.

    Management Rules:
        - Superuser (3) can manage Admin (2), WorldBuilder (1), Player (0)
        - Admin (2) can manage WorldBuilder (1), Player (0)
        - WorldBuilder (1) can manage Player (0)
        - Player (0) cannot manage anyone
        - You CANNOT manage users at the same level or higher

    Args:
        manager_role: Role of the user performing the management action
        target_role: Role of the user being managed

    Returns:
        True if manager can manage target, False otherwise

    Security Note:
        Always call this function before allowing role changes, bans, or
        other user management actions to prevent privilege escalation attacks.

    Example:
        >>> can_manage_role("admin", "player")
        True
        >>> can_manage_role("player", "admin")
        False
        >>> can_manage_role("admin", "admin")
        False  # Cannot manage users at same level
        >>> can_manage_role("superuser", "admin")
        True
    """
    return get_role_hierarchy_level(manager_role) > get_role_hierarchy_level(target_role)


# ============================================================================
# ROUTE DECORATOR FUNCTIONS
# ============================================================================


def require_permission(permission: Permission):
    """
    Decorator to require a specific permission for a route.

    This decorator wraps a route function and checks if the user has the
    required permission before allowing the function to execute. If the
    user lacks the permission, an HTTP 403 Forbidden error is raised.

    Note:
        This decorator is currently defined but not actively used in the codebase.
        Most routes use validate_session_with_permission() directly instead.
        This decorator could be useful for cleaner route definitions in the future.

    Args:
        permission: The permission required to access the route

    Returns:
        Decorator function that wraps the route handler

    Raises:
        HTTPException(403): If user lacks the required permission

    Usage:
        @app.post("/admin/action")
        @require_permission(Permission.MANAGE_USERS)
        async def admin_action(username: str, role: str):
            # This only executes if user has MANAGE_USERS permission
            ...

    Requirements:
        The wrapped function must have "role" in its kwargs, typically obtained
        from validate_session() before calling the route handler.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract role from function arguments (should be in kwargs)
            role = kwargs.get("role")

            # Check if role exists and has required permission
            if not role or not has_permission(role, permission):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required: {permission.value}",
                )

            # Permission granted - execute the route handler
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_role(min_role: Role):
    """
    Decorator to require a minimum role level for a route.

    This decorator checks role hierarchy level rather than specific permissions.
    It ensures the user has at least the specified role level (or higher) before
    allowing access to the route.

    Note:
        This decorator is currently defined but not actively used in the codebase.
        Most routes use validate_session_with_permission() for permission-based
        checks instead of role-based checks. However, this could be useful for
        routes that need role-level restrictions regardless of specific permissions.

    Args:
        min_role: Minimum role enum value required (e.g., Role.ADMIN)

    Returns:
        Decorator function that wraps the route handler

    Raises:
        HTTPException(403): If user's role is below the minimum required level

    Usage:
        @app.post("/admin/dashboard")
        @require_role(Role.ADMIN)
        async def admin_dashboard(username: str, role: str):
            # This only executes if user is Admin or Superuser
            ...

    Requirements:
        The wrapped function must have "role" in its kwargs, typically obtained
        from validate_session() before calling the route handler.

    Example:
        If min_role=Role.ADMIN:
        - Superuser (level 3) ✓ Allowed (3 >= 2)
        - Admin (level 2) ✓ Allowed (2 >= 2)
        - WorldBuilder (level 1) ✗ Denied (1 < 2)
        - Player (level 0) ✗ Denied (0 < 2)
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract role from function arguments
            role = kwargs.get("role")

            # Ensure role exists in kwargs
            if not role:
                raise HTTPException(status_code=403, detail="Role not found in session")

            # Compare hierarchy levels
            if get_role_hierarchy_level(role) < get_role_hierarchy_level(min_role.value):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient privileges. Minimum role required: {min_role.value}",
                )

            # Role level sufficient - execute the route handler
            return await func(*args, **kwargs)

        return wrapper

    return decorator
