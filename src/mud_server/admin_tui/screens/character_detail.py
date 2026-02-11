"""
Character detail screen for PipeWorks Admin TUI.

Placeholder view for future character management tooling.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class CharacterDetailScreen(Screen):
    """Placeholder character detail screen."""

    BINDINGS = [
        Binding("b", "back", "Back", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
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
                yield Static(f"ID: {self._character.get('id', '-')}")
                yield Static(f"Name: {self._character.get('name', '-')}")
                yield Static(f"User: {self._character.get('username', '-')}")
                yield Static(f"User ID: {self._character.get('user_id', '-')}")
                yield Static(
                    "Guest Created: " + ("Yes" if self._character.get("is_guest_created") else "No")
                )
                yield Static(
                    f"Created: {self._format_timestamp(self._character.get('created_at'))}"
                )
                yield Static(
                    f"Updated: {self._format_timestamp(self._character.get('updated_at'))}"
                )
        yield Footer()

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
