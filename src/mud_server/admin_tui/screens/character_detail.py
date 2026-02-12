"""
Character detail screen for PipeWorks Admin TUI.

Placeholder view for future character management tooling.
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class CharacterDetailScreen(Screen):
    """Placeholder character detail screen."""

    BINDINGS = [
        Binding("b", "back", "Back", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    CSS = """
    CharacterDetailScreen {
        layout: vertical;
    }

    .detail-container {
        height: 1fr;
        padding: 1 2;
    }

    .detail-box {
        border: solid $primary;
        padding: 1 2;
        height: auto;
    }

    .detail-label {
        color: $text;
    }
    """

    def __init__(self, character: dict[str, Any]) -> None:
        """Initialize with the character record chosen from a list view."""
        super().__init__()
        self._character = character

    def compose(self) -> ComposeResult:
        """Compose a placeholder detail view for a character."""
        yield Header()
        with Vertical(classes="detail-container"):
            yield Static("Character Detail (Placeholder)", classes="summary-title")
            with Vertical(classes="detail-box"):
                yield Static("", id="character-id", classes="detail-label")
                yield Static("", id="character-name", classes="detail-label")
                yield Static("", id="character-user", classes="detail-label")
                yield Static("", id="character-user-id", classes="detail-label")
                yield Static("", id="character-guest", classes="detail-label")
                yield Static("", id="character-created", classes="detail-label")
                yield Static("", id="character-updated", classes="detail-label")
        yield Footer()

    def on_mount(self) -> None:
        """Render initial fields and hydrate missing details if needed."""
        self._render_character(self._character)

        if self._needs_hydration(self._character):
            self._hydrate_character()

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

    def _render_character(self, character: dict[str, Any]) -> None:
        """Update the detail fields from the provided character dict."""
        self.query_one("#character-id", Static).update(f"ID: {character.get('id', '-')}")
        self.query_one("#character-name", Static).update(f"Name: {character.get('name', '-')}")
        self.query_one("#character-user", Static).update(f"User: {character.get('username', '-')}")
        self.query_one("#character-user-id", Static).update(
            f"User ID: {character.get('user_id', '-')}"
        )
        guest_flag = "Yes" if character.get("is_guest_created") else "No"
        self.query_one("#character-guest", Static).update(f"Guest Created: {guest_flag}")
        self.query_one("#character-created", Static).update(
            f"Created: {self._format_timestamp(character.get('created_at'))}"
        )
        self.query_one("#character-updated", Static).update(
            f"Updated: {self._format_timestamp(character.get('updated_at'))}"
        )

    def _needs_hydration(self, character: dict[str, Any]) -> bool:
        """Return True when core fields are missing and should be loaded."""
        required_keys = {"user_id", "username", "is_guest_created", "created_at", "updated_at"}
        return any(character.get(key) in (None, "", "-") for key in required_keys)

    @work(thread=False)
    async def _hydrate_character(self) -> None:
        """Fetch missing character details from the admin API."""
        api_client = self.app.api_client
        if not api_client or not api_client.session.is_admin:
            return

        character_id = self._character.get("id")
        if character_id is None:
            return

        payload = await api_client.get_table_rows("characters", limit=500)
        columns = payload.get("columns", [])
        rows = payload.get("rows", [])

        if "id" not in columns:
            return

        id_idx = columns.index("id")
        user_idx = columns.index("user_id") if "user_id" in columns else None
        name_idx = columns.index("name") if "name" in columns else None
        guest_idx = columns.index("is_guest_created") if "is_guest_created" in columns else None
        created_idx = columns.index("created_at") if "created_at" in columns else None
        updated_idx = columns.index("updated_at") if "updated_at" in columns else None

        row = next((row for row in rows if str(row[id_idx]) == str(character_id)), None)
        if row is None:
            return

        user_id = row[user_idx] if user_idx is not None else None
        username = "-"
        if user_id is not None:
            users = await api_client.get_players()
            for user in users:
                if user.get("id") == user_id:
                    username = user.get("username", "-")
                    break

        self._character = {
            **self._character,
            "name": row[name_idx] if name_idx is not None else self._character.get("name"),
            "user_id": user_id,
            "username": username,
            "is_guest_created": bool(row[guest_idx]) if guest_idx is not None else False,
            "created_at": row[created_idx] if created_idx is not None else None,
            "updated_at": row[updated_idx] if updated_idx is not None else None,
        }
        self._render_character(self._character)
