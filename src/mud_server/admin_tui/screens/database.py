"""
Database viewer screen for PipeWorks Admin TUI.

This module provides a database viewing interface that allows superusers
to view the contents of various database tables (users, sessions, chat).

    The DatabaseScreen shows:
    - Tabbed interface for different tables
    - DataTable widgets for viewing records
    - A table browser for any database table
    - Character locations view for room/zone occupancy
    - Refresh functionality for each table
"""

from typing import Any, Protocol, cast

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, TabbedContent, TabPane

from mud_server.admin_tui.screens.database_actions import DatabaseActions
from mud_server.admin_tui.screens.database_tabs import (
    CharacterLocationsTab,
    ChatTab,
    ConnectionsTab,
    SessionsTab,
    TableDataTab,
    TablesListTab,
    UsersTab,
)


class _DatabaseTab(Protocol):
    """Common interface for database screen tabs."""

    def setup(self) -> None:
        """Prepare table columns and defaults."""

    async def load(self, *args: Any, **kwargs: Any) -> None:
        """Fetch and render tab data."""


class DatabaseScreen(Screen):
    """
    Database viewer screen for superusers.

    Displays database tables in a tabbed interface with DataTable widgets.
    Allows viewing of users, sessions, and chat messages.

    Key Bindings:
        r: Refresh current table
        b: Go back to dashboard
        s: Sort users by selected column
        x: Kick selected session (connections/sessions tabs)
        d: Deactivate/delete selected user (users tab)
        ctrl+q: Quit application

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
        Binding("ctrl+q", "quit", "Quit", priority=True),
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

        # Set up table handlers
        self._tabs: dict[str, _DatabaseTab] = {
            "tables": TablesListTab(self),
            "users": UsersTab(self),
            "character_locations": CharacterLocationsTab(self),
            "connections": ConnectionsTab(self),
            "sessions": SessionsTab(self),
            "chat": ChatTab(self),
            "table_data": TableDataTab(self),
        }
        self._actions = DatabaseActions(self)

        self._tabs["tables"].setup()
        self._tabs["users"].setup()
        self._tabs["character_locations"].setup()
        self._tabs["connections"].setup()
        self._tabs["sessions"].setup()
        self._tabs["chat"].setup()
        self._tabs["table_data"].setup()

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
            "sort",
            "kick",
            "remove_user",
        ):
            for key in bindings.get_keys(action):
                # Preserve the first binding if duplicates exist.
                self._keybindings_by_key.setdefault(key, action)

    @work(thread=False)
    async def _load_tables(self) -> None:
        """Fetch and display available database tables."""
        tab_id = "tab-tables"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            await self._tabs["tables"].load()
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_player_locations(self) -> None:
        """Fetch and display character locations."""
        tab_id = "tab-player-locations"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            await self._tabs["character_locations"].load()
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_connections(self) -> None:
        """Fetch and display active connections."""
        tab_id = "tab-connections"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            await self._tabs["connections"].load()
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_table_data(self, table_name: str) -> None:
        """Fetch and display rows for a selected table."""
        tab_id = "tab-table-data"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            # Remember the active table so auto-refresh can reload it.
            self._active_table_name = table_name
            await self._tabs["table_data"].load(table_name, limit=200)

            tabs = self.query_one("#table-tabs", TabbedContent)
            tabs.active = "tab-table-data"
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_players(self) -> None:
        """Fetch and display users from the database."""
        tab_id = "tab-players"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            await self._tabs["users"].load()
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_sessions(self) -> None:
        """Fetch and display active sessions from the database."""
        tab_id = "tab-sessions"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            await self._tabs["sessions"].load()
        finally:
            self._refreshing_tabs.discard(tab_id)

    @work(thread=False)
    async def _load_chat_messages(self) -> None:
        """Fetch and display chat messages from the database."""
        tab_id = "tab-chat"
        if tab_id in self._refreshing_tabs:
            return

        try:
            self._refreshing_tabs.add(tab_id)
            await self._tabs["chat"].load()
        finally:
            self._refreshing_tabs.discard(tab_id)

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
        table = self.get_active_table()
        if table:
            table.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move selection down in the active table."""
        table = self.get_active_table()
        if table:
            table.action_cursor_down()

    def action_cursor_left(self) -> None:
        """Move selection left in the active table."""
        self._actions.safe_cursor_left()

    def action_cursor_right(self) -> None:
        """Move selection right in the active table."""
        self._actions.safe_cursor_right()

    def action_select(self) -> None:
        """Select the current row in the active table."""
        table = self.get_active_table()
        if not table:
            return

        if self._is_players_tab_active():
            self._actions.open_user_detail()
            return

        if self._is_tables_tab_active():
            selected_row = table.get_row_at(table.cursor_row)
            if selected_row:
                table_name = str(selected_row[0])
                if table_name:
                    self._load_table_data(table_name)
            return

        table.action_select_cursor()

    def action_sort(self) -> None:
        """Sort the users table by the current column."""
        if not self._is_players_tab_active():
            return

        table = self.query_one("#table-players", DataTable)
        if table.cursor_column is None:
            return

        column_index = int(table.cursor_column)
        cast(UsersTab, self._tabs["users"]).sort_by_column(column_index)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open detail screens when a row is activated with mouse or Enter."""
        if event.data_table.id == "table-players":
            self._actions.open_user_detail()
            return

        if event.data_table.id == "table-player-locations":
            self._actions.open_character_detail_from_locations()

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

    def get_active_table(self) -> DataTable | None:
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

    @work(thread=False)
    async def _kick_selected(self) -> None:
        """Prompt and kick the selected session from the connections table."""
        await self._actions.kick_selected()

    @work(thread=False)
    async def _remove_selected_player(self) -> None:
        """Prompt and remove the selected player (deactivate or delete)."""
        await self._actions.remove_selected_user()

    def get_selected_session_target(self) -> tuple[str, str] | None:
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

    def get_selected_user_target(self) -> tuple[str, str] | None:
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
