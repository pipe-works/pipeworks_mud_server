"""
Database viewer screen for PipeWorks Admin TUI.

This module provides a database viewing interface that allows superusers
to view the contents of various database tables (players, sessions, chat).

The DatabaseScreen shows:
- Tabbed interface for different tables
- DataTable widgets for viewing records
- Refresh functionality for each table
"""

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, TabbedContent, TabPane

from mud_server.admin_tui.api.client import AuthenticationError


class DatabaseScreen(Screen):
    """
    Database viewer screen for superusers.

    Displays database tables in a tabbed interface with DataTable widgets.
    Allows viewing of players, sessions, and chat messages.

    Key Bindings:
        r: Refresh current table
        b: Go back to dashboard
        q, ctrl+q: Quit application

    CSS Classes:
        .database-container: Main content container.
        .table-container: Container for each table tab.
        .table-header: Header row styling for tables.
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("b", "back", "Back", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
    ]

    CSS = """
    DatabaseScreen {
        layout: vertical;
    }

    .database-container {
        padding: 1 2;
    }

    .table-container {
        height: 100%;
        border: solid $primary;
    }

    .error-message {
        color: $error;
        padding: 1 2;
        text-align: center;
    }

    .loading-message {
        color: $text-muted;
        padding: 1 2;
        text-align: center;
    }

    DataTable {
        height: 100%;
    }

    DataTable > .datatable--header {
        text-style: bold;
        background: $primary;
    }

    .action-bar {
        height: 3;
        padding: 0 1;
        background: $surface;
        border-bottom: solid $primary-darken-2;
    }

    .action-button {
        margin-right: 1;
    }

    TabbedContent {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the database viewer layout."""
        yield Header()

        with Vertical(classes="database-container"):
            # Action bar
            with Vertical(classes="action-bar"):
                yield Button("← Back", variant="default", id="btn-back", classes="action-button")

            # Tabbed content for different tables
            with TabbedContent(id="table-tabs"):
                with TabPane("Players", id="tab-players"):
                    yield DataTable(id="table-players")

                with TabPane("Sessions", id="tab-sessions"):
                    yield DataTable(id="table-sessions")

                with TabPane("Chat Messages", id="tab-chat"):
                    yield DataTable(id="table-chat")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize the database viewer."""
        # Check permissions
        api_client = self.app.api_client
        if not api_client or not api_client.session.is_superuser:
            self.notify("Superuser access required", severity="error")
            self.app.pop_screen()
            return

        # Set up tables
        self._setup_players_table()
        self._setup_sessions_table()
        self._setup_chat_table()

        # Load initial data
        self._load_players()
        self._load_sessions()
        self._load_chat_messages()

    def _setup_players_table(self) -> None:
        """Configure the players DataTable columns."""
        table = self.query_one("#table-players", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "ID",
            "Username",
            "Role",
            "Room",
            "Active",
            "Created",
            "Last Login",
        )

    def _setup_sessions_table(self) -> None:
        """Configure the sessions DataTable columns."""
        table = self.query_one("#table-sessions", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "ID",
            "Username",
            "Session ID",
            "Connected At",
            "Last Activity",
        )

    def _setup_chat_table(self) -> None:
        """Configure the chat messages DataTable columns."""
        table = self.query_one("#table-chat", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "ID",
            "Username",
            "Room",
            "Message",
            "Timestamp",
        )

    @work(thread=False)
    async def _load_players(self) -> None:
        """Fetch and display players from the database."""
        table = self.query_one("#table-players", DataTable)
        table.clear()

        try:
            players = await self.app.api_client.get_players()

            for player in players:
                table.add_row(
                    str(player.get("id", "")),
                    player.get("username", ""),
                    player.get("role", ""),
                    player.get("current_room", ""),
                    "Yes" if player.get("is_active", False) else "No",
                    self._format_timestamp(player.get("created_at", "")),
                    self._format_timestamp(player.get("last_login", "")),
                )

            self.notify(f"Loaded {len(players)} players", severity="information")

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load players: {e}", severity="error")

    @work(thread=False)
    async def _load_sessions(self) -> None:
        """Fetch and display active sessions from the database."""
        table = self.query_one("#table-sessions", DataTable)
        table.clear()

        try:
            sessions = await self.app.api_client.get_sessions()

            for session in sessions:
                table.add_row(
                    str(session.get("id", "")),
                    session.get("username", ""),
                    self._truncate(session.get("session_id", ""), 20),
                    self._format_timestamp(session.get("connected_at", "")),
                    self._format_timestamp(session.get("last_activity", "")),
                )

            self.notify(f"Loaded {len(sessions)} sessions", severity="information")

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load sessions: {e}", severity="error")

    @work(thread=False)
    async def _load_chat_messages(self) -> None:
        """Fetch and display chat messages from the database."""
        table = self.query_one("#table-chat", DataTable)
        table.clear()

        try:
            messages = await self.app.api_client.get_chat_messages(limit=100)

            for msg in messages:
                table.add_row(
                    str(msg.get("id", "")),
                    msg.get("username", ""),
                    msg.get("room", ""),
                    self._truncate(msg.get("message", ""), 50),
                    self._format_timestamp(msg.get("timestamp", "")),
                )

            self.notify(f"Loaded {len(messages)} messages", severity="information")

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load chat messages: {e}", severity="error")

    def _format_timestamp(self, timestamp: str | None) -> str:
        """Format a timestamp for display."""
        if not timestamp:
            return "-"
        # Truncate microseconds for cleaner display
        if "." in timestamp:
            timestamp = timestamp.split(".")[0]
        return timestamp

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to a maximum length."""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    # -------------------------------------------------------------------------
    # Button Handlers
    # -------------------------------------------------------------------------

    @on(Button.Pressed, "#btn-back")
    def handle_back_button(self) -> None:
        """Handle back button press."""
        self.action_back()

    # -------------------------------------------------------------------------
    # Actions (Bound to Keys)
    # -------------------------------------------------------------------------

    def action_refresh(self) -> None:
        """Refresh all tables (key: r)."""
        self._load_players()
        self._load_sessions()
        self._load_chat_messages()
        self.notify("Refreshing all tables...", severity="information")

    def action_back(self) -> None:
        """Go back to dashboard (key: b)."""
        self.app.pop_screen()

    def action_quit(self) -> None:
        """Quit the application (key: q)."""
        self.app.exit()
