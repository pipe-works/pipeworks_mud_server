"""
API client modules for PipeWorks Admin TUI.

This package contains the HTTP client implementation for communicating
with the MUD server API. It uses httpx for async HTTP requests.

The main class is AdminAPIClient, which provides methods for all
administrative operations supported by the server API.

Example:
    from mud_server.admin_tui.api import AdminAPIClient, APIError

    async with AdminAPIClient(config) as client:
        await client.login("admin", "password")
        players = await client.get_players()
"""

from mud_server.admin_tui.api.client import (
    AdminAPIClient,
    APIError,
    AuthenticationError,
    SessionState,
)

__all__ = [
    "AdminAPIClient",
    "APIError",
    "AuthenticationError",
    "SessionState",
]
