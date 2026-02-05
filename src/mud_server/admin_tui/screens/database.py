"""
Database viewer screen for PipeWorks Admin TUI.

This module provides a database viewing interface that allows superusers
to view the contents of various database tables (players, sessions, chat).

    The DatabaseScreen shows:
    - Tabbed interface for different tables
    - DataTable widgets for viewing records
    - A table browser for any database table
    - Refresh functionality for each table
"""

from textual import events, on, work
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
        height: 1fr;
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

    TabPane {
        height: 1fr;
    }

    DataTable {
        height: 1fr;
        width: 100%;
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
                with TabPane("Tables", id="tab-tables"):
                    yield DataTable(id="table-list")

                with TabPane("Players", id="tab-players"):
                    yield DataTable(id="table-players")

                with TabPane("Sessions", id="tab-sessions"):
                    yield DataTable(id="table-sessions")

                with TabPane("Chat Messages", id="tab-chat"):
                    yield DataTable(id="table-chat")

                with TabPane("Table Data", id="tab-table-data"):
                    yield DataTable(id="table-data")

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
        self._setup_tables_list_table()
        self._setup_players_table()
        self._setup_sessions_table()
        self._setup_chat_table()
        self._setup_table_data_table()

        # Apply user-configured keybindings
        self._apply_keybindings()

        # Load initial data
        self._load_tables()
        self._load_players()
        self._load_sessions()
        self._load_chat_messages()

    def _apply_keybindings(self) -> None:
        """
        Bind user-configurable navigation keys.

        This binds actions for:
        - Tab navigation (next/prev)
        - Table cursor movement (hjkl)
        - Selection (space/enter)
        """
        bindings = getattr(self.app, "keybindings", None)
        if not bindings:
            return

        # Map configured keys to actions so we can handle them in on_key.
        # Textual's Screen does not support dynamic bind() calls, so we
        # interpret these keys manually to avoid global app bindings.
        self._keybindings_by_key: dict[str, str] = {}
        for action in (
            "next_tab",
            "prev_tab",
            "cursor_up",
            "cursor_down",
            "cursor_left",
            "cursor_right",
            "select",
        ):
            for key in bindings.get_keys(action):
                # Preserve the first binding if duplicates exist.
                self._keybindings_by_key.setdefault(key, action)

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
            "Created At",
            "Last Activity",
            "Expires At",
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

    def _setup_tables_list_table(self) -> None:
        """Configure the table list DataTable columns."""
        table = self.query_one("#table-list", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Table",
            "Columns",
            "Rows",
        )

    def _setup_table_data_table(self) -> None:
        """Configure the generic table data DataTable."""
        table = self.query_one("#table-data", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

    @work(thread=False)
    async def _load_tables(self) -> None:
        """Fetch and display available database tables."""
        table = self.query_one("#table-list", DataTable)
        table.clear()

        try:
            tables = await self.app.api_client.get_tables()

            for table_info in tables:
                columns = ", ".join(table_info.get("columns", []))
                table.add_row(
                    table_info.get("name", ""),
                    columns,
                    str(table_info.get("row_count", 0)),
                )

            self.notify(f"Loaded {len(tables)} tables", severity="information")

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load tables: {e}", severity="error")

    @work(thread=False)
    async def _load_table_data(self, table_name: str) -> None:
        """Fetch and display rows for a selected table."""
        data_table = self.query_one("#table-data", DataTable)
        data_table.clear(columns=True)

        try:
            payload = await self.app.api_client.get_table_rows(table_name, limit=200)
            columns = payload.get("columns", [])
            rows = payload.get("rows", [])

            if not columns:
                self.notify(f"No columns found for {table_name}", severity="warning")
                return

            data_table.add_columns(*columns)
            for row in rows:
                data_table.add_row(*[self._format_cell(value) for value in row])

            self.notify(
                f"Loaded {len(rows)} rows from {table_name}",
                severity="information",
            )

            tabs = self.query_one("#table-tabs", TabbedContent)
            tabs.active = "tab-table-data"

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load table data: {e}", severity="error")

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
                    self._format_timestamp(session.get("created_at", "")),
                    self._format_timestamp(session.get("last_activity", "")),
                    self._format_timestamp(session.get("expires_at", "")),
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

    def on_key(self, event: events.Key) -> None:
        """
        Handle user-configured keybindings.

        We translate key presses into action methods for this screen. This
        keeps bindings scoped to the screen without relying on global app
        bindings, and avoids mutation of class-level BINDINGS.
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

    # -------------------------------------------------------------------------
    # Keybinding Actions
    # -------------------------------------------------------------------------

    def action_next_tab(self) -> None:
        """Switch to the next database tab."""
        self._switch_tab(direction=1)

    def action_prev_tab(self) -> None:
        """Switch to the previous database tab."""
        self._switch_tab(direction=-1)

    def action_cursor_up(self) -> None:
        """Move selection up in the active table."""
        table = self._get_active_table()
        if table:
            table.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move selection down in the active table."""
        table = self._get_active_table()
        if table:
            table.action_cursor_down()

    def action_cursor_left(self) -> None:
        """Move selection left in the active table."""
        table = self._get_active_table()
        if table:
            table.action_cursor_left()

    def action_cursor_right(self) -> None:
        """Move selection right in the active table."""
        table = self._get_active_table()
        if table:
            table.action_cursor_right()

    def action_select(self) -> None:
        """Select the current row in the active table."""
        table = self._get_active_table()
        if not table:
            return

        if self._is_tables_tab_active():
            selected_row = table.get_row_at(table.cursor_row)
            if selected_row:
                table_name = str(selected_row[0])
                if table_name:
                    self._load_table_data(table_name)
            return

        table.action_select_cursor()

    def _switch_tab(self, direction: int) -> None:
        """Rotate tab selection by +1 (next) or -1 (prev)."""
        tabs = self.query_one("#table-tabs", TabbedContent)
        panes = list(tabs.query(TabPane))
        if not panes:
            return

        pane_ids = [pane.id for pane in panes if pane.id]
        if not pane_ids:
            return

        current_id = tabs.active or (tabs.active_pane.id if tabs.active_pane else None)
        if current_id in pane_ids:
            current_index = pane_ids.index(current_id)
        else:
            current_index = 0

        next_index = (current_index + direction) % len(pane_ids)
        tabs.active = pane_ids[next_index]

    def _get_active_table(self) -> DataTable | None:
        """
        Get the DataTable for the currently active tab.

        Falls back to the focused widget if it is already a DataTable.
        """
        if isinstance(self.app.focused, DataTable):
            return self.app.focused

        tabs = self.query_one("#table-tabs", TabbedContent)
        active_id = tabs.active or (tabs.active_pane.id if tabs.active_pane else None)
        if not active_id:
            return None

        table_id_map = {
            "tab-tables": "#table-list",
            "tab-players": "#table-players",
            "tab-sessions": "#table-sessions",
            "tab-chat": "#table-chat",
            "tab-table-data": "#table-data",
        }
        table_selector = table_id_map.get(active_id)
        if not table_selector:
            return None

        return self.query_one(table_selector, DataTable)

    def _is_tables_tab_active(self) -> bool:
        """Return True if the table list tab is active."""
        tabs = self.query_one("#table-tabs", TabbedContent)
        active_id = tabs.active or (tabs.active_pane.id if tabs.active_pane else None)
        return active_id == "tab-tables"

    def _format_cell(self, value: object) -> str:
        """Format a generic cell value for display in the DataTable."""
        if value is None:
            return "-"
        return str(value)
