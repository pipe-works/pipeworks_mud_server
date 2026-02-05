"""
Tests for API client module.

This module tests the AdminAPIClient class, including authentication,
session management, and API operations. Uses respx for mocking HTTP requests.
"""

from collections.abc import AsyncGenerator

import pytest
import respx
from httpx import Response

from mud_server.admin_tui.api.client import (
    AdminAPIClient,
    APIError,
    AuthenticationError,
    SessionState,
)
from mud_server.admin_tui.config import Config

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def config() -> Config:
    """Create a test configuration."""
    return Config(server_url="http://test-server:8000", timeout=10.0)


@pytest.fixture
async def client(config: Config) -> AsyncGenerator[AdminAPIClient, None]:
    """Create an API client for testing."""
    async with AdminAPIClient(config) as client:
        yield client


# =============================================================================
# SESSION STATE TESTS
# =============================================================================


class TestSessionState:
    """Tests for SessionState dataclass."""

    def test_initial_state_not_authenticated(self):
        """Test that initial state is not authenticated."""
        state = SessionState()

        assert state.session_id is None
        assert state.username is None
        assert state.role is None
        assert state.is_authenticated is False
        assert state.is_admin is False
        assert state.is_superuser is False

    def test_authenticated_state(self):
        """Test authenticated session state."""
        state = SessionState(
            session_id="abc123",
            username="admin",
            role="admin",
        )

        assert state.is_authenticated is True
        assert state.is_admin is True
        assert state.is_superuser is False

    def test_superuser_state(self):
        """Test superuser session state."""
        state = SessionState(
            session_id="abc123",
            username="superadmin",
            role="superuser",
        )

        assert state.is_authenticated is True
        assert state.is_admin is True  # Superuser is also admin
        assert state.is_superuser is True

    def test_player_not_admin(self):
        """Test that player role is not admin."""
        state = SessionState(
            session_id="abc123",
            username="player1",
            role="player",
        )

        assert state.is_authenticated is True
        assert state.is_admin is False
        assert state.is_superuser is False

    def test_clear_state(self):
        """Test clearing session state."""
        state = SessionState(
            session_id="abc123",
            username="admin",
            role="admin",
        )

        state.clear()

        assert state.session_id is None
        assert state.username is None
        assert state.role is None
        assert state.is_authenticated is False


# =============================================================================
# API CLIENT INITIALIZATION TESTS
# =============================================================================


class TestAdminAPIClientInit:
    """Tests for AdminAPIClient initialization."""

    def test_client_requires_context_manager(self, config: Config):
        """Test that client must be used as context manager."""
        client = AdminAPIClient(config)

        with pytest.raises(RuntimeError, match="async context manager"):
            _ = client.http_client

    @pytest.mark.asyncio
    async def test_client_context_manager(self, config: Config):
        """Test client works as async context manager."""
        async with AdminAPIClient(config) as client:
            # Should not raise
            assert client.http_client is not None

    @pytest.mark.asyncio
    async def test_client_has_initial_session_state(self, client: AdminAPIClient):
        """Test client has initial unauthenticated session state."""
        assert client.session.is_authenticated is False


# =============================================================================
# LOGIN TESTS
# =============================================================================


class TestAdminAPIClientLogin:
    """Tests for login functionality."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_login(self, client: AdminAPIClient):
        """Test successful login updates session state."""
        # Mock successful login response
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={
                    "message": "Welcome, admin!",
                    "session_id": "test-session-123",
                    "role": "admin",
                },
            )
        )

        result = await client.login("admin", "password123")

        # Check response
        assert result["message"] == "Welcome, admin!"
        assert result["session_id"] == "test-session-123"
        assert result["role"] == "admin"

        # Check session state updated
        assert client.session.is_authenticated is True
        assert client.session.session_id == "test-session-123"
        assert client.session.username == "admin"
        assert client.session.role == "admin"

    @pytest.mark.asyncio
    @respx.mock
    async def test_login_invalid_credentials(self, client: AdminAPIClient):
        """Test login with invalid credentials raises AuthenticationError."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                401,
                json={"detail": "Invalid username or password"},
            )
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await client.login("admin", "wrongpassword")

        assert exc_info.value.status_code == 401
        assert "Invalid username or password" in exc_info.value.detail

        # Session should remain unauthenticated
        assert client.session.is_authenticated is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_login_server_error(self, client: AdminAPIClient):
        """Test login with server error raises APIError."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                500,
                json={"detail": "Internal server error"},
            )
        )

        with pytest.raises(APIError) as exc_info:
            await client.login("admin", "password123")

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @respx.mock
    async def test_login_default_role(self, client: AdminAPIClient):
        """Test login defaults to player role if not specified."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={
                    "message": "Welcome!",
                    "session_id": "test-session-123",
                    # No role specified
                },
            )
        )

        await client.login("player", "password123")

        assert client.session.role == "player"


# =============================================================================
# LOGOUT TESTS
# =============================================================================


class TestAdminAPIClientLogout:
    """Tests for logout functionality."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_logout(self, client: AdminAPIClient):
        """Test successful logout clears session state."""
        # First login
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        # Mock logout
        respx.post("http://test-server:8000/logout").mock(
            return_value=Response(200, json={"message": "Logged out"})
        )

        result = await client.logout()

        assert result is True
        assert client.session.is_authenticated is False

    @pytest.mark.asyncio
    async def test_logout_when_not_authenticated(self, client: AdminAPIClient):
        """Test logout when not authenticated returns False."""
        result = await client.logout()

        assert result is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_logout_clears_state_even_on_error(self, client: AdminAPIClient):
        """Test logout clears local state even if server request fails."""
        # First login
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        # Mock logout failure
        respx.post("http://test-server:8000/logout").mock(
            return_value=Response(500, json={"detail": "Server error"})
        )

        result = await client.logout()

        # Should still return True and clear local state
        assert result is True
        assert client.session.is_authenticated is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_logout_handles_network_exception(self, client: AdminAPIClient):
        """Test logout handles network exceptions gracefully.

        This tests the exception handling path in logout() where the HTTP
        request fails with a network error (e.g., connection refused, timeout).
        The local session should still be cleared even when the server is unreachable.
        """
        # First login
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        # Verify we're authenticated
        assert client.session.is_authenticated is True

        # Mock logout to raise a network exception
        import httpx

        respx.post("http://test-server:8000/logout").mock(side_effect=httpx.ConnectError)

        # Logout should still succeed (clearing local state)
        result = await client.logout()

        # Should return True and clear local state despite the exception
        assert result is True
        assert client.session.is_authenticated is False
        assert client.session.session_id is None  # type: ignore[unreachable]
        assert client.session.username is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_logout_handles_timeout_exception(self, client: AdminAPIClient):
        """Test logout handles timeout exceptions gracefully.

        The try/except/pass in logout is intentional - we don't want network
        issues to prevent local session cleanup. This test ensures that
        timeout errors are caught and local state is cleared.
        """
        # First login
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "superuser"},
            )
        )
        await client.login("admin", "password")

        # Mock logout to raise a timeout exception
        import httpx

        respx.post("http://test-server:8000/logout").mock(side_effect=httpx.TimeoutException)

        # Logout should still succeed
        result = await client.logout()

        assert result is True
        assert client.session.is_authenticated is False


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================


class TestAdminAPIClientHealth:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_health_success(self, client: AdminAPIClient):
        """Test successful health check."""
        respx.get("http://test-server:8000/health").mock(
            return_value=Response(
                200,
                json={"status": "ok", "active_players": 5},
            )
        )

        health = await client.get_health()

        assert health["status"] == "ok"
        assert health["active_players"] == 5

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_health_server_down(self, client: AdminAPIClient):
        """Test health check when server returns error."""
        respx.get("http://test-server:8000/health").mock(
            return_value=Response(503, json={"detail": "Service unavailable"})
        )

        with pytest.raises(APIError) as exc_info:
            await client.get_health()

        assert exc_info.value.status_code == 503


# =============================================================================
# AUTHENTICATION REQUIRED TESTS
# =============================================================================


class TestAdminAPIClientAuthRequired:
    """Tests for methods that require authentication."""

    @pytest.mark.asyncio
    async def test_get_players_requires_auth(self, client: AdminAPIClient):
        """Test get_players raises error when not authenticated."""
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            await client.get_players()

    @pytest.mark.asyncio
    async def test_get_sessions_requires_auth(self, client: AdminAPIClient):
        """Test get_sessions raises error when not authenticated."""
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            await client.get_sessions()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_players_permission_denied(self, client: AdminAPIClient):
        """Test get_players with insufficient permissions."""
        # Login as player (not admin)
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "player"},
            )
        )
        await client.login("player", "password")

        # Mock permission denied response
        respx.get("http://test-server:8000/admin/database/players").mock(
            return_value=Response(403, json={"detail": "Forbidden"})
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await client.get_players()

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_players_success(self, client: AdminAPIClient):
        """Test successful get_players call."""
        # Login as admin
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        # Mock players response
        respx.get("http://test-server:8000/admin/database/players").mock(
            return_value=Response(
                200,
                json={
                    "players": [
                        {"username": "player1", "role": "player"},
                        {"username": "admin", "role": "admin"},
                    ]
                },
            )
        )

        players = await client.get_players()

        assert len(players) == 2
        assert players[0]["username"] == "player1"

    @pytest.mark.asyncio
    async def test_get_chat_messages_requires_auth(self, client: AdminAPIClient):
        """Test get_chat_messages raises error when not authenticated."""
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            await client.get_chat_messages()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_chat_messages_permission_denied(self, client: AdminAPIClient):
        """Test get_chat_messages with insufficient permissions."""
        # Login as player (not admin)
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "player"},
            )
        )
        await client.login("player", "password")

        # Mock permission denied response
        respx.get("http://test-server:8000/admin/database/chat-messages").mock(
            return_value=Response(403, json={"detail": "Forbidden"})
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await client.get_chat_messages()

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_chat_messages_success(self, client: AdminAPIClient):
        """Test successful get_chat_messages call."""
        # Login as admin
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        # Mock chat messages response
        respx.get("http://test-server:8000/admin/database/chat-messages").mock(
            return_value=Response(
                200,
                json={
                    "messages": [
                        {"username": "player1", "message": "Hello", "room": "spawn"},
                        {"username": "player2", "message": "Hi there", "room": "spawn"},
                    ]
                },
            )
        )

        messages = await client.get_chat_messages()

        assert len(messages) == 2
        assert messages[0]["username"] == "player1"
        assert messages[0]["message"] == "Hello"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_chat_messages_with_limit(self, client: AdminAPIClient):
        """Test get_chat_messages respects limit parameter."""
        # Login as admin
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        # Mock chat messages response - verify limit is passed in params
        route = respx.get("http://test-server:8000/admin/database/chat-messages").mock(
            return_value=Response(
                200,
                json={"messages": [{"username": "player1", "message": "Test"}]},
            )
        )

        await client.get_chat_messages(limit=50)

        # Verify the request was made with correct params
        assert route.called
        assert "limit=50" in str(route.calls[0].request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_chat_messages_server_error(self, client: AdminAPIClient):
        """Test get_chat_messages handles server errors."""
        # Login as admin
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        # Mock server error response
        respx.get("http://test-server:8000/admin/database/chat-messages").mock(
            return_value=Response(500, json={"detail": "Internal server error"})
        )

        with pytest.raises(APIError) as exc_info:
            await client.get_chat_messages()

        assert exc_info.value.status_code == 500
        assert "Failed to get chat messages" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_tables_requires_auth(self, client: AdminAPIClient):
        """Test get_tables raises error when not authenticated."""
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            await client.get_tables()

    @pytest.mark.asyncio
    async def test_get_table_rows_requires_auth(self, client: AdminAPIClient):
        """Test get_table_rows raises error when not authenticated."""
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            await client.get_table_rows("players")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_tables_permission_denied(self, client: AdminAPIClient):
        """Test get_tables with insufficient permissions."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "player"},
            )
        )
        await client.login("player", "password")

        respx.get("http://test-server:8000/admin/database/tables").mock(
            return_value=Response(403, json={"detail": "Forbidden"})
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await client.get_tables()

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_tables_success(self, client: AdminAPIClient):
        """Test successful get_tables call."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        respx.get("http://test-server:8000/admin/database/tables").mock(
            return_value=Response(
                200,
                json={
                    "tables": [
                        {"name": "players", "columns": ["id"], "row_count": 1},
                        {"name": "sessions", "columns": ["id"], "row_count": 0},
                    ]
                },
            )
        )

        tables = await client.get_tables()

        assert len(tables) == 2
        assert tables[0]["name"] == "players"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_tables_server_error(self, client: AdminAPIClient):
        """Test get_tables handles server errors."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        respx.get("http://test-server:8000/admin/database/tables").mock(
            return_value=Response(500, json={"detail": "Internal server error"})
        )

        with pytest.raises(APIError) as exc_info:
            await client.get_tables()

        assert exc_info.value.status_code == 500
        assert "Failed to get database tables" in exc_info.value.message

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_table_rows_success(self, client: AdminAPIClient):
        """Test successful get_table_rows call."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        respx.get("http://test-server:8000/admin/database/table/players").mock(
            return_value=Response(
                200,
                json={
                    "table": "players",
                    "columns": ["id", "username"],
                    "rows": [[1, "player1"]],
                },
            )
        )

        result = await client.get_table_rows("players")

        assert result["table"] == "players"
        assert result["columns"] == ["id", "username"]
        assert result["rows"][0][1] == "player1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_table_rows_server_error(self, client: AdminAPIClient):
        """Test get_table_rows handles server errors."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        respx.get("http://test-server:8000/admin/database/table/players").mock(
            return_value=Response(500, json={"detail": "Internal server error"})
        )

        with pytest.raises(APIError) as exc_info:
            await client.get_table_rows("players")

        assert exc_info.value.status_code == 500
        assert "Failed to get table" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_player_locations_requires_auth(self, client: AdminAPIClient):
        """Test get_player_locations raises error when not authenticated."""
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            await client.get_player_locations()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_player_locations_permission_denied(self, client: AdminAPIClient):
        """Test get_player_locations with insufficient permissions."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "player"},
            )
        )
        await client.login("player", "password")

        respx.get("http://test-server:8000/admin/database/player-locations").mock(
            return_value=Response(403, json={"detail": "Forbidden"})
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await client.get_player_locations()

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_player_locations_success(self, client: AdminAPIClient):
        """Test successful get_player_locations call."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        respx.get("http://test-server:8000/admin/database/player-locations").mock(
            return_value=Response(
                200,
                json={
                    "locations": [
                        {
                            "player_id": 1,
                            "username": "player1",
                            "zone_id": "ledgerfall_alley",
                            "room_id": "spawn",
                            "updated_at": "2026-02-05 12:00:00",
                        }
                    ]
                },
            )
        )

        locations = await client.get_player_locations()

        assert len(locations) == 1
        assert locations[0]["username"] == "player1"
        assert locations[0]["zone_id"] == "ledgerfall_alley"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_player_locations_server_error(self, client: AdminAPIClient):
        """Test get_player_locations handles server errors."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        respx.get("http://test-server:8000/admin/database/player-locations").mock(
            return_value=Response(500, json={"detail": "Internal server error"})
        )

        with pytest.raises(APIError) as exc_info:
            await client.get_player_locations()

        assert exc_info.value.status_code == 500
        assert "Failed to get player locations" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_connections_requires_auth(self, client: AdminAPIClient):
        """Test get_connections raises error when not authenticated."""
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            await client.get_connections()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_connections_permission_denied(self, client: AdminAPIClient):
        """Test get_connections with insufficient permissions."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "player"},
            )
        )
        await client.login("player", "password")

        respx.get("http://test-server:8000/admin/database/connections").mock(
            return_value=Response(403, json={"detail": "Forbidden"})
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await client.get_connections()

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_connections_success(self, client: AdminAPIClient):
        """Test successful get_connections call."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        respx.get("http://test-server:8000/admin/database/connections").mock(
            return_value=Response(
                200,
                json={
                    "connections": [
                        {
                            "username": "player1",
                            "session_id": "session-1",
                            "last_activity": "2026-02-05 12:00:00",
                            "age_seconds": 30,
                        }
                    ]
                },
            )
        )

        connections = await client.get_connections()

        assert connections[0]["session_id"] == "session-1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_connections_server_error(self, client: AdminAPIClient):
        """Test get_connections handles server errors."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "test-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        respx.get("http://test-server:8000/admin/database/connections").mock(
            return_value=Response(500, json={"detail": "Internal server error"})
        )

        with pytest.raises(APIError) as exc_info:
            await client.get_connections()

        assert exc_info.value.status_code == 500
        assert "Failed to get connections" in exc_info.value.message

    @pytest.mark.asyncio
    @respx.mock
    async def test_kick_session_success(self, client: AdminAPIClient):
        """Test successful kick_session call."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "admin-session", "role": "admin"},
            )
        )
        await client.login("admin", "password")

        respx.post("http://test-server:8000/admin/session/kick").mock(
            return_value=Response(200, json={"success": True, "message": "Session disconnected"})
        )

        result = await client.kick_session("session-1")

        assert result["success"] is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_kick_session_permission_denied(self, client: AdminAPIClient):
        """Test kick_session with insufficient permissions."""
        respx.post("http://test-server:8000/login").mock(
            return_value=Response(
                200,
                json={"session_id": "player-session", "role": "player"},
            )
        )
        await client.login("player", "password")

        respx.post("http://test-server:8000/admin/session/kick").mock(
            return_value=Response(403, json={"detail": "Forbidden"})
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await client.kick_session("session-1")

        assert exc_info.value.status_code == 403
