"""
Tab handlers for the Admin TUI database screen.

These classes isolate per-tab setup and data loading so the main screen
can focus on orchestration and user input.
"""

from __future__ import annotations

from typing import Any

from textual.widgets import DataTable

from mud_server.admin_tui.api.client import AuthenticationError
from mud_server.admin_tui.screens.formatting import (
    format_cell,
    format_duration,
    format_timestamp,
    truncate,
)


def _capture_selection(table: DataTable) -> tuple[str | None, int]:
    """Capture the current selection key and row index."""
    selected_key: str | None = None
    selected_index = table.cursor_row
    if table.row_count:
        row = table.get_row_at(table.cursor_row)
        if row and row[0] is not None:
            selected_key = str(row[0])
    return selected_key, selected_index


def _restore_selection(
    table: DataTable, selected_key: str | None, selected_index: int, key_map: dict[str, int]
) -> None:
    """Restore selection by key, falling back to row index when possible."""
    if selected_key and selected_key in key_map:
        table.move_cursor(row=key_map[selected_key], column=table.cursor_column, animate=False)
        return
    if 0 <= selected_index < table.row_count:
        table.move_cursor(row=selected_index, column=table.cursor_column, animate=False)


class UsersTab:
    """Users tab handler (account list and sorting)."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen
        self._users_cache: list[dict[str, Any]] = []
        self._sort_state: tuple[int, bool] | None = None
        self._show_tombstoned = False

    def setup(self) -> None:
        """Configure the users DataTable columns."""
        table = self._screen.query_one("#table-players", DataTable)
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

    async def load(self) -> None:
        """Fetch and display users from the database."""
        table = self._screen.query_one("#table-players", DataTable)
        selected_key, selected_index = _capture_selection(table)
        if selected_key is not None:
            self._screen.selected_user_id = selected_key
        table.clear()

        try:
            players = await self._screen.app.api_client.get_players()
            self._users_cache = list(players)
            self._sort_state = None
            self._render_users_table(self._filter_users(self._users_cache))

        except AuthenticationError as exc:
            self._screen.notify(f"Permission denied: {exc.detail}", severity="error")
        except Exception as exc:  # pragma: no cover - best-effort UI error
            self._screen.notify(f"Failed to load users: {exc}", severity="error")

    def sort_by_column(self, column_index: int) -> None:
        """Sort users by the selected column, toggling direction."""
        if not self._users_cache:
            return

        previous = self._sort_state
        ascending = True
        if previous and previous[0] == column_index:
            ascending = not previous[1]

        visible_users = self._filter_users(self._users_cache)
        sorted_users = self._sort_users(visible_users, column_index, ascending)
        self._sort_state = (column_index, ascending)
        self._render_users_table(sorted_users)

    def resolve_user(self, user_id: str) -> dict[str, Any] | None:
        """Return the cached user dict matching the given id."""
        return next((entry for entry in self._users_cache if str(entry.get("id")) == user_id), None)

    def toggle_tombstoned_visibility(self) -> None:
        """Toggle whether tombstoned users are shown in the users table."""
        table = self._screen.query_one("#table-players", DataTable)
        selected_key, selected_index = _capture_selection(table)
        self._show_tombstoned = not self._show_tombstoned
        visible_users = self._filter_users(self._users_cache)
        if self._sort_state:
            column_index, ascending = self._sort_state
            visible_users = self._sort_users(visible_users, column_index, ascending)
        self._render_users_table(visible_users)
        if selected_key is not None:
            self._screen.selected_user_id = selected_key

    def _filter_users(self, users: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter users based on the tombstone visibility toggle."""
        if self._show_tombstoned:
            return list(users)
        return [user for user in users if not user.get("tombstoned_at")]

    def _render_users_table(self, users: list[dict[str, Any]]) -> None:
        table = self._screen.query_one("#table-players", DataTable)
        selected_key = self._screen.selected_user_id
        selected_index = table.cursor_row
        if selected_key is None:
            selected_key, selected_index = _capture_selection(table)
        table.clear()
        row_index_by_id: dict[str, int] = {}
        for user in users:
            row = (
                str(user.get("id", "")),
                user.get("username", ""),
                user.get("role", ""),
                user.get("account_origin", "") or "-",
                str(user.get("character_count", "")),
                "Yes" if user.get("is_guest", False) else "No",
                format_timestamp(user.get("guest_expires_at", "")),
                "Yes" if user.get("is_active", False) else "No",
                format_timestamp(user.get("tombstoned_at", "")),
                format_timestamp(user.get("created_at", "")),
                format_timestamp(user.get("last_login", "")),
                user.get("password_hash", "") or "-",
            )
            table.add_row(*row)
            if row[0]:
                row_index_by_id[str(row[0])] = table.row_count - 1

        _restore_selection(table, selected_key, selected_index, row_index_by_id)

    def _sort_users(
        self, users: list[dict[str, Any]], column_index: int, ascending: bool
    ) -> list[dict[str, Any]]:
        column_keys = [
            "id",
            "username",
            "role",
            "account_origin",
            "character_count",
            "is_guest",
            "guest_expires_at",
            "is_active",
            "tombstoned_at",
            "created_at",
            "last_login",
            "password_hash",
        ]
        key_name = column_keys[column_index] if column_index < len(column_keys) else "id"

        def sort_key(item: dict[str, Any]) -> tuple[int, str]:
            value = item.get(key_name)
            if value is None:
                return (1, "")
            if isinstance(value, bool):
                return (0, "1" if value else "0")
            return (0, str(value).lower())

        return sorted(users, key=sort_key, reverse=not ascending)


class TombstonedTab:
    """Tombstoned users tab handler."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen

    def setup(self) -> None:
        """Configure the tombstoned users DataTable columns."""
        table = self._screen.query_one("#table-tombstoned-users", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "ID",
            "Username",
            "Role",
            "Origin",
            "Guest",
            "Guest Expires",
            "Created",
            "Last Login",
            "Tombstoned",
        )

    async def load(self) -> None:
        """Fetch and display tombstoned users from the database."""
        table = self._screen.query_one("#table-tombstoned-users", DataTable)
        selected_key, selected_index = _capture_selection(table)
        table.clear()

        try:
            users = await self._screen.app.api_client.get_players()
        except AuthenticationError as exc:
            self._screen.notify(f"Permission denied: {exc.detail}", severity="error")
            return
        except Exception as exc:  # pragma: no cover - best-effort UI error
            self._screen.notify(f"Failed to load tombstoned users: {exc}", severity="error")
            return

        tombstoned_users = [user for user in users if user.get("tombstoned_at")]
        row_index_by_id: dict[str, int] = {}
        for user in tombstoned_users:
            row = (
                str(user.get("id", "")),
                user.get("username", ""),
                user.get("role", ""),
                user.get("account_origin", "") or "-",
                "Yes" if user.get("is_guest", False) else "No",
                format_timestamp(user.get("guest_expires_at", "")),
                format_timestamp(user.get("created_at", "")),
                format_timestamp(user.get("last_login", "")),
                format_timestamp(user.get("tombstoned_at", "")),
            )
            table.add_row(*row)
            if row[0]:
                row_index_by_id[str(row[0])] = table.row_count - 1

        _restore_selection(table, selected_key, selected_index, row_index_by_id)


class CharacterLocationsTab:
    """Character locations tab handler."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen

    def setup(self) -> None:
        table = self._screen.query_one("#table-player-locations", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Character ID",
            "Character",
            "Zone",
            "Room",
            "Updated",
        )

    async def load(self) -> None:
        table = self._screen.query_one("#table-player-locations", DataTable)
        selected_key, selected_index = _capture_selection(table)
        table.clear()

        try:
            locations = await self._screen.app.api_client.get_player_locations()
            key_map: dict[str, int] = {}
            for location in locations:
                row = (
                    str(location.get("character_id", "")),
                    location.get("character_name", ""),
                    location.get("zone_id") or "-",
                    location.get("room_id", ""),
                    format_timestamp(location.get("updated_at", "")),
                )
                table.add_row(*row)
                if row[0]:
                    key_map[str(row[0])] = table.row_count - 1
            _restore_selection(table, selected_key, selected_index, key_map)

        except AuthenticationError as exc:
            self._screen.notify(f"Permission denied: {exc.detail}", severity="error")
        except Exception as exc:  # pragma: no cover - best-effort UI error
            self._screen.notify(f"Failed to load character locations: {exc}", severity="error")


class ConnectionsTab:
    """Active connections tab handler."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen

    def setup(self) -> None:
        table = self._screen.query_one("#table-connections", DataTable)
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

    async def load(self) -> None:
        table = self._screen.query_one("#table-connections", DataTable)
        selected_key, selected_index = _capture_selection(table)
        table.clear()

        try:
            connections = await self._screen.app.api_client.get_connections()
            key_map: dict[str, int] = {}
            for connection in connections:
                row = (
                    connection.get("username", ""),
                    connection.get("client_type", "") or "-",
                    connection.get("session_id", ""),
                    format_timestamp(connection.get("last_activity", "")),
                    format_duration(connection.get("age_seconds")),
                    format_timestamp(connection.get("expires_at", "")),
                )
                table.add_row(*row)
                if row[2]:
                    key_map[str(row[2])] = table.row_count - 1
            _restore_selection(table, selected_key, selected_index, key_map)

        except AuthenticationError as exc:
            self._screen.notify(f"Permission denied: {exc.detail}", severity="error")
        except Exception as exc:  # pragma: no cover - best-effort UI error
            self._screen.notify(f"Failed to load connections: {exc}", severity="error")


class SessionsTab:
    """Sessions tab handler."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen

    def setup(self) -> None:
        table = self._screen.query_one("#table-sessions", DataTable)
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

    async def load(self) -> None:
        table = self._screen.query_one("#table-sessions", DataTable)
        selected_key, selected_index = _capture_selection(table)
        table.clear()

        try:
            sessions = await self._screen.app.api_client.get_sessions()
            key_map: dict[str, int] = {}
            for session in sessions:
                row = (
                    str(session.get("id", "")),
                    session.get("username", ""),
                    session.get("character_name", "") or "-",
                    session.get("client_type", "") or "-",
                    truncate(session.get("session_id", ""), 20),
                    format_timestamp(session.get("created_at", "")),
                    format_timestamp(session.get("last_activity", "")),
                    format_timestamp(session.get("expires_at", "")),
                )
                table.add_row(*row)
                if row[0]:
                    key_map[str(row[0])] = table.row_count - 1
            _restore_selection(table, selected_key, selected_index, key_map)

        except AuthenticationError as exc:
            self._screen.notify(f"Permission denied: {exc.detail}", severity="error")
        except Exception as exc:  # pragma: no cover - best-effort UI error
            self._screen.notify(f"Failed to load sessions: {exc}", severity="error")


class ChatTab:
    """Chat messages tab handler."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen

    def setup(self) -> None:
        table = self._screen.query_one("#table-chat", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "ID",
            "Username",
            "Room",
            "Message",
            "Timestamp",
        )

    async def load(self) -> None:
        table = self._screen.query_one("#table-chat", DataTable)
        selected_key, selected_index = _capture_selection(table)
        table.clear()

        try:
            messages = await self._screen.app.api_client.get_chat_messages(limit=100)
            key_map: dict[str, int] = {}
            for msg in messages:
                row = (
                    str(msg.get("id", "")),
                    msg.get("username", ""),
                    msg.get("room", ""),
                    truncate(msg.get("message", ""), 50),
                    format_timestamp(msg.get("timestamp", "")),
                )
                table.add_row(*row)
                if row[0]:
                    key_map[str(row[0])] = table.row_count - 1
            _restore_selection(table, selected_key, selected_index, key_map)

        except AuthenticationError as exc:
            self._screen.notify(f"Permission denied: {exc.detail}", severity="error")
        except Exception as exc:  # pragma: no cover - best-effort UI error
            self._screen.notify(f"Failed to load chat messages: {exc}", severity="error")


class TablesListTab:
    """Database tables list tab handler."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen

    def setup(self) -> None:
        table = self._screen.query_one("#table-list", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Table",
            "Columns",
            "Rows",
        )

    async def load(self) -> None:
        table = self._screen.query_one("#table-list", DataTable)
        selected_key, selected_index = _capture_selection(table)
        table.clear()

        try:
            tables = await self._screen.app.api_client.get_tables()
            key_map: dict[str, int] = {}
            for table_info in tables:
                columns = ", ".join(table_info.get("columns", []))
                row = (
                    table_info.get("name", ""),
                    columns,
                    str(table_info.get("row_count", 0)),
                )
                table.add_row(*row)
                if row[0]:
                    key_map[str(row[0])] = table.row_count - 1
            _restore_selection(table, selected_key, selected_index, key_map)

        except AuthenticationError as exc:
            self._screen.notify(f"Permission denied: {exc.detail}", severity="error")
        except Exception as exc:  # pragma: no cover - best-effort UI error
            self._screen.notify(f"Failed to load tables: {exc}", severity="error")


class TableDataTab:
    """Generic table data viewer tab handler."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen

    def setup(self) -> None:
        table = self._screen.query_one("#table-data", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

    async def load(self, table_name: str, *, limit: int = 200) -> None:
        data_table = self._screen.query_one("#table-data", DataTable)
        selected_key, selected_index = _capture_selection(data_table)
        data_table.clear(columns=True)

        payload = await self._screen.app.api_client.get_table_rows(table_name, limit=limit)
        columns = payload.get("columns", [])
        rows = payload.get("rows", [])

        if not columns:
            self._screen.notify(f"No columns found for {table_name}", severity="warning")
            return

        data_table.add_columns(*columns)
        key_map: dict[str, int] = {}
        for row in rows:
            formatted = [format_cell(value) for value in row]
            data_table.add_row(*formatted)
            if formatted and formatted[0] != "-":
                key_map[str(formatted[0])] = data_table.row_count - 1

        _restore_selection(data_table, selected_key, selected_index, key_map)
