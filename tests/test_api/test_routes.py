"""
API endpoint tests for FastAPI routes (mud_server/api/routes.py).

Tests cover:
- Public endpoints (login, register, health)
- Authenticated endpoints (command, logout, status, chat)
- Admin endpoints (database views, user management, server control)
- Command parsing and execution
- Error handling and validation

Uses TestClient for HTTP request testing.
"""

import sqlite3
from unittest.mock import patch

import pytest

from mud_server.config import config, use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD


def assert_login_direct_deprecated(response) -> None:
    """
    Assert the migration contract for the deprecated /login-direct endpoint.

    Option A enforces account-first authentication, so legacy direct-world
    requests must return a stable error that points clients to:
      1) /login
      2) /characters/select
    """
    assert response.status_code == 410
    detail = response.json().get("detail", "")
    assert "Direct world login is deprecated" in detail
    assert "/login" in detail
    assert "/characters/select" in detail


# ============================================================================
# PUBLIC ENDPOINT TESTS
# ============================================================================


@pytest.mark.api
def test_root_endpoint(test_client):
    """Test root endpoint returns API info."""
    response = test_client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "MUD Server API" in data["message"]


@pytest.mark.api
def test_health_endpoint(test_client):
    """Test health check endpoint."""
    response = test_client.get("/health")

    # Health endpoint should exist and return 200
    assert response.status_code in [200, 404]  # May not be implemented yet


# ============================================================================
# REGISTRATION TESTS
# ============================================================================


@pytest.mark.api
def test_register_success(test_client, test_db, temp_db_path):
    """Test successful user registration."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/register",
            json={
                "username": "newuser",
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "created successfully" in data["message"].lower()
        assert database.get_player_account_origin("newuser") == "visitor"
        # Account registration no longer auto-provisions a bootstrap character.
        assert database.get_character_by_name("newuser_char") is None


@pytest.mark.api
def test_register_username_too_short(test_client):
    """Test registration with username too short."""
    response = test_client.post(
        "/register",
        json={"username": "a", "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD},
    )

    assert response.status_code == 400
    assert "2-20 characters" in response.json()["detail"]


@pytest.mark.api
def test_register_username_too_long(test_client):
    """Test registration with username too long."""
    response = test_client.post(
        "/register",
        json={"username": "a" * 30, "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD},
    )

    assert response.status_code == 400


@pytest.mark.api
def test_register_password_too_short(test_client):
    """Test registration with password too short."""
    response = test_client.post(
        "/register", json={"username": "newuser", "password": "short", "password_confirm": "short"}
    )

    assert response.status_code == 400
    # STANDARD policy requires at least 12 characters
    assert "at least 12 characters" in response.json()["detail"]


@pytest.mark.api
def test_register_passwords_dont_match(test_client):
    """Test registration when passwords don't match."""
    response = test_client.post(
        "/register",
        json={"username": "newuser", "password": TEST_PASSWORD, "password_confirm": "different123"},
    )

    assert response.status_code == 400
    assert "do not match" in response.json()["detail"].lower()


@pytest.mark.api
def test_register_duplicate_username(test_client, test_db, temp_db_path, db_with_users):
    """Test registration with existing username."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/register",
            json={
                "username": "testplayer",
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
            },
        )

        assert response.status_code == 400
        assert "already taken" in response.json()["detail"].lower()


@pytest.mark.api
def test_register_create_user_failure(test_client, test_db, temp_db_path):
    """Test registration returns 500 when account creation fails."""
    with use_test_database(temp_db_path):
        with patch.object(database, "create_user_with_password", return_value=False):
            response = test_client.post(
                "/register",
                json={
                    "username": "newuser",
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                },
            )

        assert response.status_code == 500


@pytest.mark.api
def test_register_closed_by_policy(test_client, test_db, temp_db_path):
    """Registration should return 403 when account registration mode is closed."""
    original_mode = config.registration.account_registration_mode
    config.registration.account_registration_mode = "closed"
    try:
        with use_test_database(temp_db_path):
            response = test_client.post(
                "/register",
                json={
                    "username": "newuser",
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                },
            )
        assert response.status_code == 403
        assert "closed" in response.json()["detail"].lower()
    finally:
        config.registration.account_registration_mode = original_mode


# ============================================================================
# GUEST REGISTRATION TESTS
# ============================================================================


@pytest.mark.api
def test_register_guest_success(test_client, test_db, temp_db_path):
    """Test successful guest registration with server-generated username."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/register-guest",
            json={
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
                "character_name": "Guest Traveler",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["username"].startswith("guest_")
        assert len(data["username"]) <= 20
        assert database.get_user_account_origin(data["username"]) == "visitor"
        assert data["character_name"] == "Guest Traveler"
        assert data["world_id"] == database.DEFAULT_WORLD_ID
        assert isinstance(data["character_id"], int)
        assert data["entity_state"] is not None
        assert "axes" in data["entity_state"]
        assert isinstance(data["entity_state"]["seed"], int)
        assert data["entity_state"]["seed"] > 0
        assert "wealth" in data["entity_state"]["axes"]
        assert "legitimacy" in data["entity_state"]["axes"]
        assert data["entity_state_error"] is None

        character = database.get_character_by_name("Guest Traveler")
        assert character is not None
        assert character["is_guest_created"] is True


@pytest.mark.api
def test_register_guest_disabled_by_policy(test_client, test_db, temp_db_path):
    """Guest registration should return 403 when guest mode is disabled."""
    original_guest_enabled = config.registration.guest_registration_enabled
    config.registration.guest_registration_enabled = False
    try:
        with use_test_database(temp_db_path):
            response = test_client.post(
                "/register-guest",
                json={
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                    "character_name": "Guest Disabled",
                },
            )
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"].lower()
    finally:
        config.registration.guest_registration_enabled = original_guest_enabled


@pytest.mark.api
def test_register_guest_entity_service_failure_does_not_block_signup(
    test_client, test_db, temp_db_path
):
    """Local snapshot should keep guest registration resilient to entity API outages."""
    import requests

    with use_test_database(temp_db_path):
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError):
            response = test_client.post(
                "/register-guest",
                json={
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                    "character_name": "Guest Cartographer",
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["entity_state"] is not None
    assert "axes" in payload["entity_state"]
    assert payload["entity_state_error"] is None


@pytest.mark.api
def test_register_guest_returns_error_when_local_and_external_state_unavailable(
    test_client, test_db, temp_db_path
):
    """When both snapshot and integration fail, registration should still succeed."""
    import requests

    with use_test_database(temp_db_path):
        with patch.object(database, "get_character_axis_state", return_value=None):
            with patch("requests.post", side_effect=requests.exceptions.ConnectionError):
                response = test_client.post(
                    "/register-guest",
                    json={
                        "password": TEST_PASSWORD,
                        "password_confirm": TEST_PASSWORD,
                        "character_name": "Guest Cartographer 2",
                    },
                )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["entity_state"] is None
    assert payload["entity_state_error"] is not None
    assert "unavailable" in payload["entity_state_error"].lower()


@pytest.mark.api
def test_register_guest_falls_back_to_external_state_when_local_missing(
    test_client, test_db, temp_db_path
):
    """Local snapshot miss should fall back to external entity API payload."""
    with use_test_database(temp_db_path):

        class FakeEntityResponse:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "seed": 999,
                    "character": {"demeanor": "wary"},
                    "occupation": {"visibility": "routine"},
                }

        with patch.object(database, "get_character_axis_state", return_value=None):
            with patch("requests.post", return_value=FakeEntityResponse()):
                response = test_client.post(
                    "/register-guest",
                    json={
                        "password": TEST_PASSWORD,
                        "password_confirm": TEST_PASSWORD,
                        "character_name": "Guest Fallback",
                    },
                )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["entity_state"] is not None
    assert payload["entity_state"]["seed"] == 999
    assert payload["entity_state"]["character"]["demeanor"] == "wary"
    assert payload["entity_state_error"] is None


@pytest.mark.api
def test_register_guest_returns_external_error_when_local_error_is_empty(
    test_client, test_db, temp_db_path
):
    """External fallback error should be used when local helper gives no message."""
    with use_test_database(temp_db_path):
        with patch(
            "mud_server.api.routes.auth._fetch_local_axis_snapshot_for_character",
            return_value=(None, None),
        ):
            with patch(
                "mud_server.api.routes.auth._fetch_entity_state_for_character",
                return_value=(None, "Entity fallback unavailable."),
            ):
                response = test_client.post(
                    "/register-guest",
                    json={
                        "password": TEST_PASSWORD,
                        "password_confirm": TEST_PASSWORD,
                        "character_name": "Guest Fallback Error",
                    },
                )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["entity_state"] is None
    assert payload["entity_state_error"] == "Entity fallback unavailable."


@pytest.mark.api
def test_register_guest_fails_when_created_character_cannot_be_resolved(
    test_client, test_db, temp_db_path
):
    """If character lookup fails post-create, endpoint should rollback with 500."""
    with use_test_database(temp_db_path):
        with patch.object(database, "get_character_by_name", return_value=None):
            response = test_client.post(
                "/register-guest",
                json={
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                    "character_name": "Guest Missing Character",
                },
            )

    assert response.status_code == 500
    assert "failed to resolve created character" in response.json()["detail"].lower()


@pytest.mark.api
def test_register_guest_character_name_taken(test_client, test_db, temp_db_path, db_with_users):
    """Test guest registration fails when character name already exists."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "TakenName") is True

        response = test_client.post(
            "/register-guest",
            json={
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
                "character_name": "TakenName",
            },
        )

        assert response.status_code == 400
        assert "already taken" in response.json()["detail"].lower()


@pytest.mark.api
def test_register_guest_passwords_dont_match(test_client):
    """Test guest registration rejects mismatched passwords."""
    response = test_client.post(
        "/register-guest",
        json={
            "password": TEST_PASSWORD,
            "password_confirm": "different123",
            "character_name": "Guest Wanderer",
        },
    )

    assert response.status_code == 400
    assert "do not match" in response.json()["detail"].lower()


@pytest.mark.api
def test_register_guest_username_allocation_failure(test_client, test_db, temp_db_path):
    """Test guest registration fails when no usernames can be allocated."""
    with use_test_database(temp_db_path):
        with patch.object(database, "user_exists", return_value=True):
            response = test_client.post(
                "/register-guest",
                json={
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                    "character_name": "Guest Nomad",
                },
            )

        assert response.status_code == 500
        assert "allocate" in response.json()["detail"].lower()


@pytest.mark.api
def test_register_guest_create_user_failure(test_client, test_db, temp_db_path):
    """Test guest registration fails when account creation returns False."""
    with use_test_database(temp_db_path):
        with patch.object(database, "create_user_with_password", return_value=False):
            response = test_client.post(
                "/register-guest",
                json={
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                    "character_name": "Guest Baker",
                },
            )

        assert response.status_code == 500
        assert "create guest account" in response.json()["detail"].lower()


@pytest.mark.api
def test_register_guest_user_id_missing_rolls_back(test_client, test_db, temp_db_path):
    """Test guest registration rolls back when user id cannot be resolved."""
    with use_test_database(temp_db_path):
        with (
            patch.object(database, "get_user_id", return_value=None),
            patch.object(database, "delete_user") as delete_user,
        ):
            response = test_client.post(
                "/register-guest",
                json={
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                    "character_name": "Guest Sailor",
                },
            )

        assert response.status_code == 500
        delete_user.assert_called_once()


@pytest.mark.api
def test_register_guest_character_creation_failure(test_client, test_db, temp_db_path):
    """Test guest registration fails when character creation returns False."""
    with use_test_database(temp_db_path):
        with patch.object(database, "create_character_for_user", return_value=False):
            response = test_client.post(
                "/register-guest",
                json={
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                    "character_name": "Guest Weaver",
                },
            )

        assert response.status_code == 400
        assert "character name already taken" in response.json()["detail"].lower()


# ============================================================================
# LOGIN TESTS
# ============================================================================


@pytest.mark.api
def test_login_success(test_client, test_db, temp_db_path, db_with_users):
    """Test successful login."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "session_id" in data
        assert data["role"] == "player"
        assert "Login successful" in data["message"]


@pytest.mark.api
def test_login_wrong_password(test_client, test_db, temp_db_path, db_with_users):
    """Test login with incorrect password."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": "wrongpassword"}
        )

        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]


@pytest.mark.api
def test_login_nonexistent_user(test_client, test_db, temp_db_path):
    """Test login with non-existent username."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login", json={"username": "nonexistent", "password": TEST_PASSWORD}
        )

        assert response.status_code == 401


@pytest.mark.api
def test_login_creates_session(test_client, test_db, temp_db_path, db_with_users):
    """Test that login creates an account-only session in the database."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )

        session_id = response.json()["session_id"]
        session = database.get_session_by_id(session_id)
        assert session is not None
        assert session["user_id"] == database.get_user_id("testplayer")
        assert session["client_type"] == "unknown"
        # Account-first invariant: login does not implicitly select a
        # character or world.
        assert session["character_id"] is None
        assert session["world_id"] is None


@pytest.mark.api
def test_login_records_client_type_header(test_client, test_db, temp_db_path, db_with_users):
    """Test that login records the client type header."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login",
            json={"username": "testplayer", "password": TEST_PASSWORD},
            headers={"X-Client-Type": "TUI"},
        )

        session_id = response.json()["session_id"]
        session = database.get_session_by_id(session_id)
        assert session is not None
        assert session["client_type"] == "tui"


@pytest.mark.api
def test_login_blank_client_type_header_defaults_unknown(
    test_client, test_db, temp_db_path, db_with_users
):
    """Test blank client type header is coerced to unknown."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login",
            json={"username": "testplayer", "password": TEST_PASSWORD},
            headers={"X-Client-Type": "   "},
        )

        session_id = response.json()["session_id"]
        session = database.get_session_by_id(session_id)
        assert session is not None
        assert session["client_type"] == "unknown"


@pytest.mark.api
def test_login_username_too_short(test_client):
    """Test login with username too short."""
    response = test_client.post("/login", json={"username": "a", "password": TEST_PASSWORD})

    assert response.status_code == 400


@pytest.mark.api
def test_login_deactivated_user(test_client, test_db, temp_db_path, db_with_users):
    """Test login with a deactivated account."""
    with use_test_database(temp_db_path):
        database.deactivate_user("testplayer")
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )

        assert response.status_code == 401
        assert "deactivated" in response.json()["detail"].lower()


@pytest.mark.api
def test_login_invalid_user_record(test_client, test_db, temp_db_path, db_with_users):
    """Test login fails when user id lookup fails."""
    with use_test_database(temp_db_path):
        with patch.object(database, "get_user_id", return_value=None):
            response = test_client.post(
                "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
            )

        assert response.status_code == 401
        assert "invalid user record" in response.json()["detail"].lower()


@pytest.mark.api
def test_login_create_session_failure(test_client, test_db, temp_db_path, db_with_users):
    """Test login fails when session creation fails."""
    with use_test_database(temp_db_path):
        with patch.object(database, "create_session", return_value=False):
            response = test_client.post(
                "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
            )

        assert response.status_code == 500
        assert "failed to create session" in response.json()["detail"].lower()


@pytest.mark.api
def test_login_direct_create_session_failure(test_client, test_db, temp_db_path, db_with_users):
    """Deprecated login-direct should return migration guidance."""
    with use_test_database(temp_db_path):
        with patch.object(database, "create_session", return_value=False):
            response = test_client.post(
                "/login-direct",
                json={
                    "username": "testplayer",
                    "password": TEST_PASSWORD,
                    "world_id": "pipeworks_web",
                    "character_name": "testplayer_char",
                },
            )

        assert_login_direct_deprecated(response)


# ============================================================================
# CHARACTER SELECTION TESTS
# ============================================================================


@pytest.mark.api
def test_list_characters(test_client, test_db, temp_db_path, db_with_users):
    """Test listing characters for a valid session."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get("/characters", params={"session_id": session_id})

        assert response.status_code == 200
        data = response.json()
        assert "characters" in data
        assert any(char["name"] == "testplayer_char" for char in data["characters"])


@pytest.mark.api
def test_list_characters_excludes_legacy_defaults_when_real_character_exists(
    test_client, test_db, temp_db_path, db_with_users
):
    """
    Character listing can hide legacy bootstrap names when explicit characters exist.

    Legacy account provisioning created ``<username>_char`` records. The play
    selector requests ``exclude_legacy_defaults=true`` so users are presented
    with their explicit characters first during the account-first flow.
    """
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "Named Adventurer")

        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(
            "/characters",
            params={
                "session_id": session_id,
                "world_id": database.DEFAULT_WORLD_ID,
                "exclude_legacy_defaults": "true",
            },
        )

        assert response.status_code == 200
        names = [entry["name"] for entry in response.json()["characters"]]
        assert names == ["Named Adventurer"]


@pytest.mark.api
def test_list_characters_exclude_legacy_defaults_keeps_bootstrap_when_only_option(
    test_client, test_db, temp_db_path, db_with_users
):
    """
    Legacy bootstrap character is retained when it is the only available choice.

    This fallback prevents account lockout for users that have not created a
    non-legacy character yet.
    """
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(
            "/characters",
            params={
                "session_id": session_id,
                "world_id": database.DEFAULT_WORLD_ID,
                "exclude_legacy_defaults": "true",
            },
        )

        assert response.status_code == 200
        names = [entry["name"] for entry in response.json()["characters"]]
        assert names == ["testplayer_char"]


@pytest.mark.api
def test_select_character_success(test_client, test_db, temp_db_path, db_with_users):
    """Test selecting a character for the session."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        characters = database.get_user_characters(user_id)
        character_id = characters[0]["id"]

        response = test_client.post(
            "/characters/select",
            json={"session_id": session_id, "character_id": character_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["character_name"] == "testplayer_char"


@pytest.mark.api
def test_select_character_not_owned(test_client, test_db, temp_db_path, db_with_users):
    """Test selecting a character that is not owned by the user."""
    with use_test_database(temp_db_path):
        database.create_user_with_password("otheruser", TEST_PASSWORD)
        other_id = database.get_user_id("otheruser")
        assert other_id is not None
        assert database.create_character_for_user(other_id, "otheruser_char")
        other_character = database.get_user_characters(other_id)[0]

        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/characters/select",
            json={"session_id": session_id, "character_id": other_character["id"]},
        )

        assert response.status_code == 404


@pytest.mark.api
def test_select_character_failure_sets_error(test_client, test_db, temp_db_path, db_with_users):
    """Test select character returns 500 when session update fails."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        character_id = database.get_user_characters(user_id)[0]["id"]

        with patch.object(database, "set_session_character", return_value=False):
            response = test_client.post(
                "/characters/select",
                json={"session_id": session_id, "character_id": character_id},
            )

        assert response.status_code == 500


# ============================================================================
# LOGOUT TESTS
# ============================================================================


@pytest.mark.api
def test_logout_success(authenticated_client, test_db, temp_db_path):
    """Test successful logout."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        # Verify session exists
        assert database.get_session_by_id(session_id) is not None

        # Logout
        response = client.post("/logout", json={"session_id": session_id})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Goodbye" in data["message"]

        # Session should be removed
        assert database.get_session_by_id(session_id) is None


@pytest.mark.api
def test_logout_invalid_session(test_client):
    """Test logout with invalid session."""
    response = test_client.post("/logout", json={"session_id": "invalid-session"})

    assert response.status_code == 401


# ============================================================================
# COMMAND ENDPOINT TESTS
# ============================================================================


@pytest.mark.api
@pytest.mark.game
def test_command_look(authenticated_client, test_db, temp_db_path):
    """Test /command endpoint with 'look' command."""
    with use_test_database(temp_db_path):
        with patch("mud_server.core.world.database.get_characters_in_room", return_value=[]):
            session_id = authenticated_client["session_id"]
            client = authenticated_client["client"]

            response = client.post("/command", json={"session_id": session_id, "command": "look"})

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            # Should contain room description
            assert "Test Spawn" in data["message"]


@pytest.mark.api
@pytest.mark.game
def test_command_inventory(authenticated_client, test_db, temp_db_path):
    """Test /command endpoint with 'inventory' command."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "inventory"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "inventory" in data["message"].lower()


@pytest.mark.api
@pytest.mark.game
def test_command_move_valid(authenticated_client, test_db, temp_db_path):
    """Test /command endpoint with valid movement."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "north"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "move" in data["message"].lower()


@pytest.mark.api
@pytest.mark.game
def test_command_move_invalid(authenticated_client, test_db, temp_db_path):
    """Test /command endpoint with invalid movement."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "west"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "cannot move" in data["message"].lower()


@pytest.mark.api
@pytest.mark.game
def test_command_say(authenticated_client, test_db, temp_db_path):
    """Test /command endpoint with 'say' command."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post(
            "/command", json={"session_id": session_id, "command": "say Hello everyone!"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "You say:" in data["message"]


@pytest.mark.api
@pytest.mark.game
def test_command_recall(authenticated_client, test_db, temp_db_path):
    """Test /command endpoint with 'recall' command."""
    from mud_server.db import database

    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        # Move player away from spawn first
        database.set_player_room("testplayer", "forest")

        response = client.post("/command", json={"session_id": session_id, "command": "recall"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Player should be back at spawn
        assert database.get_player_room("testplayer") == "spawn"


@pytest.mark.api
@pytest.mark.game
def test_command_flee_alias(authenticated_client, test_db, temp_db_path):
    """Test /command endpoint with 'flee' command (alias for recall)."""
    from mud_server.db import database

    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        # Move player away from spawn first
        database.set_player_room("testplayer", "forest")

        response = client.post("/command", json={"session_id": session_id, "command": "flee"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert database.get_player_room("testplayer") == "spawn"


@pytest.mark.api
@pytest.mark.game
def test_command_scurry_alias(authenticated_client, test_db, temp_db_path):
    """Test /command endpoint with 'scurry' command (alias for recall)."""
    from mud_server.db import database

    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        # Move player away from spawn first
        database.set_player_room("testplayer", "forest")

        response = client.post("/command", json={"session_id": session_id, "command": "scurry"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert database.get_player_room("testplayer") == "spawn"


@pytest.mark.api
@pytest.mark.game
def test_command_empty(authenticated_client):
    """Test /command endpoint with empty command."""
    session_id = authenticated_client["session_id"]
    client = authenticated_client["client"]

    response = client.post("/command", json={"session_id": session_id, "command": ""})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


@pytest.mark.api
@pytest.mark.game
def test_command_invalid_session(test_client):
    """Test /command endpoint with invalid session."""
    response = test_client.post(
        "/command", json={"session_id": "invalid-session", "command": "look"}
    )

    assert response.status_code == 401


@pytest.mark.api
@pytest.mark.game
def test_command_get_requires_item(authenticated_client, test_db, temp_db_path):
    """Test /command get requires an item argument."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "get"})

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
@pytest.mark.game
def test_command_get_item(authenticated_client, test_db, temp_db_path):
    """Test /command get with a valid item."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "get torch"})

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
@pytest.mark.game
def test_command_drop_requires_item(authenticated_client, test_db, temp_db_path):
    """Test /command drop requires an item argument."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "drop"})

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
@pytest.mark.game
def test_command_drop_item(authenticated_client, test_db, temp_db_path):
    """Test /command drop with a valid item."""
    with use_test_database(temp_db_path):
        database.set_character_inventory("testplayer", ["torch"])
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "drop torch"})

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
@pytest.mark.game
def test_command_say_requires_message(authenticated_client, test_db, temp_db_path):
    """Test /command say requires a message."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "say"})

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
@pytest.mark.game
def test_command_yell_requires_message(authenticated_client, test_db, temp_db_path):
    """Test /command yell requires a message."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "yell"})

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
@pytest.mark.game
def test_command_yell_success(authenticated_client, test_db, temp_db_path):
    """Test /command yell with a message."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "yell hello"})

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
@pytest.mark.game
def test_command_whisper_requires_target(authenticated_client, test_db, temp_db_path):
    """Test /command whisper requires a target and message."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "whisper"})

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
@pytest.mark.game
def test_command_whisper_requires_message(authenticated_client, test_db, temp_db_path):
    """Test /command whisper requires a message after target."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post(
            "/command", json={"session_id": session_id, "command": "whisper targetonly"}
        )

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
@pytest.mark.game
def test_command_whisper_success(authenticated_client, test_db, temp_db_path, db_with_users):
    """Test /command whisper with a valid target and message."""
    with use_test_database(temp_db_path):
        database.create_session("testadmin", "admin-session")
        admin_char = database.get_character_by_name("testadmin_char")
        assert admin_char is not None
        database.set_session_character("admin-session", admin_char["id"])

        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post(
            "/command",
            json={"session_id": session_id, "command": "whisper testadmin hello"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
@pytest.mark.game
def test_command_unknown(authenticated_client, test_db, temp_db_path):
    """Test /command unknown command handling."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "blorf"})

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
@pytest.mark.game
def test_command_who_lists_players(authenticated_client, test_db, temp_db_path, db_with_users):
    """Test /command who lists active players."""
    with use_test_database(temp_db_path):
        database.create_session("testadmin", "admin-session")
        admin_char = database.get_character_by_name("testadmin_char")
        assert admin_char is not None
        database.set_session_character("admin-session", admin_char["id"])

        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "who"})

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
@pytest.mark.game
def test_command_kick_requires_admin_permissions(authenticated_client, test_db, temp_db_path):
    """Player role should not be able to execute /kick."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post(
            "/command", json={"session_id": session_id, "command": "kick testadmin_char"}
        )

        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "Insufficient permissions" in response.json()["message"]


@pytest.mark.api
@pytest.mark.game
def test_command_kick_as_admin_disconnects_target(
    test_client, test_db, temp_db_path, db_with_users
):
    """Admin /kick should disconnect all sessions for the target character."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        admin_session = admin_login.json()["session_id"]
        admin_characters = admin_login.json()["characters"]
        assert admin_characters
        admin_select = test_client.post(
            "/characters/select",
            json={"session_id": admin_session, "character_id": int(admin_characters[0]["id"])},
        )
        assert admin_select.status_code == 200

        player_login = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        player_session = player_login.json()["session_id"]
        player_characters = player_login.json()["characters"]
        assert player_characters
        player_select = test_client.post(
            "/characters/select",
            json={"session_id": player_session, "character_id": int(player_characters[0]["id"])},
        )
        assert player_select.status_code == 200

        response = test_client.post(
            "/command",
            json={"session_id": admin_session, "command": "kick testplayer_char"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert database.get_session_by_id(player_session) is None


@pytest.mark.api
@pytest.mark.game
def test_command_help(authenticated_client, test_db, temp_db_path):
    """Test /command help returns help text."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "help"})

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
@pytest.mark.game
def test_command_accepts_slash_prefix(authenticated_client, test_db, temp_db_path):
    """Test /command handles slash-prefixed commands."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.post("/command", json={"session_id": session_id, "command": "/look"})

        assert response.status_code == 200
        assert response.json()["success"] is True


# ============================================================================
# STATUS ENDPOINT TESTS
# ============================================================================


@pytest.mark.api
def test_status_endpoint(authenticated_client, test_db, temp_db_path):
    """Test /status endpoint returns player status."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.get(f"/status/{session_id}")

        # Status endpoint may or may not be implemented
        assert response.status_code in [200, 404]


# ============================================================================
# CHAT ENDPOINT TESTS
# ============================================================================


@pytest.mark.api
@pytest.mark.game
def test_chat_endpoint(authenticated_client, test_db, temp_db_path):
    """Test /chat endpoint returns room messages."""
    with use_test_database(temp_db_path):
        session_id = authenticated_client["session_id"]
        client = authenticated_client["client"]

        response = client.get(f"/chat/{session_id}")

        # Chat endpoint may or may not be implemented
        assert response.status_code in [200, 404]


# ============================================================================
# INTEGRATION TEST - Full User Flow
# ============================================================================


@pytest.mark.integration
@pytest.mark.api
def test_full_user_flow(test_client, test_db, temp_db_path):
    """Integration test of complete user flow: register -> login -> play -> logout."""
    with use_test_database(temp_db_path):
        with patch("mud_server.core.world.database.get_characters_in_room", return_value=[]):
            # 1. Register
            register_response = test_client.post(
                "/register",
                json={
                    "username": "flowuser",
                    "password": TEST_PASSWORD,
                    "password_confirm": TEST_PASSWORD,
                },
            )
            assert register_response.status_code == 200

            # 2. Character provisioning is a separate lifecycle step.
            flow_user_id = database.get_user_id("flowuser")
            assert flow_user_id is not None
            assert database.create_character_for_user(flow_user_id, "Flow Runner")

            # 3. Login
            login_response = test_client.post(
                "/login", json={"username": "flowuser", "password": TEST_PASSWORD}
            )
            assert login_response.status_code == 200
            session_id = login_response.json()["session_id"]
            characters = login_response.json()["characters"]
            assert characters

            # Account login is intentionally separate from world entry.
            select_response = test_client.post(
                "/characters/select",
                json={"session_id": session_id, "character_id": int(characters[0]["id"])},
            )
            assert select_response.status_code == 200

            # 4. Look around
            look_response = test_client.post(
                "/command", json={"session_id": session_id, "command": "look"}
            )
            assert look_response.status_code == 200

            # 5. Move
            move_response = test_client.post(
                "/command", json={"session_id": session_id, "command": "north"}
            )
            assert move_response.status_code == 200

            # 6. Say something
            say_response = test_client.post(
                "/command", json={"session_id": session_id, "command": "say Testing!"}
            )
            assert say_response.status_code == 200

            # 7. Logout
            logout_response = test_client.post("/logout", json={"session_id": session_id})
            assert logout_response.status_code == 200

            # Session should be gone
            assert database.get_session_by_id(session_id) is None


@pytest.mark.api
def test_ping_endpoint(test_client, test_db, temp_db_path, db_with_users):
    """Test heartbeat endpoint returns ok for authenticated sessions."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(f"/ping/{session_id}")

        assert response.status_code == 200
        assert response.json()["ok"] is True


@pytest.mark.api
def test_login_direct_success(test_client, test_db, temp_db_path, db_with_users):
    """Deprecated login-direct should return migration guidance."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login-direct",
            json={
                "username": "testplayer",
                "password": TEST_PASSWORD,
                "world_id": "pipeworks_web",
                "character_name": "testplayer_char",
            },
        )

        assert_login_direct_deprecated(response)


@pytest.mark.api
def test_login_direct_requires_character_name(test_client, test_db, temp_db_path, db_with_users):
    """Deprecated login-direct should ignore old payload shape and return 410."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login-direct",
            json={
                "username": "testplayer",
                "password": TEST_PASSWORD,
                "world_id": "pipeworks_web",
            },
        )

        assert_login_direct_deprecated(response)


@pytest.mark.api
def test_login_direct_blocks_multi_world_character_creation(
    test_client, test_db, temp_db_path, db_with_users
):
    """Deprecated login-direct should return migration guidance."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO world_permissions (user_id, world_id, can_access)
            VALUES (?, ?, 1)
            """,
            (user_id, "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        response = test_client.post(
            "/login-direct",
            json={
                "username": "testplayer",
                "password": TEST_PASSWORD,
                "world_id": "daily_undertaking",
                "character_name": "altchar",
                "create_character": True,
            },
        )

        assert_login_direct_deprecated(response)


@pytest.mark.api
def test_login_includes_available_worlds(test_client, test_db, temp_db_path, db_with_users):
    """Login should return available_worlds for selection."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )

        assert response.status_code == 200
        payload = response.json()
        assert "available_worlds" in payload
        assert any(world["id"] == "pipeworks_web" for world in payload["available_worlds"])


@pytest.mark.api
def test_login_includes_invite_locked_world_preview(
    test_client, test_db, temp_db_path, db_with_users
):
    """Login world list should include invite-locked worlds with can_access=false."""
    with use_test_database(temp_db_path):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("invite_only_world", "invite_only_world"),
        )
        conn.commit()
        conn.close()

        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        worlds = response.json()["available_worlds"]
        invite_world = next(world for world in worlds if world["id"] == "invite_only_world")
        assert invite_world["can_access"] is False
        assert invite_world["is_locked"] is True
        assert invite_world["access_mode"] == "invite"


@pytest.mark.api
def test_login_direct_world_access_denied(test_client, test_db, temp_db_path, db_with_users):
    """Deprecated login-direct should return migration guidance."""
    with use_test_database(temp_db_path):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        response = test_client.post(
            "/login-direct",
            json={
                "username": "testplayer",
                "password": TEST_PASSWORD,
                "world_id": "daily_undertaking",
                "character_name": "daily_char",
            },
        )

        assert_login_direct_deprecated(response)


@pytest.mark.api
def test_list_characters_world_access_denied(test_client, test_db, temp_db_path, db_with_users):
    """Listing characters with an inaccessible world_id should be denied."""
    with use_test_database(temp_db_path):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(
            "/characters", params={"session_id": session_id, "world_id": "daily_undertaking"}
        )
        assert response.status_code == 403


@pytest.mark.api
def test_select_character_world_mismatch(test_client, test_db, temp_db_path, db_with_users):
    """Selecting a character with a mismatched world_id should fail."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO world_permissions (user_id, world_id, can_access)
            VALUES (?, ?, 1)
            """,
            (user_id, "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]
        character_id = database.get_user_characters(user_id)[0]["id"]

        response = test_client.post(
            "/characters/select",
            json={
                "session_id": session_id,
                "character_id": character_id,
                "world_id": "daily_undertaking",
            },
        )

        assert response.status_code == 409


@pytest.mark.api
def test_admin_sessions_fallback_without_character(
    test_client, test_db, temp_db_path, db_with_users
):
    """Admin sessions endpoint should work when no character is selected."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        # Keep this session character-less to verify admin introspection
        # endpoints do not depend on gameplay selection state.
        admin_id = database.get_user_id("testadmin")
        assert admin_id is not None
        database.create_character_for_user(admin_id, "admin_alt")

        response = test_client.get(
            "/admin/database/sessions",
            params={"session_id": session_id},
        )
        assert response.status_code == 200


@pytest.mark.api
def test_admin_database_endpoints_with_character_selected(
    test_client, test_db, temp_db_path, db_with_users
):
    """Admin endpoints should return data when a character is selected."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]
        admin_id = database.get_user_id("testadmin")
        assert admin_id is not None
        character_id = database.get_user_characters(admin_id)[0]["id"]

        select_resp = test_client.post(
            "/characters/select",
            json={"session_id": session_id, "character_id": character_id},
        )
        assert select_resp.status_code == 200

        connections = test_client.get(
            "/admin/database/connections", params={"session_id": session_id}
        )
        assert connections.status_code == 200

        locations = test_client.get(
            "/admin/database/player-locations", params={"session_id": session_id}
        )
        assert locations.status_code == 200

        sessions = test_client.get("/admin/database/sessions", params={"session_id": session_id})
        assert sessions.status_code == 200

        messages = test_client.get(
            "/admin/database/chat-messages", params={"session_id": session_id}
        )
        assert messages.status_code == 200


@pytest.mark.api
def test_admin_character_axis_state_endpoint(test_client, test_db, temp_db_path, db_with_users):
    """Admin axis-state endpoint should return axis data for a character."""
    with use_test_database(temp_db_path):
        axes_payload = {
            "axes": {
                "wealth": {
                    "description": "Economic status",
                    "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
                }
            }
        }
        thresholds_payload = {
            "axes": {
                "wealth": {
                    "values": {
                        "poor": {"min": 0.0, "max": 0.49},
                        "wealthy": {"min": 0.5, "max": 1.0},
                    }
                }
            }
        }
        database.seed_axis_registry(
            world_id=database.DEFAULT_WORLD_ID,
            axes_payload=axes_payload,
            thresholds_payload=thresholds_payload,
        )

        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]
        admin_id = database.get_user_id("testadmin")
        assert admin_id is not None

        assert database.create_character_for_user(admin_id, "axis_admin_char")
        character = database.get_character_by_name("axis_admin_char")
        assert character is not None

        response = test_client.get(
            f"/admin/characters/{character['id']}/axis-state",
            params={"session_id": session_id},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["character_id"] == character["id"]
        assert any(axis["axis_name"] == "wealth" for axis in payload["axes"])


@pytest.mark.api
def test_admin_character_axis_events_endpoint(test_client, test_db, temp_db_path, db_with_users):
    """Admin axis-events endpoint should return event history."""
    with use_test_database(temp_db_path):
        axes_payload = {
            "axes": {
                "wealth": {
                    "description": "Economic status",
                    "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
                }
            }
        }
        thresholds_payload = {
            "axes": {
                "wealth": {
                    "values": {
                        "poor": {"min": 0.0, "max": 0.49},
                        "wealthy": {"min": 0.5, "max": 1.0},
                    }
                }
            }
        }
        database.seed_axis_registry(
            world_id=database.DEFAULT_WORLD_ID,
            axes_payload=axes_payload,
            thresholds_payload=thresholds_payload,
        )

        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]
        admin_id = database.get_user_id("testadmin")
        assert admin_id is not None

        assert database.create_character_for_user(admin_id, "axis_event_char")
        character = database.get_character_by_name("axis_event_char")
        assert character is not None

        database.apply_axis_event(
            world_id=database.DEFAULT_WORLD_ID,
            character_id=int(character["id"]),
            event_type_name="axis_event_test",
            deltas={"wealth": 0.1},
        )

        response = test_client.get(
            f"/admin/characters/{character['id']}/axis-events",
            params={"session_id": session_id},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["character_id"] == character["id"]
        assert payload["events"][0]["event_type"] == "axis_event_test"


@pytest.mark.api
def test_admin_kick_session_not_found(test_client, test_db, temp_db_path, db_with_users):
    """Kick session should return not found when session is missing."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/session/kick",
            json={"session_id": session_id, "target_session_id": "missing-session"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
def test_admin_database_worlds_includes_online_status(
    test_client, test_db, temp_db_path, db_with_users
):
    """Worlds operations endpoint should expose world online state and active characters."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        player_login = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        player_session = player_login.json()["session_id"]
        player_characters = player_login.json()["characters"]
        assert player_characters
        select_response = test_client.post(
            "/characters/select",
            json={"session_id": player_session, "character_id": int(player_characters[0]["id"])},
        )
        assert select_response.status_code == 200

        response = test_client.get("/admin/database/worlds", params={"session_id": session_id})
        assert response.status_code == 200
        payload = response.json()
        assert "worlds" in payload

        pipeworks = next(
            world for world in payload["worlds"] if world["world_id"] == "pipeworks_web"
        )
        assert pipeworks["is_online"] is True
        assert pipeworks["active_session_count"] >= 1
        assert any(row["session_id"] == player_session for row in pipeworks["active_characters"])


@pytest.mark.api
def test_admin_kick_character_not_found(test_client, test_db, temp_db_path, db_with_users):
    """Kick character should return 404 for unknown character id."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/character/kick",
            json={"session_id": session_id, "character_id": 999999},
        )
        assert response.status_code == 404


@pytest.mark.api
def test_admin_kick_character_disconnects_active_sessions(
    test_client, test_db, temp_db_path, db_with_users
):
    """Kick character should remove active sessions bound to the target character."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        admin_session = admin_login.json()["session_id"]

        player_login = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        player_session = player_login.json()["session_id"]
        player_characters = player_login.json()["characters"]
        assert player_characters
        select_response = test_client.post(
            "/characters/select",
            json={"session_id": player_session, "character_id": int(player_characters[0]["id"])},
        )
        assert select_response.status_code == 200

        target_character = database.get_character_by_name("testplayer_char")
        assert target_character is not None

        response = test_client.post(
            "/admin/character/kick",
            json={
                "session_id": admin_session,
                "character_id": int(target_character["id"]),
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["removed_sessions"] >= 1
        assert database.get_session_by_id(player_session) is None


@pytest.mark.api
def test_database_table_rows_not_found(test_client, test_db, temp_db_path, db_with_users):
    """Unknown table should return 404."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.get(
            "/admin/database/table/not_a_table", params={"session_id": session_id}
        )
        assert response.status_code == 404


@pytest.mark.api
def test_login_filters_characters_by_world(test_client, test_db, temp_db_path, db_with_users):
    """Login should filter characters when world_id is provided."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO world_permissions (user_id, world_id, can_access)
            VALUES (?, ?, 1)
            """,
            (user_id, "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        response = test_client.post(
            "/login",
            json={
                "username": "testplayer",
                "password": TEST_PASSWORD,
                "world_id": "daily_undertaking",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["characters"] == []


@pytest.mark.api
def test_login_direct_create_character_success(test_client, test_db, temp_db_path, db_with_users):
    """Deprecated login-direct should return migration guidance."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None

        original = config.worlds.allow_multi_world_characters
        config.worlds.allow_multi_world_characters = True

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO world_permissions (user_id, world_id, can_access)
            VALUES (?, ?, 1)
            """,
            (user_id, "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        response = test_client.post(
            "/login-direct",
            json={
                "username": "testplayer",
                "password": TEST_PASSWORD,
                "world_id": "daily_undertaking",
                "character_name": "daily_char",
                "create_character": True,
            },
        )

        assert_login_direct_deprecated(response)

        config.worlds.allow_multi_world_characters = original


@pytest.mark.api
def test_login_direct_character_not_found_without_create(
    test_client, test_db, temp_db_path, db_with_users
):
    """Deprecated login-direct should return migration guidance."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO world_permissions (user_id, world_id, can_access)
            VALUES (?, ?, 1)
            """,
            (user_id, "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        response = test_client.post(
            "/login-direct",
            json={
                "username": "testplayer",
                "password": TEST_PASSWORD,
                "world_id": "daily_undertaking",
                "character_name": "missing_char",
            },
        )

        assert_login_direct_deprecated(response)


@pytest.mark.api
def test_session_locked_to_world_in_game_command(test_client, test_db, temp_db_path, db_with_users):
    """Command execution should respect the session's world_id binding."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO world_permissions (user_id, world_id, can_access)
            VALUES (?, ?, 1)
            """,
            (user_id, "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        assert database.create_character_for_user(
            user_id, "daily_char", world_id="daily_undertaking"
        )

        login_response = test_client.post(
            "/login",
            json={
                "username": "testplayer",
                "password": TEST_PASSWORD,
                "world_id": "daily_undertaking",
            },
        )
        assert login_response.status_code == 200
        session_id = login_response.json()["session_id"]

        daily_char = database.get_character_by_name("daily_char")
        assert daily_char is not None
        select_response = test_client.post(
            "/characters/select",
            json={
                "session_id": session_id,
                "character_id": int(daily_char["id"]),
                "world_id": "daily_undertaking",
            },
        )
        assert select_response.status_code == 200

        # Direct SQL tampering should be rejected by session invariant triggers.
        conn = database.get_connection()
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "UPDATE sessions SET world_id = ? WHERE session_id = ?",
                ("pipeworks_web", session_id),
            )
        conn.close()

        command_response = test_client.post(
            "/command",
            json={"session_id": session_id, "command": "look"},
        )
        assert command_response.status_code == 200

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT world_id FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "daily_undertaking"


@pytest.mark.api
def test_list_characters_world_access_allowed(test_client, test_db, temp_db_path, db_with_users):
    """Listing characters for an allowed world should succeed."""
    with use_test_database(temp_db_path):
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO world_permissions (user_id, world_id, can_access)
            VALUES (?, ?, 1)
            """,
            (user_id, "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.get(
            "/characters", params={"session_id": session_id, "world_id": "daily_undertaking"}
        )
        assert response.status_code == 200
        assert response.json()["characters"] == []


@pytest.mark.api
def test_create_character_for_session_success_open_world(
    test_client, test_db, temp_db_path, db_with_users
):
    """Players should be able to self-create generated characters in open worlds."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        with (
            patch(
                "mud_server.services.character_provisioning.fetch_generated_full_name",
                return_value=("Fimenscu Tarharsh", None),
            ),
            patch(
                "mud_server.services.character_provisioning.fetch_entity_state_for_seed",
                return_value=(None, None),
            ),
        ):
            response = test_client.post(
                "/characters/create",
                json={"session_id": session_id, "world_id": "pipeworks_web"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["character_name"] == "Fimenscu Tarharsh"

        character = database.get_character_by_name("Fimenscu Tarharsh")
        assert character is not None
        assert character["world_id"] == "pipeworks_web"


@pytest.mark.api
def test_create_character_for_session_invite_world_denied(
    test_client, test_db, temp_db_path, db_with_users
):
    """Invite-only worlds should deny self-create without explicit grants."""
    with use_test_database(temp_db_path):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
            VALUES (?, ?, '', 1, '{}')
            """,
            ("daily_undertaking", "daily_undertaking"),
        )
        conn.commit()
        conn.close()

        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]
        response = test_client.post(
            "/characters/create",
            json={"session_id": session_id, "world_id": "daily_undertaking"},
        )
        assert response.status_code == 403
        assert "invite" in response.json()["detail"].lower()


@pytest.mark.api
def test_create_character_for_session_respects_world_slot_limit(
    test_client, test_db, temp_db_path, db_with_users
):
    """Self-create should return 409 when world slot cap is exhausted."""
    original_slot_limit = config.character_creation.default_world_slot_limit
    original_world_overrides = dict(config.character_creation.world_policy_overrides)
    config.character_creation.default_world_slot_limit = 1
    config.character_creation.world_policy_overrides = {}
    try:
        with use_test_database(temp_db_path):
            login_response = test_client.post(
                "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
            )
            session_id = login_response.json()["session_id"]

            # testplayer already owns one seeded character in pipeworks_web.
            response = test_client.post(
                "/characters/create",
                json={"session_id": session_id, "world_id": "pipeworks_web"},
            )
            assert response.status_code == 409
            assert "slot" in response.json()["detail"].lower()
    finally:
        config.character_creation.default_world_slot_limit = original_slot_limit
        config.character_creation.world_policy_overrides = original_world_overrides


@pytest.mark.api
def test_create_character_for_session_disabled_by_policy(
    test_client, test_db, temp_db_path, db_with_users
):
    """Self-create endpoint should respect the global policy toggle."""
    original_enabled = config.character_creation.player_self_create_enabled
    config.character_creation.player_self_create_enabled = False
    try:
        with use_test_database(temp_db_path):
            login_response = test_client.post(
                "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
            )
            session_id = login_response.json()["session_id"]
            response = test_client.post(
                "/characters/create",
                json={"session_id": session_id, "world_id": "pipeworks_web"},
            )
            assert response.status_code == 403
            assert "disabled" in response.json()["detail"].lower()
    finally:
        config.character_creation.player_self_create_enabled = original_enabled


# ============================================================================
# PASSWORD CHANGE TESTS
# ============================================================================


@pytest.mark.api
def test_change_password_success(test_client, test_db, temp_db_path, db_with_users):
    """Test change-password updates the user's credentials."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]
        new_password = "VeryStrongPass!9"

        response = test_client.post(
            "/change-password",
            json={
                "session_id": session_id,
                "old_password": TEST_PASSWORD,
                "new_password": new_password,
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
def test_login_direct_create_character_failure(test_client, test_db, temp_db_path, db_with_users):
    """Deprecated login-direct should return migration guidance."""
    with use_test_database(temp_db_path):
        with patch.object(database, "create_character_for_user", return_value=False):
            response = test_client.post(
                "/login-direct",
                json={
                    "username": "testplayer",
                    "password": TEST_PASSWORD,
                    "world_id": "pipeworks_web",
                    "character_name": "new_char",
                    "create_character": True,
                },
            )

        assert_login_direct_deprecated(response)


@pytest.mark.api
def test_login_direct_set_session_character_failure(
    test_client, test_db, temp_db_path, db_with_users
):
    """Deprecated login-direct should return migration guidance."""
    with use_test_database(temp_db_path):
        with patch.object(database, "set_session_character", return_value=False):
            response = test_client.post(
                "/login-direct",
                json={
                    "username": "testplayer",
                    "password": TEST_PASSWORD,
                    "world_id": "pipeworks_web",
                    "character_name": "testplayer_char",
                },
            )

        assert_login_direct_deprecated(response)


@pytest.mark.api
def test_change_password_wrong_old(test_client, test_db, temp_db_path, db_with_users):
    """Test change-password rejects incorrect current password."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/change-password",
            json={
                "session_id": session_id,
                "old_password": "wrongpassword",
                "new_password": "NewPassword123!",
            },
        )

        assert response.status_code == 401


@pytest.mark.api
def test_change_password_same_as_old(test_client, test_db, temp_db_path, db_with_users):
    """Test change-password rejects same-as-old password."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/change-password",
            json={
                "session_id": session_id,
                "old_password": TEST_PASSWORD,
                "new_password": TEST_PASSWORD,
            },
        )

        assert response.status_code == 400


@pytest.mark.api
def test_change_password_policy_failure(test_client, test_db, temp_db_path, db_with_users):
    """Test change-password rejects weak new passwords."""
    with use_test_database(temp_db_path):
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login_response.json()["session_id"]

        response = test_client.post(
            "/change-password",
            json={
                "session_id": session_id,
                "old_password": TEST_PASSWORD,
                "new_password": "short",
            },
        )

        assert response.status_code == 400


# ============================================================================
# ADMIN USER CREATE TESTS
# ============================================================================


@pytest.mark.api
def test_admin_create_user_success(test_client, test_db, temp_db_path, db_with_users):
    """Admin can create player/worldbuilder accounts."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/user/create",
            json={
                "session_id": session_id,
                "username": "createduser",
                "role": "player",
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
def test_admin_create_user_invalid_role(test_client, test_db, temp_db_path, db_with_users):
    """Admin create user rejects invalid roles."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/user/create",
            json={
                "session_id": session_id,
                "username": "createduser",
                "role": "invalidrole",
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
            },
        )

        assert response.status_code == 400


@pytest.mark.api
def test_admin_create_user_forbidden_role(test_client, test_db, temp_db_path, db_with_users):
    """Admin cannot create other admins or superusers."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/user/create",
            json={
                "session_id": session_id,
                "username": "createdadmin",
                "role": "admin",
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
            },
        )

        assert response.status_code == 403


@pytest.mark.api
def test_admin_create_user_password_mismatch(test_client, test_db, temp_db_path, db_with_users):
    """Admin create user rejects mismatched passwords."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/user/create",
            json={
                "session_id": session_id,
                "username": "createduser",
                "role": "player",
                "password": TEST_PASSWORD,
                "password_confirm": "different123",
            },
        )

        assert response.status_code == 400


# ============================================================================
# ADMIN TABLE ROUTES TESTS
# ============================================================================


@pytest.mark.api
def test_admin_database_tables_and_rows(test_client, test_db, temp_db_path, db_with_users):
    """Admin tables endpoints return schema and rows."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        tables_resp = test_client.get("/admin/database/tables", params={"session_id": session_id})
        assert tables_resp.status_code == 200
        tables = tables_resp.json()["tables"]
        assert tables

        table_name = tables[0]["name"]
        rows_resp = test_client.get(
            f"/admin/database/table/{table_name}", params={"session_id": session_id}
        )
        assert rows_resp.status_code == 200


@pytest.mark.api
def test_admin_database_schema(test_client, test_db, temp_db_path, db_with_users):
    """Admin schema endpoint returns foreign key metadata."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        schema_resp = test_client.get("/admin/database/schema", params={"session_id": session_id})
        assert schema_resp.status_code == 200
        payload = schema_resp.json()
        assert payload["tables"]
        assert "name" in payload["tables"][0]


# ============================================================================
# OLLAMA ADMIN TESTS
# ============================================================================


@pytest.mark.api
def test_admin_ollama_list_models(test_client, test_db, temp_db_path, db_with_users):
    """Ollama list command should return available models."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "models": [
                        {"name": "llama3", "size": 1234, "modified_at": "2024-01-01"},
                    ]
                }

        with patch("requests.get", return_value=FakeResponse()):
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": session_id,
                    "server_url": "http://localhost:11434",
                    "command": "list",
                },
            )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
def test_admin_ollama_missing_args(test_client, test_db, temp_db_path, db_with_users):
    """Ollama command should reject missing server_url or command."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/ollama/command",
            json={"session_id": session_id, "server_url": "", "command": ""},
        )

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
def test_admin_ollama_unknown_command(test_client, test_db, temp_db_path, db_with_users):
    """Ollama unknown commands should return error output."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/ollama/command",
            json={
                "session_id": session_id,
                "server_url": "http://localhost:11434",
                "command": "unknown",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
def test_admin_ollama_ps(test_client, test_db, temp_db_path, db_with_users):
    """Ollama ps command should return running models."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"models": [{"name": "llama3"}]}

        with patch("requests.get", return_value=FakeResponse()):
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": session_id,
                    "server_url": "http://localhost:11434",
                    "command": "ps",
                },
            )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
def test_admin_ollama_show(test_client, test_db, temp_db_path, db_with_users):
    """Ollama show command should return model metadata."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"modelfile": "FROM llama3", "parameters": "temp=0.7"}

        with patch("requests.post", return_value=FakeResponse()):
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": session_id,
                    "server_url": "http://localhost:11434",
                    "command": "show llama3",
                },
            )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
def test_admin_ollama_pull(test_client, test_db, temp_db_path, db_with_users):
    """Ollama pull command should stream status updates."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        class FakeResponse:
            status_code = 200

            @staticmethod
            def iter_lines():
                return [
                    b'{"status": "downloading"}',
                    b'{"status": "done"}',
                ]

        with patch("requests.post", return_value=FakeResponse()):
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": session_id,
                    "server_url": "http://localhost:11434",
                    "command": "pull llama3",
                },
            )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
def test_admin_ollama_run_success(test_client, test_db, temp_db_path, db_with_users):
    """Ollama run command should return generated output."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"message": {"content": "Hello from model"}}

        with patch("requests.post", return_value=FakeResponse()):
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": session_id,
                    "server_url": "http://localhost:11434",
                    "command": "run llama3 Hello",
                },
            )

        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.api
def test_admin_ollama_run_error(test_client, test_db, temp_db_path, db_with_users):
    """Ollama run command should surface non-200 responses."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        class FakeResponse:
            status_code = 500
            text = "boom"

        with patch("requests.post", return_value=FakeResponse()):
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": session_id,
                    "server_url": "http://localhost:11434",
                    "command": "run llama3 Hello",
                },
            )

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
def test_admin_ollama_connection_error(test_client, test_db, temp_db_path, db_with_users):
    """Ollama command should handle connection errors."""
    import requests

    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": session_id,
                    "server_url": "http://localhost:11434",
                    "command": "list",
                },
            )

        assert response.status_code == 200
        assert response.json()["success"] is False


@pytest.mark.api
def test_admin_ollama_clear_context_no_history(test_client, test_db, temp_db_path, db_with_users):
    """Clearing context with no history should succeed."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/ollama/clear-context",
            json={"session_id": session_id},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


# ============================================================================
# ADMIN USER MANAGEMENT + STOP SERVER TESTS
# ============================================================================


@pytest.mark.api
def test_admin_manage_user_invalid_action(test_client, test_db, temp_db_path, db_with_users):
    """Manage user should reject invalid actions."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "target_username": "testplayer",
                "action": "nonsense",
            },
        )

        assert response.status_code == 400


@pytest.mark.api
def test_admin_manage_user_self_blocked(test_client, test_db, temp_db_path, db_with_users):
    """Manage user should block self-management actions."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "target_username": "testadmin",
                "action": "ban",
            },
        )

        assert response.status_code == 400


@pytest.mark.api
def test_admin_manage_user_insufficient_hierarchy(
    test_client, test_db, temp_db_path, db_with_users
):
    """Admin should not be able to manage other admins."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        response = test_client.post(
            "/admin/user/manage",
            json={
                "session_id": session_id,
                "target_username": "testsuperuser",
                "action": "ban",
            },
        )

        assert response.status_code == 403


@pytest.mark.api
def test_admin_stop_server_returns_success(test_client, test_db, temp_db_path, db_with_users):
    """Stop server should return a success response without killing tests."""
    with use_test_database(temp_db_path):
        admin_login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = admin_login.json()["session_id"]

        with patch("os.kill") as mock_kill, patch("asyncio.create_task") as create_task:
            response = test_client.post(
                "/admin/server/stop",
                json={"session_id": session_id},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        create_task.assert_called_once()
        mock_kill.assert_not_called()
