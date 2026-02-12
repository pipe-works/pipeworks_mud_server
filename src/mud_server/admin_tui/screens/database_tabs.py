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


class UsersTab:
    """Users tab handler (account list and sorting)."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen
        self._users_cache: list[dict[str, Any]] = []
        self._sort_state: tuple[int, bool] | None = None

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
        table.clear()

        try:
            players = await self._screen.app.api_client.get_players()
            self._users_cache = list(players)
            self._sort_state = None
            self._render_users_table(self._users_cache)

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

        sorted_users = self._sort_users(self._users_cache, column_index, ascending)
        self._sort_state = (column_index, ascending)
        self._render_users_table(sorted_users)

    def resolve_user(self, user_id: str) -> dict[str, Any] | None:
        """Return the cached user dict matching the given id."""
        return next((entry for entry in self._users_cache if str(entry.get("id")) == user_id), None)

    def _render_users_table(self, users: list[dict[str, Any]]) -> None:
        table = self._screen.query_one("#table-players", DataTable)
        table.clear()
        for user in users:
            table.add_row(
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
        table.clear()

        try:
            locations = await self._screen.app.api_client.get_player_locations()
            for location in locations:
                table.add_row(
                    str(location.get("character_id", "")),
                    location.get("character_name", ""),
                    location.get("zone_id") or "-",
                    location.get("room_id", ""),
                    format_timestamp(location.get("updated_at", "")),
                )

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
        table.clear()

        try:
            connections = await self._screen.app.api_client.get_connections()
            for connection in connections:
                table.add_row(
                    connection.get("username", ""),
                    connection.get("client_type", "") or "-",
                    connection.get("session_id", ""),
                    format_timestamp(connection.get("last_activity", "")),
                    format_duration(connection.get("age_seconds")),
                    format_timestamp(connection.get("expires_at", "")),
                )

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
        table.clear()

        try:
            sessions = await self._screen.app.api_client.get_sessions()
            for session in sessions:
                table.add_row(
                    str(session.get("id", "")),
                    session.get("username", ""),
                    session.get("character_name", "") or "-",
                    session.get("client_type", "") or "-",
                    truncate(session.get("session_id", ""), 20),
                    format_timestamp(session.get("created_at", "")),
                    format_timestamp(session.get("last_activity", "")),
                    format_timestamp(session.get("expires_at", "")),
                )

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
        table.clear()

        try:
            messages = await self._screen.app.api_client.get_chat_messages(limit=100)
            for msg in messages:
                table.add_row(
                    str(msg.get("id", "")),
                    msg.get("username", ""),
                    msg.get("room", ""),
                    truncate(msg.get("message", ""), 50),
                    format_timestamp(msg.get("timestamp", "")),
                )

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
        table.clear()

        try:
            tables = await self._screen.app.api_client.get_tables()
            for table_info in tables:
                columns = ", ".join(table_info.get("columns", []))
                table.add_row(
                    table_info.get("name", ""),
                    columns,
                    str(table_info.get("row_count", 0)),
                )

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
        data_table.clear(columns=True)

        payload = await self._screen.app.api_client.get_table_rows(table_name, limit=limit)
        columns = payload.get("columns", [])
        rows = payload.get("rows", [])

        if not columns:
            self._screen.notify(f"No columns found for {table_name}", severity="warning")
            return

        data_table.add_columns(*columns)
        for row in rows:
            data_table.add_row(*[format_cell(value) for value in row])
