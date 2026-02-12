"""
User detail screen for PipeWorks Admin TUI.

Displays account metadata and a list of characters owned by the user.
"""

from __future__ import annotations

from typing import Any

from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widget import SkipAction
from textual.widgets import DataTable, Footer, Header, Static

from mud_server.admin_tui.api.client import AuthenticationError
from mud_server.admin_tui.screens.character_detail import CharacterDetailScreen


class UserDetailScreen(Screen):
    """
    User account detail screen.

    Shows user metadata plus characters owned by the user.
    """

    BINDINGS = [
        Binding("b", "back", "Back", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    CSS = """
    UserDetailScreen {
        layout: vertical;
    }

    .detail-container {
        height: 1fr;
        padding: 1 2;
    }

    .summary-box {
        border: solid $primary;
        padding: 1 2;
        height: auto;
        margin-bottom: 1;
    }

    .summary-row {
        height: auto;
    }

    .summary-label {
        width: 18;
        color: $text-muted;
    }

    .summary-value {
        color: $text;
    }

    .characters-panel {
        height: 1fr;
    }

    DataTable {
        height: 1fr;
        width: 100%;
    }
    """

    def __init__(self, user: dict[str, Any]) -> None:
        """Initialize with the user record selected from the users table."""
        super().__init__()
        self._user = user
        self._characters_cache: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        """Compose the user summary and character list layout."""
        yield Header()

        with Vertical(classes="detail-container"):
            yield Static(f"User: {self._user.get('username', '-')}", classes="summary-title")

            with Vertical(classes="summary-box"):
                yield self._build_summary_row("User ID", str(self._user.get("id", "-")))
                yield self._build_summary_row("Role", self._user.get("role", "-"))
                yield self._build_summary_row("Origin", self._user.get("account_origin", "-"))
                yield self._build_summary_row(
                    "Active", "Yes" if self._user.get("is_active", False) else "No"
                )
                yield self._build_summary_row(
                    "Guest", "Yes" if self._user.get("is_guest", False) else "No"
                )
                yield self._build_summary_row(
                    "Guest Expires", self._format_timestamp(self._user.get("guest_expires_at"))
                )
                yield self._build_summary_row(
                    "Tombstoned", self._format_timestamp(self._user.get("tombstoned_at"))
                )
                yield self._build_summary_row(
                    "Created", self._format_timestamp(self._user.get("created_at"))
                )
                yield self._build_summary_row(
                    "Last Login", self._format_timestamp(self._user.get("last_login"))
                )

            with Vertical(classes="characters-panel"):
                yield Static("Characters", classes="summary-title")
                yield DataTable(id="table-user-characters")

        yield Footer()

    def _build_summary_row(self, label: str, value: str) -> Horizontal:
        """Build a labeled summary row for the user metadata panel."""
        return Horizontal(
            Static(f"{label}:", classes="summary-label"),
            Static(value or "-", classes="summary-value"),
            classes="summary-row",
        )

    def on_mount(self) -> None:
        """Validate permissions and load the user's character list."""
        api_client = self.app.api_client
        if not api_client or not api_client.session.is_admin:
            self.notify("Admin access required", severity="error")
            self.app.pop_screen()
            return

        self._setup_characters_table()
        self._apply_keybindings()
        self._load_characters()

    def _apply_keybindings(self) -> None:
        """Bind configured keys for table navigation and actions."""
        bindings = getattr(self.app, "keybindings", None)
        if not bindings:
            return

        self._keybindings_by_key: dict[str, str] = {}
        for action in (
            "cursor_up",
            "cursor_down",
            "cursor_left",
            "cursor_right",
            "select",
            "back",
        ):
            for key in bindings.get_keys(action):
                self._keybindings_by_key.setdefault(key, action)

    def on_key(self, event: events.Key) -> None:
        """Translate configured keys to local actions."""
        bindings_map = getattr(self, "_keybindings_by_key", {})
        action = bindings_map.get(event.key)
        if not action:
            return

        handler = getattr(self, f"action_{action}", None)
        if not handler:
            return

        handler()
        event.stop()

    def _setup_characters_table(self) -> None:
        """Define columns for the user's characters list."""
        table = self.query_one("#table-user-characters", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("ID", "Name", "Guest Created", "Created", "Updated")

    @work(thread=False)
    async def _load_characters(self) -> None:
        """Load characters for the current user via the generic table API."""
        table = self.query_one("#table-user-characters", DataTable)
        selected_key = None
        selected_index = table.cursor_row
        if table.row_count:
            row = table.get_row_at(table.cursor_row)
            if row and row[0] is not None:
                selected_key = str(row[0])

        table.clear()

        try:
            # Fetch the raw characters table so we can filter by user_id locally.
            payload = await self.app.api_client.get_table_rows("characters", limit=500)
            columns = payload.get("columns", [])
            rows = payload.get("rows", [])

            if "user_id" not in columns:
                self.notify("Characters table missing user_id", severity="error")
                return

            user_id_idx = columns.index("user_id")
            id_idx = columns.index("id") if "id" in columns else None
            name_idx = columns.index("name") if "name" in columns else None
            guest_idx = columns.index("is_guest_created") if "is_guest_created" in columns else None
            created_idx = columns.index("created_at") if "created_at" in columns else None
            updated_idx = columns.index("updated_at") if "updated_at" in columns else None

            self._characters_cache = []
            user_id = self._user.get("id")
            try:
                user_id = int(user_id) if user_id is not None else None
            except (TypeError, ValueError):
                user_id = None

            for row in rows:
                if user_id is None or row[user_id_idx] != user_id:
                    continue

                character = {
                    "id": row[id_idx] if id_idx is not None else None,
                    "name": row[name_idx] if name_idx is not None else "",
                    "user_id": self._user.get("id"),
                    "username": self._user.get("username"),
                    "is_guest_created": bool(row[guest_idx]) if guest_idx is not None else False,
                    "created_at": row[created_idx] if created_idx is not None else None,
                    "updated_at": row[updated_idx] if updated_idx is not None else None,
                }
                self._characters_cache.append(character)

            key_map: dict[str, int] = {}
            for character in self._characters_cache:
                row = (
                    str(character.get("id", "")),
                    character.get("name", ""),
                    "Yes" if character.get("is_guest_created") else "No",
                    self._format_timestamp(character.get("created_at")),
                    self._format_timestamp(character.get("updated_at")),
                )
                table.add_row(*row)
                if row[0]:
                    key_map[str(row[0])] = table.row_count - 1

            if selected_key and selected_key in key_map:
                table.move_cursor(
                    row=key_map[selected_key], column=table.cursor_column, animate=False
                )
            elif 0 <= selected_index < table.row_count:
                table.move_cursor(row=selected_index, column=table.cursor_column, animate=False)

        except AuthenticationError as exc:
            self.notify(f"Permission denied: {exc.detail}", severity="error")
        except Exception as exc:
            self.notify(f"Failed to load characters: {exc}", severity="error")

    def action_cursor_up(self) -> None:
        """Move selection up one row."""
        table = self.query_one("#table-user-characters", DataTable)
        table.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move selection down one row."""
        table = self.query_one("#table-user-characters", DataTable)
        table.action_cursor_down()

    def action_cursor_left(self) -> None:
        """Move selection left one column."""
        table = self.query_one("#table-user-characters", DataTable)
        try:
            table.action_cursor_left()
        except SkipAction:
            return

    def action_cursor_right(self) -> None:
        """Move selection right one column."""
        table = self.query_one("#table-user-characters", DataTable)
        try:
            table.action_cursor_right()
        except SkipAction:
            return

    def action_select(self) -> None:
        """Open the selected character in a detail placeholder."""
        table = self.query_one("#table-user-characters", DataTable)
        selected = table.get_row_at(table.cursor_row)
        if not selected:
            return

        character_id = str(selected[0])
        character = next(
            (entry for entry in self._characters_cache if str(entry.get("id")) == character_id),
            None,
        )
        if not character:
            return

        self.app.push_screen(CharacterDetailScreen(character=character))

    def action_back(self) -> None:
        """Return to the previous screen."""
        self.app.pop_screen()

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def _format_timestamp(self, timestamp: str | None) -> str:
        """Format timestamps for compact display."""
        if not timestamp:
            return "-"
        if "." in timestamp:
            timestamp = timestamp.split(".")[0]
        return timestamp
