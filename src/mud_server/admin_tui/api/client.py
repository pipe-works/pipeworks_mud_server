"""
HTTP API client for PipeWorks MUD Server.

This module provides an async HTTP client for communicating with the
MUD server's REST API. It handles authentication, session management,
and all administrative operations.

The client is designed to be used as an async context manager to ensure
proper resource cleanup:

    async with AdminAPIClient(config) as client:
        await client.login("admin", "password")
        health = await client.get_health()

Key Features:
    - Async HTTP requests using httpx
    - Automatic session management
    - Custom exceptions for error handling
    - Type hints for all public methods
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from mud_server.admin_tui.config import Config

# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================


@dataclass
class APIError(Exception):
    """
    Exception raised when an API request fails.

    This exception is raised for any non-2xx response from the server,
    except for authentication-specific errors which raise AuthenticationError.

    Attributes:
        message: Human-readable error message.
        status_code: HTTP status code from the response.
        detail: Additional detail from the server response, if available.

    Example:
        try:
            await client.get_health()
        except APIError as e:
            print(f"API error {e.status_code}: {e.message}")
    """

    message: str
    status_code: int = 0
    detail: str = ""

    def __str__(self) -> str:
        """Return a formatted error message."""
        if self.detail:
            return f"{self.message}: {self.detail}"
        return self.message


class AuthenticationError(APIError):
    """
    Exception raised for authentication-related failures.

    This includes:
        - Invalid credentials (401)
        - Permission denied (403)
        - Session expired
        - Not authenticated when required

    Example:
        try:
            await client.login("admin", "wrong_password")
        except AuthenticationError as e:
            print(f"Login failed: {e.detail}")
    """

    pass


# =============================================================================
# SESSION STATE
# =============================================================================


@dataclass
class SessionState:
    """
    Tracks the current authentication session state.

    This dataclass maintains information about the current user session,
    including authentication status and user role. It is updated automatically
    by the AdminAPIClient during login/logout operations.

    Attributes:
        session_id: The session ID returned by the server after login.
                   None if not authenticated.
        username: The authenticated username. None if not authenticated.
        role: The user's role (e.g., "admin", "superuser", "player").
              None if not authenticated.

    Properties:
        is_authenticated: True if currently logged in with a valid session.
        is_admin: True if the user has admin or superuser role.
        is_superuser: True if the user has superuser role.

    Example:
        state = SessionState()
        print(state.is_authenticated)  # False

        state.session_id = "abc123"
        state.username = "admin"
        state.role = "admin"
        print(state.is_authenticated)  # True
        print(state.is_admin)  # True
    """

    session_id: str | None = None
    username: str | None = None
    role: str | None = None

    @property
    def is_authenticated(self) -> bool:
        """Check if we have an active session."""
        return self.session_id is not None

    @property
    def is_admin(self) -> bool:
        """Check if the user has admin privileges."""
        return self.role in ("admin", "superuser")

    @property
    def is_superuser(self) -> bool:
        """Check if the user has superuser privileges."""
        return self.role == "superuser"

    def clear(self) -> None:
        """Clear all session state (logout)."""
        self.session_id = None
        self.username = None
        self.role = None


# =============================================================================
# API CLIENT
# =============================================================================


@dataclass
class AdminAPIClient:
    """
    Async HTTP client for the MUD server admin API.

    This client handles all communication with the MUD server's REST API.
    It must be used as an async context manager to properly manage the
    underlying HTTP connection pool.

    Attributes:
        config: Configuration object with server URL and timeout settings.
        session: Current authentication session state.

    Example:
        config = Config(server_url="http://localhost:8000", timeout=30.0)

        async with AdminAPIClient(config) as client:
            # Login
            await client.login("admin", "password123")

            # Check server health
            health = await client.get_health()
            print(f"Active players: {health['active_players']}")

            # Get list of players (requires admin)
            players = await client.get_players()

            # Logout
            await client.logout()
    """

    config: Config
    session: SessionState = field(default_factory=SessionState)

    # Private attributes for the HTTP client
    _http_client: httpx.AsyncClient | None = field(default=None, repr=False)

    # -------------------------------------------------------------------------
    # Context Manager Protocol
    # -------------------------------------------------------------------------

    async def __aenter__(self) -> AdminAPIClient:
        """
        Enter the async context manager.

        Creates the underlying httpx.AsyncClient with configured timeout.

        Returns:
            self: The AdminAPIClient instance ready for use.
        """
        self._http_client = httpx.AsyncClient(
            base_url=self.config.server_url,
            timeout=self.config.timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Exit the async context manager.

        Closes the underlying HTTP client connection pool.
        """
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """
        Get the HTTP client, ensuring it's been initialized.

        Raises:
            RuntimeError: If accessed outside of async context manager.

        Returns:
            The underlying httpx.AsyncClient.
        """
        if self._http_client is None:
            raise RuntimeError(
                "AdminAPIClient must be used as an async context manager. "
                "Use 'async with AdminAPIClient(config) as client:'"
            )
        return self._http_client

    # -------------------------------------------------------------------------
    # Authentication Methods
    # -------------------------------------------------------------------------

    async def login(self, username: str, password: str) -> dict[str, Any]:
        """
        Authenticate with the MUD server.

        Sends credentials to the server and stores the session information
        on successful authentication.

        Args:
            username: The username to authenticate with.
            password: The user's password.

        Returns:
            dict: The server response containing session_id, role, and message.

        Raises:
            AuthenticationError: If credentials are invalid (401).
            APIError: If the server returns any other error.

        Example:
            try:
                result = await client.login("admin", "password123")
                print(f"Logged in as {result['role']}")
            except AuthenticationError:
                print("Invalid credentials")
        """
        try:
            response = await self.http_client.post(
                "/login",
                json={"username": username, "password": password},
                headers={"X-Client-Type": "tui"},
            )
        except Exception as e:
            raise APIError(
                message="Login failed",
                status_code=0,
                detail=f"Cannot connect to server at {self.config.server_url}: {e}",
            ) from e

        # Try to parse JSON response, handle non-JSON gracefully
        try:
            data = response.json()
        except Exception as e:
            # Response is not valid JSON (empty, HTML error page, etc.)
            raise APIError(
                message="Login failed",
                status_code=response.status_code,
                detail=f"Server returned invalid response (status {response.status_code}). "
                f"Check that the server is running at {self.config.server_url}",
            ) from e

        if response.status_code == 401:
            raise AuthenticationError(
                message="Authentication failed",
                status_code=401,
                detail=data.get("detail", "Invalid username or password"),
            )

        if response.status_code != 200:
            raise APIError(
                message="Login failed",
                status_code=response.status_code,
                detail=data.get("detail", "Unknown error"),
            )

        # Update session state
        self.session.session_id = data.get("session_id")
        self.session.username = username
        self.session.role = data.get("role", "player")

        return dict(data)

    async def logout(self) -> bool:
        """
        End the current session.

        Notifies the server of logout and clears local session state.
        The local state is always cleared, even if the server request fails.

        Returns:
            bool: True if logout was performed, False if not authenticated.

        Example:
            if await client.logout():
                print("Logged out successfully")
            else:
                print("Was not logged in")
        """
        if not self.session.is_authenticated:
            return False

        try:
            # Attempt to notify the server of logout
            # This is a best-effort operation - the server will clean up
            # stale sessions eventually even if this request fails
            await self.http_client.post(
                "/logout",
                json={"session_id": self.session.session_id},
            )
        except Exception:  # noqa: S110  # nosec B110
            # Intentionally catching all exceptions and ignoring them.
            #
            # We don't care if the server-side logout fails because:
            # 1. The server has session cleanup mechanisms (cleanup_expired_sessions)
            # 2. The user's intent is to end their local session
            # 3. Network errors, timeouts, or server downtime shouldn't prevent
            #    local logout from completing
            #
            # The pass is intentional (S110/B110 security warnings suppressed):
            # - S110 (bandit): try-except-pass considered bad practice - but here
            #   it's the correct behavior for graceful degradation
            # - B110 (ruff): same as S110
            #
            # Common exception scenarios this handles:
            # - httpx.ConnectError: Server is down or unreachable
            # - httpx.TimeoutException: Server took too long to respond
            # - httpx.HTTPStatusError: Server returned error status (4xx/5xx)
            pass
        finally:
            # Always clear local state, regardless of server response
            # This ensures the client can log in again with fresh credentials
            self.session.clear()

        return True

    # -------------------------------------------------------------------------
    # Health & Status Methods
    # -------------------------------------------------------------------------

    async def get_health(self) -> dict[str, Any]:
        """
        Get server health status.

        This endpoint is public and does not require authentication.

        Returns:
            dict: Server health information including:
                - status: "ok" if healthy
                - active_players: Number of currently connected players

        Raises:
            APIError: If the server returns an error.

        Example:
            health = await client.get_health()
            if health["status"] == "ok":
                print(f"{health['active_players']} players online")
        """
        try:
            response = await self.http_client.get("/health")
        except Exception as e:
            raise APIError(
                message="Health check failed",
                status_code=0,
                detail=f"Cannot connect to server at {self.config.server_url}: {e}",
            ) from e

        # Try to parse JSON response
        try:
            data = response.json()
        except Exception as e:
            raise APIError(
                message="Health check failed",
                status_code=response.status_code,
                detail=f"Server returned invalid response (status {response.status_code})",
            ) from e

        if response.status_code != 200:
            raise APIError(
                message="Health check failed",
                status_code=response.status_code,
                detail=data.get("detail", "Server error"),
            )

        return dict(data)

    # -------------------------------------------------------------------------
    # Admin Methods (Require Authentication)
    # -------------------------------------------------------------------------

    def _require_auth(self) -> None:
        """
        Verify that we have an active session.

        Raises:
            AuthenticationError: If not currently authenticated.
        """
        if not self.session.is_authenticated:
            raise AuthenticationError(
                message="Not authenticated",
                status_code=401,
                detail="You must be logged in to perform this action",
            )

    async def get_players(self) -> list[dict[str, Any]]:
        """
        Get list of all players in the database.

        Requires admin privileges.

        Returns:
            list: List of player dictionaries with username, role, etc.

        Raises:
            AuthenticationError: If not authenticated or lacks permission.
            APIError: If the server returns an error.

        Example:
            players = await client.get_players()
            for player in players:
                print(f"{player['username']} ({player['role']})")
        """
        self._require_auth()

        response = await self.http_client.get(
            "/admin/database/players",
            params={"session_id": self.session.session_id},
        )

        if response.status_code == 403:
            raise AuthenticationError(
                message="Permission denied",
                status_code=403,
                detail="Admin privileges required",
            )

        if response.status_code != 200:
            data = response.json()
            raise APIError(
                message="Failed to get players",
                status_code=response.status_code,
                detail=data.get("detail", "Unknown error"),
            )

        data = response.json()
        return list(data.get("players", []))

    async def get_sessions(self) -> list[dict[str, Any]]:
        """
        Get list of active sessions.

        Requires admin privileges.

        Returns:
            list: List of session dictionaries with username, created_at, etc.

        Raises:
            AuthenticationError: If not authenticated or lacks permission.
            APIError: If the server returns an error.

        Example:
            sessions = await client.get_sessions()
            print(f"{len(sessions)} active sessions")
        """
        self._require_auth()

        response = await self.http_client.get(
            "/admin/database/sessions",
            params={"session_id": self.session.session_id},
        )

        if response.status_code == 403:
            raise AuthenticationError(
                message="Permission denied",
                status_code=403,
                detail="Admin privileges required",
            )

        if response.status_code != 200:
            data = response.json()
            raise APIError(
                message="Failed to get sessions",
                status_code=response.status_code,
                detail=data.get("detail", "Unknown error"),
            )

        data = response.json()
        return list(data.get("sessions", []))

    async def get_chat_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get recent chat messages from the database.

        Requires admin privileges.

        Args:
            limit: Maximum number of messages to return (default 100).

        Returns:
            list: List of chat message dictionaries with username, message, etc.

        Raises:
            AuthenticationError: If not authenticated or lacks permission.
            APIError: If the server returns an error.

        Example:
            messages = await client.get_chat_messages(limit=50)
            for msg in messages:
                print(f"{msg['username']}: {msg['message']}")
        """
        self._require_auth()

        response = await self.http_client.get(
            "/admin/database/chat-messages",
            params={"session_id": self.session.session_id, "limit": limit},
        )

        if response.status_code == 403:
            raise AuthenticationError(
                message="Permission denied",
                status_code=403,
                detail="Admin privileges required",
            )

        if response.status_code != 200:
            data = response.json()
            raise APIError(
                message="Failed to get chat messages",
                status_code=response.status_code,
                detail=data.get("detail", "Unknown error"),
            )

        data = response.json()
        return list(data.get("messages", []))

    async def get_tables(self) -> list[dict[str, Any]]:
        """
        Get list of database tables with schema metadata.

        Requires admin privileges.

        Returns:
            list: List of table metadata dictionaries with name, columns, row_count.

        Raises:
            AuthenticationError: If not authenticated or lacks permission.
            APIError: If the server returns an error.
        """
        self._require_auth()

        response = await self.http_client.get(
            "/admin/database/tables",
            params={"session_id": self.session.session_id},
        )

        if response.status_code == 403:
            raise AuthenticationError(
                message="Permission denied",
                status_code=403,
                detail="Admin privileges required",
            )

        if response.status_code != 200:
            data = response.json()
            raise APIError(
                message="Failed to get database tables",
                status_code=response.status_code,
                detail=data.get("detail", "Unknown error"),
            )

        data = response.json()
        return list(data.get("tables", []))

    async def get_table_rows(self, table_name: str, limit: int = 100) -> dict[str, Any]:
        """
        Get rows and columns for a specific database table.

        Requires admin privileges.

        Args:
            table_name: Table name to query.
            limit: Max number of rows to return.

        Returns:
            dict: Contains table, columns, and rows.

        Raises:
            AuthenticationError: If not authenticated or lacks permission.
            APIError: If the server returns an error.
        """
        self._require_auth()

        response = await self.http_client.get(
            f"/admin/database/table/{table_name}",
            params={"session_id": self.session.session_id, "limit": limit},
        )

        if response.status_code == 403:
            raise AuthenticationError(
                message="Permission denied",
                status_code=403,
                detail="Admin privileges required",
            )

        if response.status_code != 200:
            error_data = response.json()
            raise APIError(
                message=f"Failed to get table '{table_name}'",
                status_code=response.status_code,
                detail=error_data.get("detail", "Unknown error"),
            )

        data = cast(dict[str, Any], response.json())
        return data

    async def get_player_locations(self) -> list[dict[str, Any]]:
        """
        Get player locations with zone context for admin display.

        Requires admin privileges.

        Returns:
            list: List of player location dictionaries.

        Raises:
            AuthenticationError: If not authenticated or lacks permission.
            APIError: If the server returns an error.
        """
        self._require_auth()

        response = await self.http_client.get(
            "/admin/database/player-locations",
            params={"session_id": self.session.session_id},
        )

        if response.status_code == 403:
            raise AuthenticationError(
                message="Permission denied",
                status_code=403,
                detail="Admin privileges required",
            )

        if response.status_code != 200:
            error_data = response.json()
            raise APIError(
                message="Failed to get player locations",
                status_code=response.status_code,
                detail=error_data.get("detail", "Unknown error"),
            )

        data = cast(dict[str, Any], response.json())
        return list(data.get("locations", []))

    async def get_connections(self) -> list[dict[str, Any]]:
        """
        Get active session connections with activity age.

        Requires admin privileges.

        Returns:
            list: List of connection dictionaries.

        Raises:
            AuthenticationError: If not authenticated or lacks permission.
            APIError: If the server returns an error.
        """
        self._require_auth()

        response = await self.http_client.get(
            "/admin/database/connections",
            params={"session_id": self.session.session_id},
        )

        if response.status_code == 403:
            raise AuthenticationError(
                message="Permission denied",
                status_code=403,
                detail="Admin privileges required",
            )

        if response.status_code != 200:
            error_data = response.json()
            raise APIError(
                message="Failed to get connections",
                status_code=response.status_code,
                detail=error_data.get("detail", "Unknown error"),
            )

        data = cast(dict[str, Any], response.json())
        return list(data.get("connections", []))

    async def kick_session(
        self, target_session_id: str, reason: str | None = None
    ) -> dict[str, Any]:
        """
        Force-disconnect a session (admin/superuser only).

        Args:
            target_session_id: Session id to disconnect.
            reason: Optional reason for the action.

        Returns:
            dict: Response payload with success/message.
        """
        self._require_auth()

        response = await self.http_client.post(
            "/admin/session/kick",
            json={
                "session_id": self.session.session_id,
                "target_session_id": target_session_id,
                "reason": reason,
            },
        )

        if response.status_code == 403:
            raise AuthenticationError(
                message="Permission denied",
                status_code=403,
                detail="Admin privileges required",
            )

        if response.status_code != 200:
            error_data = response.json()
            raise APIError(
                message="Failed to kick session",
                status_code=response.status_code,
                detail=error_data.get("detail", "Unknown error"),
            )

        return cast(dict[str, Any], response.json())
