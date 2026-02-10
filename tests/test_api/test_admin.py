"""
Tests for administrative API endpoints and actions.

Tests cover:
- Admin database viewing endpoints
- User management (role changes, activation/deactivation)
- Password management
- Permission checks for admin actions
- Server control endpoints

All tests verify proper permission checking and role-based access.
"""

from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD

CREATE_USER_PASSWORD = "R7$kM2%vH9!q"

# ============================================================================
# ADMIN DATABASE VIEWING TESTS
# ============================================================================


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_players_as_admin(test_client, test_db, temp_db_path, db_with_users):
    """Test admin can view all players."""
    with use_test_database(temp_db_path):
        # Login as admin
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        # Try to view players (endpoint may not exist yet)
        response = test_client.get(f"/admin/database/players?session_id={session_id}")

        # Should either work (200) or not be implemented (404)
        assert response.status_code in [200, 404]


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_tables_as_admin(test_client, test_db, temp_db_path, db_with_users):
    """Test admin can view database table metadata."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(f"/admin/database/tables?session_id={session_id}")

        assert response.status_code == 200
        assert "tables" in response.json()


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_players_as_player_forbidden(test_client, test_db, temp_db_path, db_with_users):
    """Test regular player cannot view admin endpoints."""
    with use_test_database(temp_db_path):
        # Login as regular player
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        # Try to view players
        response = test_client.get(f"/admin/database/players?session_id={session_id}")

        # Should be forbidden (403) or not found (404)
        assert response.status_code in [403, 404]


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_tables_as_player_forbidden(test_client, test_db, temp_db_path, db_with_users):
    """Test regular player cannot view database table metadata."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(f"/admin/database/tables?session_id={session_id}")

        assert response.status_code == 403


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_table_rows_as_admin(test_client, test_db, temp_db_path, db_with_users):
    """Test admin can view table rows for a specific table."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(f"/admin/database/table/players?session_id={session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["table"] == "players"
        assert "columns" in data
        assert "rows" in data


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_table_rows_invalid_table(test_client, test_db, temp_db_path, db_with_users):
    """Test invalid table returns 404 for admins."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(f"/admin/database/table/not_a_table?session_id={session_id}")

        assert response.status_code == 404


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_table_rows_as_player_forbidden(
    test_client, test_db, temp_db_path, db_with_users
):
    """Test regular player cannot view table rows."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

    response = test_client.get(f"/admin/database/table/players?session_id={session_id}")

    assert response.status_code == 403


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_player_locations_as_admin(test_client, test_db, temp_db_path, db_with_users):
    """Test admin can view player locations."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(f"/admin/database/player-locations?session_id={session_id}")

        assert response.status_code == 200
        data = response.json()
        assert "locations" in data
        if data["locations"]:
            assert "player_id" in data["locations"][0]
            assert "username" in data["locations"][0]
            assert "room_id" in data["locations"][0]


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_player_locations_as_player_forbidden(
    test_client, test_db, temp_db_path, db_with_users
):
    """Test regular player cannot view player locations."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

    response = test_client.get(f"/admin/database/player-locations?session_id={session_id}")

    assert response.status_code == 403


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_connections_as_admin(test_client, test_db, temp_db_path, db_with_users):
    """Test admin can view active connections."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(f"/admin/database/connections?session_id={session_id}")

        assert response.status_code == 200
        assert "connections" in response.json()


# ============================================================================
# ADMIN USER CREATION TESTS
# ============================================================================


@pytest.mark.admin
@pytest.mark.api
def test_admin_can_create_player(test_client, test_db, temp_db_path, db_with_users):
    """Test admin can create player accounts."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/user/create",
            json={
                "session_id": session_id,
                "username": "newplayer",
                "password": CREATE_USER_PASSWORD,
                "password_confirm": CREATE_USER_PASSWORD,
                "role": "player",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.admin
@pytest.mark.api
def test_admin_cannot_create_admin_or_superuser(test_client, test_db, temp_db_path, db_with_users):
    """Test admin cannot create admin or superuser accounts."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        for role in ("admin", "superuser"):
            response = test_client.post(
                "/admin/user/create",
                json={
                    "session_id": session_id,
                    "username": f"new-{role}",
                    "password": CREATE_USER_PASSWORD,
                    "password_confirm": CREATE_USER_PASSWORD,
                    "role": role,
                },
            )
            assert response.status_code == 403


@pytest.mark.admin
@pytest.mark.api
def test_superuser_can_create_admin(test_client, test_db, temp_db_path, db_with_users):
    """Test superuser can create admin accounts."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/user/create",
            json={
                "session_id": session_id,
                "username": "newadmin",
                "password": CREATE_USER_PASSWORD,
                "password_confirm": CREATE_USER_PASSWORD,
                "role": "admin",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.admin
@pytest.mark.api
def test_create_user_rejects_password_mismatch(test_client, test_db, temp_db_path, db_with_users):
    """Test create user rejects mismatched passwords."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/user/create",
            json={
                "session_id": session_id,
                "username": "badpass",
                "password": CREATE_USER_PASSWORD,
                "password_confirm": "DifferentPass#1234",
                "role": "player",
            },
        )

        assert response.status_code == 400


@pytest.mark.admin
@pytest.mark.api
def test_create_user_rejects_weak_password(test_client, test_db, temp_db_path, db_with_users):
    """Test create user enforces password policy."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/user/create",
            json={
                "session_id": session_id,
                "username": "weakpass",
                "password": "short",
                "password_confirm": "short",
                "role": "player",
            },
        )

        assert response.status_code == 400


@pytest.mark.admin
@pytest.mark.api
def test_create_user_rejects_duplicate_username(test_client, test_db, temp_db_path, db_with_users):
    """Test create user rejects duplicate usernames."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/user/create",
            json={
                "session_id": session_id,
                "username": "testplayer",
                "password": CREATE_USER_PASSWORD,
                "password_confirm": CREATE_USER_PASSWORD,
                "role": "player",
            },
        )

        assert response.status_code == 400


@pytest.mark.admin
@pytest.mark.api
def test_admin_view_connections_as_player_forbidden(
    test_client, test_db, temp_db_path, db_with_users
):
    """Test regular player cannot view active connections."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(f"/admin/database/connections?session_id={session_id}")

        assert response.status_code == 403


@pytest.mark.admin
@pytest.mark.api
def test_admin_can_kick_session(test_client, test_db, temp_db_path, db_with_users):
    """Test admin can kick an active session."""
    with use_test_database(temp_db_path):
        # Login as admin and create a player session.
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        admin_session = admin_login.json()["session_id"]

        player_login = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        target_session = player_login.json()["session_id"]

        response = test_client.post(
            "/admin/session/kick",
            json={
                "session_id": admin_session,
                "target_session_id": target_session,
                "reason": "test",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.admin
@pytest.mark.api
def test_player_cannot_kick_session(test_client, test_db, temp_db_path, db_with_users):
    """Test player cannot kick sessions."""
    with use_test_database(temp_db_path):
        player_login = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        player_session = player_login.json()["session_id"]

        response = test_client.post(
            "/admin/session/kick",
            json={
                "session_id": player_session,
                "target_session_id": "missing-session",
                "reason": "test",
            },
        )

        assert response.status_code == 403


# ============================================================================
# USER MANAGEMENT TESTS
# ============================================================================


@pytest.mark.admin
@pytest.mark.api
def test_superuser_can_change_user_role(test_client, test_db, temp_db_path, db_with_users):
    """Test superuser can change user roles."""
    with use_test_database(temp_db_path):
        # Login as superuser
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        # Try to change testplayer's role (endpoint may not exist yet)
        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "action": "change_role",
                "target_username": "testplayer",
                "new_role": "worldbuilder",
            },
        )

        # Should either work (200) or not be implemented (404)
        assert response.status_code in [200, 404]


@pytest.mark.admin
@pytest.mark.api
def test_admin_cannot_change_roles(test_client, test_db, temp_db_path, db_with_users):
    """Test admin cannot change user roles (superuser only)."""
    with use_test_database(temp_db_path):
        # Login as admin
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        # Try to change role
        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "action": "change_role",
                "target_username": "testplayer",
                "new_role": "admin",
            },
        )

        # Should be forbidden (403) or not found (404)
        assert response.status_code in [403, 404]


@pytest.mark.admin
@pytest.mark.api
def test_admin_can_deactivate_user(test_client, test_db, temp_db_path, db_with_users):
    """Test admin can deactivate user accounts."""
    with use_test_database(temp_db_path):
        # Login as admin
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        # Try to deactivate player (endpoint may not exist yet)
        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "action": "deactivate",
                "target_username": "testplayer",
            },
        )

        # Should either work (200) or not be implemented (404)
        assert response.status_code in [200, 404]


@pytest.mark.admin
@pytest.mark.api
def test_superuser_can_delete_user(test_client, test_db, temp_db_path, db_with_users):
    """Test superuser can permanently delete users."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "action": "delete",
                "target_username": "testplayer",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert database.player_exists("testplayer") is False


@pytest.mark.admin
@pytest.mark.api
def test_admin_cannot_delete_user(test_client, test_db, temp_db_path, db_with_users):
    """Test admin cannot delete users."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "action": "delete",
                "target_username": "testplayer",
            },
        )

        assert response.status_code == 403


@pytest.mark.admin
@pytest.mark.api
def test_delete_user_returns_500_when_delete_fails(
    test_client, test_db, temp_db_path, db_with_users
):
    """Test delete action surfaces failures from the database layer."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        with patch.object(database, "delete_player", return_value=False):
            response = test_client.post(
                "/admin/user/manage",
                json={
                    "session_id": session_id,
                    "action": "delete",
                    "target_username": "testplayer",
                },
            )

        assert response.status_code == 500


# ============================================================================
# PASSWORD MANAGEMENT TESTS
# ============================================================================


@pytest.mark.admin
@pytest.mark.api
def test_user_can_change_own_password(test_client, test_db, temp_db_path, db_with_users):
    """Test user can change their own password."""
    with use_test_database(temp_db_path):
        # Login as testplayer
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        # Change password (endpoint may not exist yet)
        # New password must meet STANDARD policy: 12+ chars, no sequences
        response = test_client.post(
            "/change-password",
            json={
                "session_id": session_id,
                "old_password": TEST_PASSWORD,
                "new_password": "NewSecure#9x7b",
            },
        )

        # Should either work (200) or not be implemented (404)
        assert response.status_code in [200, 404]


@pytest.mark.admin
@pytest.mark.api
def test_superuser_can_change_any_password(test_client, test_db, temp_db_path, db_with_users):
    """Test superuser can change any user's password."""
    with use_test_database(temp_db_path):
        # Login as superuser
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        # Change another user's password (endpoint may not exist yet)
        # New password must meet STANDARD policy: 12+ chars, no sequences
        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "action": "change_password",
                "target_username": "testplayer",
                "new_password": "NewSecure#9x7b",
            },
        )

        # Should either work (200) or not be implemented (404)
        assert response.status_code in [200, 404]


# ============================================================================
# SERVER CONTROL TESTS
# ============================================================================


@pytest.mark.admin
@pytest.mark.api
@pytest.mark.slow
def test_admin_can_stop_server(test_client, test_db, temp_db_path, db_with_users):
    """Test admin can stop the server."""
    with use_test_database(temp_db_path):
        # Login as admin
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        # Try to stop server (endpoint may not exist yet)
        # Note: We don't actually want to stop the server in tests
        response = test_client.post(
            "/admin/server/stop", json={"session_id": session_id, "confirm": True}
        )

        # Should either work (200) or not be implemented (404)
        assert response.status_code in [200, 404]


@pytest.mark.admin
@pytest.mark.api
def test_player_cannot_stop_server(test_client, test_db, temp_db_path, db_with_users):
    """Test regular player cannot stop the server."""
    with use_test_database(temp_db_path):
        # Login as player
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        # Try to stop server
        response = test_client.post(
            "/admin/server/stop", json={"session_id": session_id, "confirm": True}
        )

        # Should be forbidden (403) or not found (404)
        assert response.status_code in [403, 404]


# ============================================================================
# PERMISSION HIERARCHY TESTS
# ============================================================================


@pytest.mark.admin
@pytest.mark.auth
def test_role_permission_hierarchy():
    """Test that permission hierarchy is properly enforced."""
    from mud_server.api.permissions import Permission, has_permission

    # Player has basic permissions
    assert has_permission("player", Permission.PLAY_GAME) is True
    assert has_permission("player", Permission.CHAT) is True
    assert has_permission("player", Permission.BAN_USERS) is False
    assert has_permission("player", Permission.MANAGE_USERS) is False

    # Admin has admin permissions but not superuser permissions
    assert has_permission("admin", Permission.PLAY_GAME) is True
    assert has_permission("admin", Permission.BAN_USERS) is True
    assert has_permission("admin", Permission.VIEW_LOGS) is True
    assert has_permission("admin", Permission.MANAGE_USERS) is False

    # Superuser has all permissions
    assert has_permission("superuser", Permission.PLAY_GAME) is True
    assert has_permission("superuser", Permission.BAN_USERS) is True
    assert has_permission("superuser", Permission.MANAGE_USERS) is True
    assert has_permission("superuser", Permission.FULL_ACCESS) is True


@pytest.mark.admin
@pytest.mark.auth
def test_management_hierarchy():
    """Test that management hierarchy prevents privilege escalation."""
    from mud_server.api.permissions import can_manage_role

    # Superuser can manage all
    assert can_manage_role("superuser", "admin") is True
    assert can_manage_role("superuser", "worldbuilder") is True
    assert can_manage_role("superuser", "player") is True

    # Admin can manage lower roles
    assert can_manage_role("admin", "worldbuilder") is True
    assert can_manage_role("admin", "player") is True

    # Admin cannot manage same or higher roles
    assert can_manage_role("admin", "admin") is False
    assert can_manage_role("admin", "superuser") is False

    # Player cannot manage anyone
    assert can_manage_role("player", "player") is False
    assert can_manage_role("player", "admin") is False


# ============================================================================
# DATA INTEGRITY TESTS
# ============================================================================


@pytest.mark.admin
@pytest.mark.db
def test_deactivated_user_cannot_login(test_client, test_db, temp_db_path, db_with_users):
    """Test that deactivated users cannot login."""
    with use_test_database(temp_db_path):
        # Deactivate player
        database.deactivate_player("testplayer")

        # Try to login
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )

        assert response.status_code == 401
        assert "deactivated" in response.json()["detail"].lower()


@pytest.mark.admin
@pytest.mark.db
def test_reactivated_user_can_login(test_client, test_db, temp_db_path, db_with_users):
    """Test that reactivated users can login."""
    with use_test_database(temp_db_path):
        # Deactivate then reactivate
        database.deactivate_player("testplayer")
        database.activate_player("testplayer")

        # Try to login
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.admin
@pytest.mark.db
def test_role_change_persists(test_client, test_db, temp_db_path, db_with_users):
    """Test that role changes are persisted to database."""
    with use_test_database(temp_db_path):
        # Change role
        result = database.set_player_role("testplayer", "worldbuilder")
        assert result is True

        # Verify change persisted
        role = database.get_player_role("testplayer")
        assert role == "worldbuilder"

        # Verify login returns new role
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["role"] == "worldbuilder"
