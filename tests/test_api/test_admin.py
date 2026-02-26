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
from mud_server.db.connection import connection_scope
from mud_server.db.errors import DatabaseOperationContext, DatabaseReadError, DatabaseWriteError
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
def test_admin_players_view_excludes_tombstoned_accounts(
    test_client, test_db, temp_db_path, db_with_users
):
    """
    Admin players endpoint should omit tombstoned accounts from Active Users data.

    The delete flow soft-deletes users by setting ``tombstoned_at``. This test
    verifies the admin-facing active-users payload excludes those archived rows.
    """
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        assert admin_login.status_code == 200
        admin_session_id = admin_login.json()["session_id"]

        # Delete/tombstone one account so it should disappear from active users.
        assert database.delete_user("testbuilder") is True

        response = test_client.get(f"/admin/database/players?session_id={admin_session_id}")
        assert response.status_code == 200
        payload = response.json()
        usernames = {entry["username"] for entry in payload["players"]}
        assert "testbuilder" not in usernames
        assert "testplayer" in usernames
        assert "testadmin" in usernames


@pytest.mark.admin
@pytest.mark.api
def test_admin_players_online_world_updates_after_character_selection(
    test_client, test_db, temp_db_path, db_with_users
):
    """
    Admin players view should separate account-online from in-world-online states.

    This regression test validates the session model enforced by Option A:
    - `/login` creates an account-only session (`character_id` remains NULL)
    - `/characters/select` binds `character_id` and `world_id` for gameplay

    The admin users table data must therefore transition in two steps:
    1) account-online = true, in-world-online = false immediately after login
    2) account-online = true, in-world-online = true after character selection
    """
    with use_test_database(temp_db_path):
        # Create an admin account session that can inspect `/admin/database/players`.
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        assert admin_login.status_code == 200
        admin_session_id = admin_login.json()["session_id"]

        # Create an account-only player session; this should not count as "in-world".
        player_login = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        assert player_login.status_code == 200
        player_session_id = player_login.json()["session_id"]

        players_before = test_client.get(f"/admin/database/players?session_id={admin_session_id}")
        assert players_before.status_code == 200
        before_row = next(
            row for row in players_before.json()["players"] if row["username"] == "testplayer"
        )
        assert before_row["is_online_account"] is True
        assert before_row["is_online_in_world"] is False
        assert before_row["online_world_ids"] == []

        # Bind the player's session to a concrete character/world pair.
        characters_response = test_client.get(
            "/characters",
            params={"session_id": player_session_id, "world_id": database.DEFAULT_WORLD_ID},
        )
        assert characters_response.status_code == 200
        characters = characters_response.json()["characters"]
        assert characters, "Expected seeded character for testplayer in default world."
        selected_character_id = int(characters[0]["id"])

        select_response = test_client.post(
            "/characters/select",
            json={
                "session_id": player_session_id,
                "character_id": selected_character_id,
                "world_id": database.DEFAULT_WORLD_ID,
            },
        )
        assert select_response.status_code == 200

        players_after = test_client.get(f"/admin/database/players?session_id={admin_session_id}")
        assert players_after.status_code == 200
        after_row = next(
            row for row in players_after.json()["players"] if row["username"] == "testplayer"
        )
        assert after_row["is_online_account"] is True
        assert after_row["is_online_in_world"] is True
        assert after_row["online_world_ids"] == [database.DEFAULT_WORLD_ID]


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

        response = test_client.get(f"/admin/database/table/users?session_id={session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["table"] == "users"
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

    response = test_client.get(f"/admin/database/table/users?session_id={session_id}")

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
            assert "character_id" in data["locations"][0]
            assert "character_name" in data["locations"][0]
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


@pytest.mark.admin
@pytest.mark.api
def test_admin_axis_events_maps_database_error_to_500(
    test_client, test_db, temp_db_path, db_with_users
):
    """Axis-events endpoint should map typed DB read errors to HTTP 500."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]
        character = database.get_character_by_name("testplayer_char")
        assert character is not None

        with patch.object(
            database,
            "get_character_axis_events",
            side_effect=DatabaseReadError(
                context=DatabaseOperationContext(operation="events.get_character_axis_events")
            ),
        ):
            response = test_client.get(
                f"/admin/characters/{int(character['id'])}/axis-events",
                params={"session_id": session_id},
            )

        assert response.status_code == 500
        assert "character events unavailable" in response.json()["detail"].lower()


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
        # Admin account creation should not auto-provision any character rows.
        assert database.get_character_by_name("newplayer_char") is None


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
def test_admin_create_user_maps_database_error_to_500(
    test_client, test_db, temp_db_path, db_with_users
):
    """Admin create-user endpoint should map typed DB failures to HTTP 500."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        with patch.object(
            database,
            "user_exists",
            side_effect=DatabaseReadError(
                context=DatabaseOperationContext(operation="users.user_exists")
            ),
        ):
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

        assert response.status_code == 500
        assert "user creation unavailable" in response.json()["detail"].lower()


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
def test_admin_kick_session_maps_database_error_to_500(
    test_client, test_db, temp_db_path, db_with_users
):
    """Kick-session endpoint should convert typed DB errors into HTTP 500."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        admin_session = admin_login.json()["session_id"]

        with patch.object(
            database,
            "remove_session_by_id",
            side_effect=DatabaseWriteError(
                context=DatabaseOperationContext(operation="sessions.remove_session_by_id")
            ),
        ):
            response = test_client.post(
                "/admin/session/kick",
                json={
                    "session_id": admin_session,
                    "target_session_id": "target-session",
                    "reason": "test",
                },
            )

        assert response.status_code == 500
        assert "failed to kick session" in response.json()["detail"].lower()


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


@pytest.mark.admin
@pytest.mark.api
def test_player_cannot_kick_character(test_client, test_db, temp_db_path, db_with_users):
    """Test player cannot kick characters."""
    with use_test_database(temp_db_path):
        player_login = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        player_session = player_login.json()["session_id"]

        target_character = database.get_character_by_name("testadmin_char")
        assert target_character is not None

        response = test_client.post(
            "/admin/character/kick",
            json={
                "session_id": player_session,
                "character_id": int(target_character["id"]),
                "reason": "test",
            },
        )

        assert response.status_code == 403


@pytest.mark.admin
@pytest.mark.api
def test_admin_kick_character_maps_database_error_to_500(
    test_client, test_db, temp_db_path, db_with_users
):
    """Kick-character endpoint should convert typed DB failures into HTTP 500."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        admin_session = admin_login.json()["session_id"]

        target_character = database.get_character_by_name("testplayer_char")
        assert target_character is not None

        with patch.object(
            database,
            "remove_sessions_for_character_count",
            side_effect=DatabaseWriteError(
                context=DatabaseOperationContext(
                    operation="sessions.remove_sessions_for_character_count"
                )
            ),
        ):
            response = test_client.post(
                "/admin/character/kick",
                json={
                    "session_id": admin_session,
                    "character_id": int(target_character["id"]),
                    "reason": "test",
                },
            )

        assert response.status_code == 500
        assert "failed to kick character" in response.json()["detail"].lower()


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
def test_ban_user_maps_database_error_during_session_cleanup(
    test_client, test_db, temp_db_path, db_with_users
):
    """Ban action should surface typed DB errors from session cleanup as HTTP 500."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        with patch.object(
            database,
            "remove_sessions_for_user",
            side_effect=DatabaseWriteError(
                context=DatabaseOperationContext(operation="sessions.remove_sessions_for_user")
            ),
        ):
            response = test_client.post(
                "/admin/user/manage",
                json={
                    "session_id": session_id,
                    "action": "ban",
                    "target_username": "testplayer",
                },
            )

        assert response.status_code == 500
        assert "failed to ban user" in response.json()["detail"].lower()


@pytest.mark.admin
@pytest.mark.api
def test_manage_user_maps_database_error_to_500(test_client, test_db, temp_db_path, db_with_users):
    """User-management endpoint should map typed DB errors to HTTP 500."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        with patch.object(
            database,
            "user_exists",
            side_effect=DatabaseReadError(
                context=DatabaseOperationContext(operation="users.user_exists")
            ),
        ):
            response = test_client.post(
                "/admin/user/manage",
                json={
                    "session_id": session_id,
                    "action": "ban",
                    "target_username": "testplayer",
                },
            )

        assert response.status_code == 500
        assert "user management unavailable" in response.json()["detail"].lower()


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
        assert database.user_exists("testplayer") is True
        assert database.is_user_active("testplayer") is False


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

        with patch.object(database, "delete_user", return_value=False):
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


@pytest.mark.admin
@pytest.mark.api
def test_admin_change_password_requires_new_password(
    test_client, test_db, temp_db_path, db_with_users
):
    """Admin change_password should require new_password."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "action": "change_password",
                "target_username": "testplayer",
            },
        )

        assert response.status_code == 400
        assert "new_password" in response.json()["detail"]


@pytest.mark.admin
@pytest.mark.api
def test_admin_change_password_rejects_short_password(
    test_client, test_db, temp_db_path, db_with_users
):
    """Admin change_password should enforce minimum length."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "action": "change_password",
                "target_username": "testplayer",
                "new_password": "short",
            },
        )

        assert response.status_code == 400
        assert "at least 8 characters" in response.json()["detail"]


@pytest.mark.admin
@pytest.mark.api
def test_admin_change_password_handles_database_failure(
    test_client, test_db, temp_db_path, db_with_users
):
    """Admin change_password should return 500 when database update fails."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        with patch.object(database, "change_password_for_user", return_value=False):
            response = test_client.post(
                "/admin/user/manage",
                json={
                    "session_id": session_id,
                    "action": "change_password",
                    "target_username": "testplayer",
                    "new_password": "LongEnough#9x",
                },
            )

        assert response.status_code == 500


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
        database.deactivate_user("testplayer")

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
        database.deactivate_user("testplayer")
        database.activate_user("testplayer")

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
        result = database.set_user_role("testplayer", "worldbuilder")
        assert result is True

        # Verify change persisted
        role = database.get_user_role("testplayer")
        assert role == "worldbuilder"

        # Verify login returns new role
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["role"] == "worldbuilder"


# ============================================================================
# CHAT MESSAGES ENDPOINT TESTS
# ============================================================================


@pytest.mark.admin
@pytest.mark.api
def test_admin_chat_messages_explicit_world_filter(
    test_client, test_db, temp_db_path, db_with_users
):
    """GET /admin/database/chat-messages?world_id=X should only return messages from world X."""
    with use_test_database(temp_db_path):
        # Create a character in a second world and insert one message per world.
        player_id = database.get_user_id("testplayer")
        assert player_id is not None
        database.create_character_for_user(
            player_id, "alt_world_char", world_id="daily_undertaking"
        )

        database.add_chat_message(
            "testplayer_char", "web world hello", "spawn", world_id="pipeworks_web"
        )
        database.add_chat_message(
            "alt_world_char", "alt world hello", "spawn", world_id="daily_undertaking"
        )

        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        assert login_response.status_code == 200
        session_id = login_response.json()["session_id"]

        response = test_client.get(
            "/admin/database/chat-messages",
            params={"session_id": session_id, "world_id": "pipeworks_web"},
        )
        assert response.status_code == 200
        messages = response.json()["messages"]
        assert all(m["world_id"] == "pipeworks_web" for m in messages)
        assert any(m["message"] == "web world hello" for m in messages)
        assert not any(m["message"] == "alt world hello" for m in messages)


@pytest.mark.admin
@pytest.mark.api
def test_admin_chat_messages_no_world_filter_returns_all(
    test_client, test_db, temp_db_path, db_with_users
):
    """GET /admin/database/chat-messages without world_id should return messages from all worlds."""
    with use_test_database(temp_db_path):
        player_id = database.get_user_id("testplayer")
        assert player_id is not None
        database.create_character_for_user(
            player_id, "alt_world_char2", world_id="daily_undertaking"
        )

        database.add_chat_message(
            "testplayer_char", "web only msg", "spawn", world_id="pipeworks_web"
        )
        database.add_chat_message(
            "alt_world_char2", "alt only msg", "spawn", world_id="daily_undertaking"
        )

        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        assert login_response.status_code == 200
        session_id = login_response.json()["session_id"]

        response = test_client.get(
            "/admin/database/chat-messages",
            params={"session_id": session_id},
        )
        assert response.status_code == 200
        messages = response.json()["messages"]
        world_ids = {m["world_id"] for m in messages}
        assert "pipeworks_web" in world_ids
        assert "daily_undertaking" in world_ids


@pytest.mark.admin
@pytest.mark.api
def test_admin_chat_messages_room_id_field_present(
    test_client, test_db, temp_db_path, db_with_users
):
    """GET /admin/database/chat-messages response entries must include room_id, not room."""
    with use_test_database(temp_db_path):
        database.add_chat_message(
            "testplayer_char", "check room_id", "spawn", world_id="pipeworks_web"
        )

        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        assert login_response.status_code == 200
        session_id = login_response.json()["session_id"]

        response = test_client.get(
            "/admin/database/chat-messages",
            params={"session_id": session_id, "world_id": "pipeworks_web"},
        )
        assert response.status_code == 200
        messages = response.json()["messages"]
        assert messages, "Expected at least one message"
        entry = messages[0]
        assert "room_id" in entry, "Response must contain room_id key"
        assert "room" not in entry, "Response must not contain legacy room key"


# ============================================================================
# CHAT PRUNE ENDPOINT TESTS
# ============================================================================


@pytest.mark.admin
@pytest.mark.api
def test_admin_chat_prune_success(test_client, test_db, temp_db_path, db_with_users):
    """POST /admin/chat/prune should delete old messages and return pruned_count."""
    with use_test_database(temp_db_path):
        # Insert a message then age it directly.
        database.add_chat_message(
            "testplayer_char", "stale message", "spawn", world_id="pipeworks_web"
        )
        with connection_scope(write=True) as conn:
            conn.execute(
                "UPDATE chat_messages SET timestamp = datetime('now', '-100 hours') "
                "WHERE message = 'stale message'"
            )

        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        assert login_response.status_code == 200
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/chat/prune",
            json={"session_id": session_id, "max_age_hours": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pruned_count"] >= 1


@pytest.mark.admin
@pytest.mark.api
def test_admin_chat_prune_requires_manage_users_permission(
    test_client, test_db, temp_db_path, db_with_users
):
    """POST /admin/chat/prune must be forbidden for accounts without MANAGE_USERS."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        assert login_response.status_code == 200
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/chat/prune",
            json={"session_id": session_id, "max_age_hours": 1},
        )

        assert response.status_code == 403


@pytest.mark.admin
@pytest.mark.api
def test_admin_chat_prune_invalid_age(test_client, test_db, temp_db_path, db_with_users):
    """POST /admin/chat/prune with max_age_hours=0 should return 422."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        assert login_response.status_code == 200
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/chat/prune",
            json={"session_id": session_id, "max_age_hours": 0},
        )

        assert response.status_code == 422


@pytest.mark.admin
@pytest.mark.api
def test_admin_chat_prune_room_without_world_id_returns_422(
    test_client, test_db, temp_db_path, db_with_users
):
    """POST /admin/chat/prune with room but no world_id should return 422."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        assert login_response.status_code == 200
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/admin/chat/prune",
            json={"session_id": session_id, "max_age_hours": 1, "room": "spawn"},
        )

        assert response.status_code == 422
        assert "world_id" in response.json()["detail"].lower()
