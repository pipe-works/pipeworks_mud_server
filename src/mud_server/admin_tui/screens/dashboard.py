"""
Dashboard screen for PipeWorks Admin TUI.

This module provides the main admin dashboard that displays server
status and provides quick access to administrative actions.

The DashboardScreen shows:
- Current server connection status
- Active player count
- Quick action buttons
- User session information
- User creation entry point (admin/superuser)
"""

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from mud_server.admin_tui.screens.create_user import CreateUserScreen
from mud_server.admin_tui.screens.database import DatabaseScreen


class DashboardScreen(Screen):
    """
    Main admin dashboard screen.

    Displays server status and provides administrative actions.
    Automatically refreshes status periodically.

    Key Bindings:
        r: Refresh server status
        d: View database tables (superuser only)
        u: Create user (admin or superuser)
        l: Logout
        q, ctrl+q: Quit application

    CSS Classes:
        .dashboard-container: Main content container.
        .status-panel: Server status display panel.
        .actions-panel: Quick actions button panel.
        .info-label: Status information labels.
        .info-value: Status information values.
    """

    # Key bindings for quick actions
    # Using Binding class with priority=True to ensure bindings work even when
    # child widgets (like Buttons) have focus
    BINDINGS = [
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("d", "view_database", "Database", priority=True),
        Binding("u", "create_user", "Create User", priority=True),
        Binding("l", "logout", "Logout", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
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
                        "Database", variant="primary", id="btn-database", classes="action-button"
                    )
                    yield Button(
                        "Create User",
                        variant="success",
                        id="btn-create-user",
                        classes="action-button",
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
        # Apply user-configured keybindings (if any).
        self._apply_keybindings()
        # Update user info from session
        self._update_user_info()
        # Start initial refresh
        self.refresh_status()

    def _apply_keybindings(self) -> None:
        """
        Capture user-configured keybindings for dashboard actions.

        We interpret configured keys in on_key to keep bindings scoped
        to this screen without mutating class-level BINDINGS.
        """
        bindings = getattr(self.app, "keybindings", None)
        if not bindings:
            return

        self._keybindings_by_key: dict[str, str] = {}
        for action, keys in bindings.bindings.items():
            if not hasattr(self, f"action_{action}"):
                continue
            for key in keys:
                self._keybindings_by_key.setdefault(key, action)

    def on_key(self, event: events.Key) -> None:
        """
        Handle user-configured keybindings for dashboard actions.

        If a key is configured for an action, invoke the matching
        action method and stop further propagation.
        """
        bindings_map = getattr(self, "_keybindings_by_key", {})
        action = bindings_map.get(event.key)
        if not action:
            return

        handler = getattr(self, f"action_{action}", None)
        if not handler:
            return

        handler()
        event.stop()

    def _update_user_info(self) -> None:
        """Update the user info display from session state."""
        api_client = self.app.api_client
        if api_client and api_client.session.is_authenticated:
            self.query_one("#user-name", Static).update(api_client.session.username or "Unknown")
            self.query_one("#user-role", Static).update(api_client.session.role or "Unknown")
        else:
            self.query_one("#user-name", Static).update("Not logged in")
            self.query_one("#user-role", Static).update("-")

    @work(thread=False)
    async def refresh_status(self) -> None:
        """
        Refresh server status from API.

        This is a background worker that fetches server health
        and updates the display. Uses @work decorator for async execution.
        """
        api_client = self.app.api_client
        config = self.app.config

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

    @on(Button.Pressed, "#btn-database")
    def handle_database_button(self) -> None:
        """Handle database button press."""
        self.action_view_database()

    @on(Button.Pressed, "#btn-logout")
    async def handle_logout_button(self) -> None:
        """Handle logout button press."""
        await self.action_logout()

    @on(Button.Pressed, "#btn-create-user")
    def handle_create_user_button(self) -> None:
        """Handle create user button press."""
        self.action_create_user()

    # -------------------------------------------------------------------------
    # Actions (Bound to Keys)
    # -------------------------------------------------------------------------

    def action_refresh(self) -> None:
        """Refresh server status (key: r)."""
        self.refresh_status()

    def action_view_database(self) -> None:
        """View database tables (key: d). Requires superuser privileges."""
        api_client = self.app.api_client
        if not api_client or not api_client.session.is_superuser:
            self.notify("Superuser access required to view database", severity="warning")
            return
        self.app.push_screen(DatabaseScreen())

    def action_create_user(self) -> None:
        """Create a new user account (key: u). Requires admin or superuser."""
        api_client = self.app.api_client
        if not api_client or not api_client.session.is_admin:
            self.notify("Admin access required to create users", severity="warning")
            return

        role = api_client.session.role or "player"
        if role == "admin":
            allowed_roles = ["player", "worldbuilder"]
        elif role == "superuser":
            allowed_roles = ["player", "worldbuilder", "admin", "superuser"]
        else:
            allowed_roles = []

        if not allowed_roles:
            self.notify("No roles available for your account", severity="warning")
            return

        self.app.push_screen(CreateUserScreen(allowed_roles=allowed_roles))

    async def action_logout(self) -> None:
        """Logout and return to login screen (key: l)."""
        await self.app.do_logout()

    def action_quit(self) -> None:
        """Quit the application (key: q)."""
        self.app.exit()
