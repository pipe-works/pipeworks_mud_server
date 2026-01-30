"""
Dashboard screen for PipeWorks Admin TUI.

This module provides the main admin dashboard that displays server
status and provides quick access to administrative actions.

The DashboardScreen shows:
- Current server connection status
- Active player count
- Quick action buttons
- User session information
"""

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


class DashboardScreen(Screen):
    """
    Main admin dashboard screen.

    Displays server status and provides administrative actions.
    Automatically refreshes status periodically.

    Key Bindings:
        r: Refresh server status
        p: View players list
        s: View active sessions
        l: Logout
        q: Quit application

    CSS Classes:
        .dashboard-container: Main content container.
        .status-panel: Server status display panel.
        .actions-panel: Quick actions button panel.
        .info-label: Status information labels.
        .info-value: Status information values.
    """

    # Key bindings for quick actions
    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("p", "view_players", "Players"),
        ("s", "view_sessions", "Sessions"),
        ("l", "logout", "Logout"),
        ("q", "quit", "Quit"),
    ]

    CSS = """
    DashboardScreen {
        layout: vertical;
    }

    .dashboard-container {
        padding: 1 2;
    }

    .status-panel {
        border: solid green;
        padding: 1 2;
        height: auto;
        margin-bottom: 1;
    }

    .status-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    .status-row {
        height: 1;
    }

    .info-label {
        width: 20;
        color: $text-muted;
    }

    .info-value {
        color: $text;
    }

    .actions-panel {
        border: solid $primary;
        padding: 1 2;
        height: auto;
    }

    .actions-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    .action-buttons {
        height: 3;
    }

    .action-button {
        margin-right: 1;
    }

    .user-info {
        dock: bottom;
        height: 3;
        padding: 1 2;
        background: $surface;
        border-top: solid $primary-darken-2;
    }

    .user-label {
        color: $text-muted;
    }

    .user-value {
        color: $success;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        """
        Create the dashboard layout.

        Layout consists of:
        - Header with app title
        - Status panel showing server info
        - Actions panel with quick action buttons
        - User info bar at bottom
        - Footer with key bindings
        """
        yield Header()

        with Vertical(classes="dashboard-container"):
            # Server Status Panel
            with Vertical(classes="status-panel"):
                yield Static("Server Status", classes="status-title")
                with Horizontal(classes="status-row"):
                    yield Static("Server:", classes="info-label")
                    yield Static("...", id="server-url", classes="info-value")
                with Horizontal(classes="status-row"):
                    yield Static("Status:", classes="info-label")
                    yield Static("...", id="server-status", classes="info-value")
                with Horizontal(classes="status-row"):
                    yield Static("Active Players:", classes="info-label")
                    yield Static("...", id="active-players", classes="info-value")

            # Quick Actions Panel
            with Vertical(classes="actions-panel"):
                yield Static("Quick Actions", classes="actions-title")
                with Horizontal(classes="action-buttons"):
                    yield Button(
                        "Refresh", variant="default", id="btn-refresh", classes="action-button"
                    )
                    yield Button(
                        "Players", variant="primary", id="btn-players", classes="action-button"
                    )
                    yield Button(
                        "Sessions", variant="primary", id="btn-sessions", classes="action-button"
                    )
                    yield Button(
                        "Logout", variant="warning", id="btn-logout", classes="action-button"
                    )

        # User info bar
        with Horizontal(classes="user-info"):
            yield Static("Logged in as: ", classes="user-label")
            yield Static("...", id="user-name", classes="user-value")
            yield Static("  Role: ", classes="user-label")
            yield Static("...", id="user-role", classes="user-value")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize dashboard when mounted."""
        # Update user info from session
        self._update_user_info()
        # Start initial data refresh
        self.refresh_status()

    def _update_user_info(self) -> None:
        """Update the user info display from session state."""
        api_client = self.app.api_client  # type: ignore
        if api_client and api_client.session.is_authenticated:
            self.query_one("#user-name", Static).update(api_client.session.username or "Unknown")
            self.query_one("#user-role", Static).update(api_client.session.role or "Unknown")
        else:
            self.query_one("#user-name", Static).update("Not logged in")
            self.query_one("#user-role", Static).update("-")

    @work(exclusive=True)
    async def refresh_status(self) -> None:
        """
        Refresh server status from API.

        This is a background worker that fetches server health
        and updates the display. Uses @work decorator for async execution.
        """
        api_client = self.app.api_client  # type: ignore
        config = self.app.config  # type: ignore

        # Update server URL display
        self.query_one("#server-url", Static).update(config.server_url)

        try:
            health = await api_client.get_health()
            status = health.get("status", "unknown")
            players = health.get("active_players", 0)

            # Update status display
            if status == "ok":
                self.query_one("#server-status", Static).update("[green]Online[/green]")
            else:
                self.query_one("#server-status", Static).update(f"[yellow]{status}[/yellow]")

            self.query_one("#active-players", Static).update(str(players))

        except Exception as e:
            self.query_one("#server-status", Static).update(f"[red]Error: {e}[/red]")
            self.query_one("#active-players", Static).update("-")

    # -------------------------------------------------------------------------
    # Button Handlers
    # -------------------------------------------------------------------------

    @on(Button.Pressed, "#btn-refresh")
    def handle_refresh_button(self) -> None:
        """Handle refresh button press."""
        self.refresh_status()

    @on(Button.Pressed, "#btn-players")
    def handle_players_button(self) -> None:
        """Handle players button press."""
        self.action_view_players()

    @on(Button.Pressed, "#btn-sessions")
    def handle_sessions_button(self) -> None:
        """Handle sessions button press."""
        self.action_view_sessions()

    @on(Button.Pressed, "#btn-logout")
    async def handle_logout_button(self) -> None:
        """Handle logout button press."""
        await self.action_logout()

    # -------------------------------------------------------------------------
    # Actions (Bound to Keys)
    # -------------------------------------------------------------------------

    def action_refresh(self) -> None:
        """Refresh server status (key: r)."""
        self.refresh_status()

    def action_view_players(self) -> None:
        """View players list (key: p)."""
        # TODO: Implement players list screen
        self.notify("Players view not yet implemented", severity="information")

    def action_view_sessions(self) -> None:
        """View active sessions (key: s)."""
        # TODO: Implement sessions list screen
        self.notify("Sessions view not yet implemented", severity="information")

    async def action_logout(self) -> None:
        """Logout and return to login screen (key: l)."""
        await self.app.do_logout()  # type: ignore

    def action_quit(self) -> None:
        """Quit the application (key: q)."""
        self.app.exit()
