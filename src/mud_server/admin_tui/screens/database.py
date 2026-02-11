"""
Database viewer screen for PipeWorks Admin TUI.

This module provides a database viewing interface that allows superusers
to view the contents of various database tables (users, sessions, chat).

    The DatabaseScreen shows:
    - Tabbed interface for different tables
    - DataTable widgets for viewing records
    - A table browser for any database table
    - Player locations view for room/zone occupancy
    - Refresh functionality for each table
"""

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Static, TabbedContent, TabPane

from mud_server.admin_tui.api.client import AuthenticationError


class ConfirmKickScreen(ModalScreen[bool]):
    """Modal confirmation prompt for kicking a session."""

    DEFAULT_CSS = """
    ConfirmKickScreen {
        align: center middle;
    }

    .confirm-dialog {
        width: 60;
        border: solid $primary;
        padding: 1 2;
        background: $surface;
    }

    .confirm-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    .confirm-actions {
        height: 3;
        padding-top: 1;
    }

    .confirm-button {
        margin-right: 1;
    }
    """

    def __init__(self, username: str, session_id: str) -> None:
        super().__init__()
        self._username = username
        self._session_id = session_id

    def compose(self) -> ComposeResult:
        with Vertical(classes="confirm-dialog"):
            yield Static("Kick Session", classes="confirm-title")
            yield Static(
                f"Kick {self._username}?\nSession: {self._session_id}",
                id="confirm-message",
            )
            with Horizontal(classes="confirm-actions"):
                yield Button(
                    "Cancel", variant="default", id="confirm-cancel", classes="confirm-button"
                )
                yield Button(
                    "Kick", variant="warning", id="confirm-accept", classes="confirm-button"
                )

    @on(Button.Pressed, "#confirm-cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-accept")
    def _accept(self) -> None:
        self.dismiss(True)


class ConfirmUserRemovalScreen(ModalScreen[str | None]):
    """Modal confirmation prompt for user deactivation or deletion."""

    DEFAULT_CSS = """
    ConfirmUserRemovalScreen {
        align: center middle;
    }

    .confirm-dialog {
        width: 70;
        border: solid $primary;
        padding: 1 2;
        background: $surface;
    }

    .confirm-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    .confirm-actions {
        height: 3;
        padding-top: 1;
    }

    .confirm-button {
        margin-right: 1;
    }
    """

    def __init__(self, username: str, role: str) -> None:
        super().__init__()
        self._username = username
        self._role = role

    def compose(self) -> ComposeResult:
        with Vertical(classes="confirm-dialog"):
            yield Static("Remove User", classes="confirm-title")
            yield Static(
                "\n".join(
                    [
                        f"User: {self._username} ({self._role})",
                        "",
                        "Deactivate: disables login and removes active sessions.",
                        "Delete: permanently removes the user and related data.",
                    ]
                ),
                id="confirm-message",
            )
            with Horizontal(classes="confirm-actions"):
                yield Button(
                    "Cancel", variant="default", id="confirm-cancel", classes="confirm-button"
                )
                yield Button(
                    "Deactivate",
                    variant="warning",
                    id="confirm-deactivate",
                    classes="confirm-button",
                )
                yield Button(
                    "Delete",
                    variant="error",
                    id="confirm-delete",
                    classes="confirm-button",
                )

    @on(Button.Pressed, "#confirm-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-deactivate")
    def _deactivate(self) -> None:
        self.dismiss("deactivate")

    @on(Button.Pressed, "#confirm-delete")
    def _delete(self) -> None:
        self.dismiss("delete")


class DatabaseScreen(Screen):
    """
    Database viewer screen for superusers.

    Displays database tables in a tabbed interface with DataTable widgets.
    Allows viewing of users, sessions, and chat messages.

    Key Bindings:
        r: Refresh current table
        b: Go back to dashboard
        x: Kick selected session (connections/sessions tabs)
        d: Deactivate/delete selected user (users tab)
        q, ctrl+q: Quit application

    CSS Classes:
        .database-container: Main content container.
        .table-container: Container for each table tab.
        .table-header: Header row styling for tables.
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("b", "back", "Back", priority=True),
        Binding("x", "kick", "Kick", priority=True),
        Binding("d", "remove_user", "Remove User", priority=True),
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
            # Tabbed content for different tables
            with TabbedContent(id="table-tabs"):
                with TabPane("Tables", id="tab-tables"):
                    yield DataTable(id="table-list")

                with TabPane("Users", id="tab-players"):
                    yield DataTable(id="table-players")

                with TabPane("Character Locations", id="tab-player-locations"):
                    yield DataTable(id="table-player-locations")

                with TabPane("Connections", id="tab-connections"):
                    yield DataTable(id="table-connections")

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
        self._setup_player_locations_table()
        self._setup_connections_table()
        self._setup_sessions_table()
        self._setup_chat_table()
        self._setup_table_data_table()

        # Apply user-configured keybindings
        self._apply_keybindings()

        # Track per-tab refresh state to prevent overlapping requests.
        self._refreshing_tabs: set[str] = set()
        # Track the selected table name for the generic table data tab.
        self._active_table_name: str | None = None

        # Load initial data
        self._load_tables()
        self._load_players()
        self._load_player_locations()
        self._load_connections()
        self._load_sessions()
        self._load_chat_messages()

        # Auto-refresh the active tab on an interval for a lightweight live view.
        self._auto_refresh_interval = 10.0
        self._auto_refresh_timer = self.set_interval(
            self._auto_refresh_interval, self._auto_refresh_active_tab
        )

    def on_unmount(self) -> None:
        """Stop auto-refresh when the screen unmounts."""
        timer = getattr(self, "_auto_refresh_timer", None)
        if timer:
            timer.stop()

    def _apply_keybindings(self) -> None:
        """
        Bind user-configurable navigation keys.

        This binds actions for:
        - Tab navigation (next/prev)
        - Table cursor movement (hjkl)
        - Selection (space/enter)
        - Session management (kick)
        - User management (remove/deactivate)
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
            "kick",
            "remove_user",
        ):
            for key in bindings.get_keys(action):
                # Preserve the first binding if duplicates exist.
                self._keybindings_by_key.setdefault(key, action)

    def _setup_players_table(self) -> None:
        """Configure the users DataTable columns."""
        table = self.query_one("#table-players", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "ID",
            "Username",
            "Role",
            "Origin",
            "Characters",
            "Guest",
            "Guest Expires",
            "Active",
            "Tombstoned",
            "Created",
            "Last Login",
            "Password Hash",
        )

    def _setup_sessions_table(self) -> None:
        """Configure the sessions DataTable columns."""
        table = self.query_one("#table-sessions", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "ID",
            "Username",
            "Character",
            "Client",
            "Session ID",
            "Created At",
            "Last Activity",
            "Expires At",
        )

    def _setup_connections_table(self) -> None:
        """Configure the connections DataTable columns."""
        table = self.query_one("#table-connections", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Username",
            "Client",
            "Session ID",
            "Last Activity",
            "Age",
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

    def _setup_player_locations_table(self) -> None:
        """Configure the character locations DataTable columns."""
        table = self.query_one("#table-player-locations", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Character ID",
            "Character",
            "Zone",
            "Room",
            "Updated",
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

        tab_id = "tab-tables"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            tables = await self.app.api_client.get_tables()

            for table_info in tables:
                columns = ", ".join(table_info.get("columns", []))
                table.add_row(
                    table_info.get("name", ""),
                    columns,
                    str(table_info.get("row_count", 0)),
                )

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load tables: {e}", severity="error")
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_player_locations(self) -> None:
        """Fetch and display character locations."""
        table = self.query_one("#table-player-locations", DataTable)
        table.clear()

        tab_id = "tab-player-locations"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            locations = await self.app.api_client.get_player_locations()

            for location in locations:
                table.add_row(
                    str(location.get("character_id", "")),
                    location.get("character_name", ""),
                    location.get("zone_id") or "-",
                    location.get("room_id", ""),
                    self._format_timestamp(location.get("updated_at", "")),
                )

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load character locations: {e}", severity="error")
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_connections(self) -> None:
        """Fetch and display active connections."""
        table = self.query_one("#table-connections", DataTable)
        table.clear()

        tab_id = "tab-connections"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            connections = await self.app.api_client.get_connections()

            for connection in connections:
                table.add_row(
                    connection.get("username", ""),
                    connection.get("client_type", "") or "-",
                    connection.get("session_id", ""),
                    self._format_timestamp(connection.get("last_activity", "")),
                    self._format_duration(connection.get("age_seconds")),
                    self._format_timestamp(connection.get("expires_at", "")),
                )

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load connections: {e}", severity="error")
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_table_data(self, table_name: str) -> None:
        """Fetch and display rows for a selected table."""
        data_table = self.query_one("#table-data", DataTable)
        data_table.clear(columns=True)

        tab_id = "tab-table-data"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            # Remember the active table so auto-refresh can reload it.
            self._active_table_name = table_name
            payload = await self.app.api_client.get_table_rows(table_name, limit=200)
            columns = payload.get("columns", [])
            rows = payload.get("rows", [])

            if not columns:
                self.notify(f"No columns found for {table_name}", severity="warning")
                return

            data_table.add_columns(*columns)
            for row in rows:
                data_table.add_row(*[self._format_cell(value) for value in row])

            tabs = self.query_one("#table-tabs", TabbedContent)
            tabs.active = "tab-table-data"

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load table data: {e}", severity="error")
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_players(self) -> None:
        """Fetch and display users from the database."""
        table = self.query_one("#table-players", DataTable)
        table.clear()

        tab_id = "tab-players"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            players = await self.app.api_client.get_players()

            for player in players:
                table.add_row(
                    str(player.get("id", "")),
                    player.get("username", ""),
                    player.get("role", ""),
                    player.get("account_origin", "") or "-",
                    str(player.get("character_count", "")),
                    "Yes" if player.get("is_guest", False) else "No",
                    self._format_timestamp(player.get("guest_expires_at", "")),
                    "Yes" if player.get("is_active", False) else "No",
                    self._format_timestamp(player.get("tombstoned_at", "")),
                    self._format_timestamp(player.get("created_at", "")),
                    self._format_timestamp(player.get("last_login", "")),
                    player.get("password_hash", "") or "-",
                )

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load players: {e}", severity="error")
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_sessions(self) -> None:
        """Fetch and display active sessions from the database."""
        table = self.query_one("#table-sessions", DataTable)
        table.clear()

        tab_id = "tab-sessions"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            sessions = await self.app.api_client.get_sessions()

            for session in sessions:
                table.add_row(
                    str(session.get("id", "")),
                    session.get("username", ""),
                    session.get("character_name", "") or "-",
                    session.get("client_type", "") or "-",
                    self._truncate(session.get("session_id", ""), 20),
                    self._format_timestamp(session.get("created_at", "")),
                    self._format_timestamp(session.get("last_activity", "")),
                    self._format_timestamp(session.get("expires_at", "")),
                )

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load sessions: {e}", severity="error")
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_chat_messages(self) -> None:
        """Fetch and display chat messages from the database."""
        table = self.query_one("#table-chat", DataTable)
        table.clear()

        tab_id = "tab-chat"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            messages = await self.app.api_client.get_chat_messages(limit=100)

            for msg in messages:
                table.add_row(
                    str(msg.get("id", "")),
                    msg.get("username", ""),
                    msg.get("room", ""),
                    self._truncate(msg.get("message", ""), 50),
                    self._format_timestamp(msg.get("timestamp", "")),
                )

        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to load chat messages: {e}", severity="error")
        finally:
            self._refreshing_tabs.discard(tab_id)

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

        # Special-case kick to avoid clashing with cursor-up in other tabs.
        # Only allow kick on Connections or Sessions tabs.
        if action == "kick":
            if self._is_connections_tab_active() or self._is_sessions_tab_active():
                self.action_kick()
                event.stop()
            return
        if action == "remove_user":
            if self._is_players_tab_active():
                self.action_remove_user()
                event.stop()
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
        self._load_player_locations()
        self._load_connections()
        self._load_sessions()
        self._load_chat_messages()
        # No success toast; refresh silently to keep the UI clean.

    def action_kick(self) -> None:
        """Kick the selected session (key: x)."""
        if not (self._is_connections_tab_active() or self._is_sessions_tab_active()):
            return
        self._kick_selected()

    def action_remove_user(self) -> None:
        """Deactivate or delete the selected user (key: d)."""
        if not self._is_players_tab_active():
            return
        self._remove_selected_player()

    @on(TabbedContent.TabActivated)
    def handle_tab_activated(self) -> None:
        """Refresh the active tab when the user switches tabs."""
        self._refresh_active_tab()

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
            "tab-player-locations": "#table-player-locations",
            "tab-connections": "#table-connections",
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

    def _is_players_tab_active(self) -> bool:
        """Return True if the players tab is active."""
        tabs = self.query_one("#table-tabs", TabbedContent)
        active_id = tabs.active or (tabs.active_pane.id if tabs.active_pane else None)
        return active_id == "tab-players"

    def _is_connections_tab_active(self) -> bool:
        """Return True if the connections tab is active."""
        tabs = self.query_one("#table-tabs", TabbedContent)
        active_id = tabs.active or (tabs.active_pane.id if tabs.active_pane else None)
        return active_id == "tab-connections"

    def _is_sessions_tab_active(self) -> bool:
        """Return True if the sessions tab is active."""
        tabs = self.query_one("#table-tabs", TabbedContent)
        active_id = tabs.active or (tabs.active_pane.id if tabs.active_pane else None)
        return active_id == "tab-sessions"

    def _format_cell(self, value: object) -> str:
        """Format a generic cell value for display in the DataTable."""
        if value is None:
            return "-"
        return str(value)

    def _format_duration(self, seconds: object) -> str:
        """Format seconds into HH:MM:SS."""
        if seconds is None:
            return "-"
        try:
            total = int(str(seconds))
        except (TypeError, ValueError):
            return "-"
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @work(thread=False)
    async def _kick_selected(self) -> None:
        """Prompt and kick the selected session from the connections table."""
        target = self._get_kick_target()
        if not target:
            return

        username, session_id = target

        confirmed = await self.app.push_screen(
            ConfirmKickScreen(username=username, session_id=session_id),
            wait_for_dismiss=True,
        )
        if not confirmed:
            return

        try:
            response = await self.app.api_client.kick_session(session_id)
            if not response.get("success", False):
                self.notify(response.get("message", "Failed to kick session"), severity="error")
                return
            self._load_connections()
        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to kick session: {e}", severity="error")

    @work(thread=False)
    async def _remove_selected_player(self) -> None:
        """Prompt and remove the selected player (deactivate or delete)."""
        target = self._get_selected_player()
        if not target:
            return

        username, role = target

        if username == (self.app.api_client.session.username or ""):
            self.notify("Cannot remove your own account", severity="error")
            return

        action = await self.app.push_screen(
            ConfirmUserRemovalScreen(username=username, role=role),
            wait_for_dismiss=True,
        )
        if action is None:
            return

        try:
            response = await self.app.api_client.manage_user(username, action)
            if not response.get("success", False):
                self.notify(response.get("message", "Failed to update user"), severity="error")
                return

            # Refresh related tabs after updates.
            self._load_players()
            self._load_player_locations()
            self._load_sessions()
            self._load_connections()
        except AuthenticationError as e:
            self.notify(f"Permission denied: {e.detail}", severity="error")
        except Exception as e:
            self.notify(f"Failed to update user: {e}", severity="error")

    def _get_kick_target(self) -> tuple[str, str] | None:
        """
        Resolve the selected session target for a kick action.

        Returns (username, session_id) when a valid row is selected.
        Uses column positions based on the active tab's table schema.
        """
        if self._is_connections_tab_active():
            table = self.query_one("#table-connections", DataTable)
            username_idx = 0
            session_idx = 2
        elif self._is_sessions_tab_active():
            table = self.query_one("#table-sessions", DataTable)
            username_idx = 1
            session_idx = 3
        else:
            return None

        if table.row_count == 0:
            return None

        selected_row = table.get_row_at(table.cursor_row)
        if not selected_row:
            return None

        username = str(selected_row[username_idx])
        session_id = str(selected_row[session_idx])
        return username, session_id

    def _get_selected_player(self) -> tuple[str, str] | None:
        """
        Resolve the selected player from the players table.

        Returns (username, role) when a valid row is selected.
        """
        if not self._is_players_tab_active():
            return None

        table = self.query_one("#table-players", DataTable)
        if table.row_count == 0:
            return None

        selected_row = table.get_row_at(table.cursor_row)
        if not selected_row:
            return None

        username = str(selected_row[1])
        role = str(selected_row[2])
        return username, role

    def _refresh_active_tab(self) -> None:
        """
        Refresh the currently active tab, if possible.

        This is called by the auto-refresh timer and when a user switches tabs.
        It avoids overlapping requests by respecting the per-tab refresh guard.
        """
        if self.app.screen is not self:
            return

        tabs = self.query_one("#table-tabs", TabbedContent)
        active_id = tabs.active or (tabs.active_pane.id if tabs.active_pane else None)
        if not active_id:
            return

        refresh_map = {
            "tab-tables": self._load_tables,
            "tab-players": self._load_players,
            "tab-player-locations": self._load_player_locations,
            "tab-connections": self._load_connections,
            "tab-sessions": self._load_sessions,
            "tab-chat": self._load_chat_messages,
            "tab-table-data": self._refresh_table_data,
        }
        refresh_fn = refresh_map.get(active_id)
        if refresh_fn:
            refresh_fn()

    def _refresh_table_data(self) -> None:
        """Refresh the currently selected table data, if any."""
        if not self._active_table_name:
            return
        self._load_table_data(self._active_table_name)

    def _auto_refresh_active_tab(self) -> None:
        """Auto-refresh hook for the periodic timer."""
        self._refresh_active_tab()
