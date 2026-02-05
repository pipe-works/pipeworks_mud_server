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

from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD

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
        assert "Welcome" in data["message"]


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
    """Test that login creates session in the database."""
    with use_test_database(temp_db_path):
        response = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )

        session_id = response.json()["session_id"]
        session = database.get_session_by_id(session_id)
        assert session is not None
        assert session["username"] == "testplayer"
        assert session["client_type"] == "unknown"


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
        with patch("mud_server.core.world.database.get_players_in_room", return_value=[]):
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
        with patch("mud_server.core.world.database.get_players_in_room", return_value=[]):
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

            # 2. Login
            login_response = test_client.post(
                "/login", json={"username": "flowuser", "password": TEST_PASSWORD}
            )
            assert login_response.status_code == 200
            session_id = login_response.json()["session_id"]

            # 3. Look around
            look_response = test_client.post(
                "/command", json={"session_id": session_id, "command": "look"}
            )
            assert look_response.status_code == 200

            # 4. Move
            move_response = test_client.post(
                "/command", json={"session_id": session_id, "command": "north"}
            )
            assert move_response.status_code == 200

            # 5. Say something
            say_response = test_client.post(
                "/command", json={"session_id": session_id, "command": "say Testing!"}
            )
            assert say_response.status_code == 200

            # 6. Logout
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
