"""
Main application module for PipeWorks Admin TUI.

This module defines the AdminApp class, which is the main Textual
application for the admin interface. It manages:
- Screen navigation (login -> dashboard)
- API client lifecycle
- Authentication flow

Entry Point:
    The main() function serves as the CLI entry point, configured
    in pyproject.toml as the "pipeworks-admin-tui" console script.

Example:
    # Run from command line
    pipeworks-admin-tui --server http://localhost:8000

    # Or programmatically
    from mud_server.admin_tui import AdminApp, Config

    config = Config.from_args()
    app = AdminApp(config)
    app.run()
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from textual.app import App
from textual.binding import Binding

from mud_server.admin_tui.api.client import AdminAPIClient
from mud_server.admin_tui.config import Config
from mud_server.admin_tui.keybindings import KeyBindings
from mud_server.admin_tui.screens.dashboard import DashboardScreen
from mud_server.admin_tui.screens.login import LoginScreen


class AdminApp(App):
    """
    Main Textual application for PipeWorks Admin TUI.

    This application provides a terminal-based interface for administering
    the MUD server. It handles authentication, displays server status,
    and provides administrative actions.

    Attributes:
        config: Application configuration (server URL, timeout).
        api_client: HTTP client for server communication. Created on mount.

    Lifecycle:
        1. on_mount: Creates API client, pushes LoginScreen
        2. do_login: Authenticates, switches to DashboardScreen
        3. do_logout: Clears session, returns to LoginScreen
        4. on_unmount: Closes API client

    Key Bindings (App-level):
        ctrl+c: Quit application (always available)
        ctrl+q: Quit application (always available)

    Example:
        config = Config(server_url="http://localhost:8000", timeout=30.0)
        app = AdminApp(config)
        app.run()
    """

    # Application metadata
    TITLE = "PipeWorks Admin"
    SUB_TITLE = "MUD Server Administration"

    # App-level bindings with priority=True ensure these work regardless of
    # which screen is active or which widget has focus
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True, show=False),
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
    ]

    # Default CSS for the application
    CSS = """
    Screen {
        background: $surface;
    }
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize the admin application.

        Args:
            config: Application configuration object.
        """
        super().__init__()
        self.config = config
        # Load keybindings once at startup to keep behavior consistent.
        self.keybindings = KeyBindings.load()
        self.api_client: AdminAPIClient | None = None

    async def on_mount(self) -> None:
        """
        Called when the application is mounted.

        Creates the API client and pushes the initial login screen.
        """
        # Create the API client (will be entered as context manager)
        self.api_client = AdminAPIClient(self.config)
        await self.api_client.__aenter__()

        # Start with login screen
        await self.push_screen(LoginScreen())

    async def on_unmount(self) -> None:
        """
        Called when the application is unmounted.

        Logs out from server (if authenticated) and closes the API client.
        This ensures the session is properly cleaned up on the server side,
        keeping the active player count accurate.
        """
        if self.api_client:
            # Logout from server if authenticated (clears server-side session)
            if self.api_client.session.is_authenticated:
                try:
                    await self.api_client.logout()
                except Exception:  # nosec B110 - best-effort logout on shutdown
                    # Ignore logout errors on shutdown (server may be unavailable)
                    pass
            # Close the HTTP client
            await self.api_client.__aexit__(None, None, None)
            self.api_client = None

    async def do_login(self, username: str, password: str) -> None:
        """
        Perform login and transition to dashboard.

        Called by LoginScreen when credentials are submitted.

        Args:
            username: The username to authenticate.
            password: The user's password.

        Raises:
            AuthenticationError: If login fails.
        """
        if not self.api_client:
            raise RuntimeError("API client not initialized")

        # Attempt login (raises on failure)
        await self.api_client.login(username, password)

        # Success - push dashboard on top of login screen
        self.push_screen(DashboardScreen())

    async def do_logout(self) -> None:
        """
        Perform logout and return to login screen.

        Called by DashboardScreen when user requests logout.
        """
        if self.api_client:
            await self.api_client.logout()

        # Pop back to login screen
        self.pop_screen()


def main(args: Sequence[str] | None = None) -> int:
    """
    Main entry point for the Admin TUI.

    Parses command-line arguments, creates the application,
    and runs the event loop.

    Args:
        args: Command-line arguments. If None, uses sys.argv[1:].

    Returns:
        Exit code (0 for success, non-zero for errors).

    Example:
        # Normal usage (reads sys.argv)
        sys.exit(main())

        # Testing
        main(["--server", "http://localhost:8000"])
    """
    try:
        # Parse configuration from command line
        config = Config.from_args(args)

        # Create and run the application
        app = AdminApp(config)
        app.run()

        return 0

    except KeyboardInterrupt:
        # User pressed Ctrl+C
        return 130

    except Exception as e:
        # Unexpected error
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
