"""
Unit tests for permissions module (mud_server/api/permissions.py).

Tests cover:
- Permission checking for different roles
- Role hierarchy levels
- Role management capabilities
- Permission decorators

All tests are pure unit tests with no external dependencies.
"""

import pytest

from mud_server.api.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    can_manage_role,
    get_role_hierarchy_level,
    has_permission,
)

# ============================================================================
# ROLE ENUM TESTS
# ============================================================================


@pytest.mark.unit
def test_role_enum_values():
    """Test Role enum has expected values."""
    assert Role.PLAYER.value == "player"
    assert Role.WORLDBUILDER.value == "worldbuilder"
    assert Role.ADMIN.value == "admin"
    assert Role.SUPERUSER.value == "superuser"


# ============================================================================
# PERMISSION ENUM TESTS
# ============================================================================


@pytest.mark.unit
def test_permission_enum_values():
    """Test Permission enum has expected values."""
    assert Permission.PLAY_GAME.value == "play_game"
    assert Permission.CHAT.value == "chat"
    assert Permission.MANAGE_USERS.value == "manage_users"
    assert Permission.FULL_ACCESS.value == "full_access"


# ============================================================================
# HAS_PERMISSION TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_player_has_play_game_permission():
    """Test that player role has PLAY_GAME permission."""
    assert has_permission("player", Permission.PLAY_GAME) is True


@pytest.mark.unit
@pytest.mark.auth
def test_player_has_chat_permission():
    """Test that player role has CHAT permission."""
    assert has_permission("player", Permission.CHAT) is True


@pytest.mark.unit
@pytest.mark.auth
def test_player_lacks_manage_users_permission():
    """Test that player role lacks MANAGE_USERS permission."""
    assert has_permission("player", Permission.MANAGE_USERS) is False


@pytest.mark.unit
@pytest.mark.auth
def test_worldbuilder_has_create_rooms_permission():
    """Test that worldbuilder role has CREATE_ROOMS permission."""
    assert has_permission("worldbuilder", Permission.CREATE_ROOMS) is True


@pytest.mark.unit
@pytest.mark.auth
def test_worldbuilder_lacks_admin_permissions():
    """Test that worldbuilder role lacks admin permissions."""
    assert has_permission("worldbuilder", Permission.MANAGE_USERS) is False
    assert has_permission("worldbuilder", Permission.BAN_USERS) is False


@pytest.mark.unit
@pytest.mark.auth
def test_admin_has_view_logs_permission():
    """Test that admin role has VIEW_LOGS permission."""
    assert has_permission("admin", Permission.VIEW_LOGS) is True


@pytest.mark.unit
@pytest.mark.auth
def test_admin_has_ban_users_permission():
    """Test that admin role has BAN_USERS permission."""
    assert has_permission("admin", Permission.BAN_USERS) is True


@pytest.mark.unit
@pytest.mark.auth
def test_admin_lacks_manage_users_permission():
    """Test that admin role lacks MANAGE_USERS permission (superuser only)."""
    assert has_permission("admin", Permission.MANAGE_USERS) is False


@pytest.mark.unit
@pytest.mark.auth
def test_superuser_has_all_permissions():
    """Test that superuser role has all permissions."""
    # Superuser should have FULL_ACCESS which grants all permissions
    assert has_permission("superuser", Permission.PLAY_GAME) is True
    assert has_permission("superuser", Permission.MANAGE_USERS) is True
    assert has_permission("superuser", Permission.BAN_USERS) is True
    assert has_permission("superuser", Permission.VIEW_LOGS) is True
    assert has_permission("superuser", Permission.CREATE_ROOMS) is True
    assert has_permission("superuser", Permission.FULL_ACCESS) is True


@pytest.mark.unit
@pytest.mark.auth
def test_has_permission_case_insensitive():
    """Test that has_permission handles case-insensitive role strings."""
    assert has_permission("PLAYER", Permission.PLAY_GAME) is True
    assert has_permission("Player", Permission.PLAY_GAME) is True
    assert has_permission("player", Permission.PLAY_GAME) is True


@pytest.mark.unit
@pytest.mark.auth
def test_has_permission_invalid_role():
    """Test that invalid role returns False."""
    assert has_permission("invalid_role", Permission.PLAY_GAME) is False


# ============================================================================
# ROLE_PERMISSIONS MAPPING TESTS
# ============================================================================


@pytest.mark.unit
def test_role_permissions_mapping_complete():
    """Test that all roles have permission mappings."""
    assert Role.PLAYER in ROLE_PERMISSIONS
    assert Role.WORLDBUILDER in ROLE_PERMISSIONS
    assert Role.ADMIN in ROLE_PERMISSIONS
    assert Role.SUPERUSER in ROLE_PERMISSIONS


@pytest.mark.unit
def test_player_permissions_set():
    """Test player permission set is correct."""
    player_perms = ROLE_PERMISSIONS[Role.PLAYER]
    assert Permission.PLAY_GAME in player_perms
    assert Permission.CHAT in player_perms
    assert len(player_perms) == 2


@pytest.mark.unit
def test_worldbuilder_permissions_set():
    """Test worldbuilder permission set includes building permissions."""
    wb_perms = ROLE_PERMISSIONS[Role.WORLDBUILDER]
    assert Permission.PLAY_GAME in wb_perms
    assert Permission.CHAT in wb_perms
    assert Permission.CREATE_ROOMS in wb_perms
    assert Permission.CREATE_ITEMS in wb_perms
    assert Permission.EDIT_WORLD in wb_perms


@pytest.mark.unit
def test_admin_permissions_set():
    """Test admin permission set includes admin permissions."""
    admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
    assert Permission.PLAY_GAME in admin_perms
    assert Permission.CHAT in admin_perms
    assert Permission.BAN_USERS in admin_perms
    assert Permission.VIEW_LOGS in admin_perms
    assert Permission.STOP_SERVER in admin_perms


@pytest.mark.unit
def test_superuser_permissions_set():
    """Test superuser has FULL_ACCESS permission."""
    su_perms = ROLE_PERMISSIONS[Role.SUPERUSER]
    assert Permission.FULL_ACCESS in su_perms


# ============================================================================
# ROLE HIERARCHY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_get_role_hierarchy_level_player():
    """Test player hierarchy level is 0."""
    assert get_role_hierarchy_level("player") == 0


@pytest.mark.unit
@pytest.mark.auth
def test_get_role_hierarchy_level_worldbuilder():
    """Test worldbuilder hierarchy level is 1."""
    assert get_role_hierarchy_level("worldbuilder") == 1


@pytest.mark.unit
@pytest.mark.auth
def test_get_role_hierarchy_level_admin():
    """Test admin hierarchy level is 2."""
    assert get_role_hierarchy_level("admin") == 2


@pytest.mark.unit
@pytest.mark.auth
def test_get_role_hierarchy_level_superuser():
    """Test superuser hierarchy level is 3."""
    assert get_role_hierarchy_level("superuser") == 3


@pytest.mark.unit
@pytest.mark.auth
def test_get_role_hierarchy_level_case_insensitive():
    """Test hierarchy level lookup is case-insensitive."""
    assert get_role_hierarchy_level("ADMIN") == 2
    assert get_role_hierarchy_level("Admin") == 2


@pytest.mark.unit
@pytest.mark.auth
def test_get_role_hierarchy_level_invalid():
    """Test invalid role returns 0."""
    assert get_role_hierarchy_level("invalid") == 0


# ============================================================================
# CAN_MANAGE_ROLE TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_superuser_can_manage_all():
    """Test superuser can manage all lower roles."""
    assert can_manage_role("superuser", "admin") is True
    assert can_manage_role("superuser", "worldbuilder") is True
    assert can_manage_role("superuser", "player") is True


@pytest.mark.unit
@pytest.mark.auth
def test_admin_can_manage_lower_roles():
    """Test admin can manage worldbuilder and player."""
    assert can_manage_role("admin", "worldbuilder") is True
    assert can_manage_role("admin", "player") is True


@pytest.mark.unit
@pytest.mark.auth
def test_admin_cannot_manage_admin():
    """Test admin cannot manage other admins."""
    assert can_manage_role("admin", "admin") is False


@pytest.mark.unit
@pytest.mark.auth
def test_admin_cannot_manage_superuser():
    """Test admin cannot manage superuser."""
    assert can_manage_role("admin", "superuser") is False


@pytest.mark.unit
@pytest.mark.auth
def test_worldbuilder_can_manage_player():
    """Test worldbuilder can manage player."""
    assert can_manage_role("worldbuilder", "player") is True


@pytest.mark.unit
@pytest.mark.auth
def test_worldbuilder_cannot_manage_worldbuilder():
    """Test worldbuilder cannot manage other worldbuilders."""
    assert can_manage_role("worldbuilder", "worldbuilder") is False


@pytest.mark.unit
@pytest.mark.auth
def test_worldbuilder_cannot_manage_higher_roles():
    """Test worldbuilder cannot manage admin or superuser."""
    assert can_manage_role("worldbuilder", "admin") is False
    assert can_manage_role("worldbuilder", "superuser") is False


@pytest.mark.unit
@pytest.mark.auth
def test_player_cannot_manage_anyone():
    """Test player cannot manage any roles."""
    assert can_manage_role("player", "player") is False
    assert can_manage_role("player", "worldbuilder") is False
    assert can_manage_role("player", "admin") is False
    assert can_manage_role("player", "superuser") is False


@pytest.mark.unit
@pytest.mark.auth
def test_cannot_manage_same_level():
    """Test that users cannot manage users at the same hierarchy level."""
    assert can_manage_role("player", "player") is False
    assert can_manage_role("admin", "admin") is False
    assert can_manage_role("superuser", "superuser") is False


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.auth
def test_has_permission_with_none_role():
    """Test has_permission handles None role gracefully."""
    # Should not raise exception, just return False
    try:
        result = has_permission(None, Permission.PLAY_GAME)
        # If it doesn't raise, it should return False
        assert result is False
    except (AttributeError, ValueError, TypeError):
        # These are acceptable exception types for None input
        pass


@pytest.mark.unit
@pytest.mark.auth
def test_role_hierarchy_preserves_order():
    """Test that role hierarchy levels are in ascending order of privilege."""
    player_level = get_role_hierarchy_level("player")
    wb_level = get_role_hierarchy_level("worldbuilder")
    admin_level = get_role_hierarchy_level("admin")
    su_level = get_role_hierarchy_level("superuser")

    assert player_level < wb_level < admin_level < su_level
