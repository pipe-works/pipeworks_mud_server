"""
Characters screen for PipeWorks Admin TUI.

Lists all characters with basic metadata and allows selection for details.
"""

from __future__ import annotations

from typing import Any

from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from mud_server.admin_tui.api.client import AuthenticationError
from mud_server.admin_tui.screens.character_detail import CharacterDetailScreen


class CharactersScreen(Screen):
    """Admin character list screen."""

    BINDINGS = [
        Binding("b", "back", "Back", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
    ]

    CSS = """
    CharactersScreen {
        layout: vertical;
    }

    .characters-container {
        height: 1fr;
        padding: 1 2;
    }

    DataTable {
        height: 1fr;
        width: 100%;
    }

    DataTable > .datatable--header {
        text-style: bold;
        background: $primary;
    }
    """

    def __init__(self) -> None:
        """Initialize state caches used for sorting and display."""
        super().__init__()
        self._characters_cache: list[dict[str, Any]] = []
        self._users_by_id: dict[int, str] = {}
        self._sort_state: tuple[int, bool] | None = None

    def compose(self) -> ComposeResult:
        """Compose the characters list layout."""
        yield Header()
        with Vertical(classes="characters-container"):
            yield Static("Characters", classes="summary-title")
            yield DataTable(id="table-characters")
        yield Footer()

    def on_mount(self) -> None:
        """Verify permissions, configure the table, and load data."""
        api_client = self.app.api_client
        if not api_client or not api_client.session.is_admin:
            self.notify("Admin access required", severity="error")
            self.app.pop_screen()
            return

        self._setup_table()
        self._apply_keybindings()
        self._load_characters()

    def _apply_keybindings(self) -> None:
        """Bind user-configured keys to local actions."""
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
            "sort",
            "back",
        ):
            for key in bindings.get_keys(action):
                self._keybindings_by_key.setdefault(key, action)

    def on_key(self, event: events.Key) -> None:
        """Translate configured keys to actions without global bindings."""
        bindings_map = getattr(self, "_keybindings_by_key", {})
        action = bindings_map.get(event.key)
        if not action:
            return

        handler = getattr(self, f"action_{action}", None)
        if not handler:
            return

        handler()
        event.stop()

    def _setup_table(self) -> None:
        """Define columns for the characters table."""
        table = self.query_one("#table-characters", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "ID",
            "Name",
            "User",
            "User ID",
            "Guest Created",
            "Created",
            "Updated",
        )

    @work(thread=False)
    async def _load_characters(self) -> None:
        """Load characters and resolve owning usernames for display."""
        table = self.query_one("#table-characters", DataTable)
        table.clear()

        try:
            # Build a lookup of user_id -> username so the list is readable.
            players = await self.app.api_client.get_players()
            self._users_by_id = {
                int(player.get("id")): player.get("username", "")
                for player in players
                if player.get("id") is not None
            }

            # Pull raw rows from the characters table to avoid API expansion here.
            payload = await self.app.api_client.get_table_rows("characters", limit=500)
            columns = payload.get("columns", [])
            rows = payload.get("rows", [])

            id_idx = columns.index("id") if "id" in columns else None
            user_idx = columns.index("user_id") if "user_id" in columns else None
            name_idx = columns.index("name") if "name" in columns else None
            guest_idx = columns.index("is_guest_created") if "is_guest_created" in columns else None
            created_idx = columns.index("created_at") if "created_at" in columns else None
            updated_idx = columns.index("updated_at") if "updated_at" in columns else None

            self._characters_cache = []
            for row in rows:
                user_id = row[user_idx] if user_idx is not None else None
                character = {
                    "id": row[id_idx] if id_idx is not None else None,
                    "name": row[name_idx] if name_idx is not None else "",
                    "user_id": user_id,
                    "username": self._users_by_id.get(int(user_id)) if user_id else "-",
                    "is_guest_created": bool(row[guest_idx]) if guest_idx is not None else False,
                    "created_at": row[created_idx] if created_idx is not None else None,
                    "updated_at": row[updated_idx] if updated_idx is not None else None,
                }
                self._characters_cache.append(character)

            self._sort_state = None
            self._render_characters_table(self._characters_cache)

        except AuthenticationError as exc:
            self.notify(f"Permission denied: {exc.detail}", severity="error")
        except Exception as exc:
            self.notify(f"Failed to load characters: {exc}", severity="error")

    def _render_characters_table(self, characters: list[dict[str, Any]]) -> None:
        """Render character rows into the table."""
        table = self.query_one("#table-characters", DataTable)
        table.clear()
        for character in characters:
            table.add_row(
                str(character.get("id", "")),
                character.get("name", ""),
                character.get("username", "-"),
                str(character.get("user_id", "-")) if character.get("user_id") else "-",
                "Yes" if character.get("is_guest_created") else "No",
                self._format_timestamp(character.get("created_at")),
                self._format_timestamp(character.get("updated_at")),
            )

    def action_cursor_up(self) -> None:
        """Move selection up one row."""
        table = self.query_one("#table-characters", DataTable)
        table.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move selection down one row."""
        table = self.query_one("#table-characters", DataTable)
        table.action_cursor_down()

    def action_cursor_left(self) -> None:
        """Move selection left one column."""
        table = self.query_one("#table-characters", DataTable)
        table.action_cursor_left()

    def action_cursor_right(self) -> None:
        """Move selection right one column."""
        table = self.query_one("#table-characters", DataTable)
        table.action_cursor_right()

    def action_select(self) -> None:
        """Open the detail screen for the selected character."""
        table = self.query_one("#table-characters", DataTable)
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

    def action_sort(self) -> None:
        """Sort the character list by the focused column."""
        table = self.query_one("#table-characters", DataTable)
        if not self._characters_cache or table.cursor_column is None:
            return

        column_index = int(table.cursor_column)
        previous = self._sort_state
        ascending = True
        if previous and previous[0] == column_index:
            ascending = not previous[1]

        sorted_chars = self._sort_characters(self._characters_cache, column_index, ascending)
        self._sort_state = (column_index, ascending)
        self._render_characters_table(sorted_chars)

    def action_back(self) -> None:
        """Return to the previous screen."""
        self.app.pop_screen()

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def _sort_characters(
        self, characters: list[dict[str, Any]], column_index: int, ascending: bool
    ) -> list[dict[str, Any]]:
        """Sort characters by a column index using stable, string-friendly keys."""
        column_keys = [
            "id",
            "name",
            "username",
            "user_id",
            "is_guest_created",
            "created_at",
            "updated_at",
        ]
        key_name = column_keys[column_index] if column_index < len(column_keys) else "id"

        def sort_key(item: dict[str, Any]) -> tuple[int, str]:
            value = item.get(key_name)
            if value is None:
                return (1, "")
            if isinstance(value, bool):
                return (0, "1" if value else "0")
            return (0, str(value).lower())

        return sorted(characters, key=sort_key, reverse=not ascending)

    def _format_timestamp(self, timestamp: str | None) -> str:
        """Format timestamps for compact display."""
        if not timestamp:
            return "-"
        if "." in timestamp:
            timestamp = timestamp.split(".")[0]
        return timestamp
