"""
Tests for kick target resolution on the database screen.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from textual.app import App
from textual.widgets import DataTable, TabbedContent

from mud_server.admin_tui.keybindings import KeyBindings
from mud_server.admin_tui.screens.database import DatabaseScreen


@dataclass
class _SessionState:
    is_superuser: bool = True


class _APIClient:
    def __init__(self) -> None:
        self.session = _SessionState()

    async def get_tables(self):
        return []

    async def get_players(self):
        return []

    async def get_player_locations(self):
        return []

    async def get_connections(self):
        return []

    async def get_sessions(self):
        return []

    async def get_chat_messages(self, limit: int = 100):
        return []

    async def get_table_rows(self, table_name: str, limit: int = 100):
        return {"columns": [], "rows": []}


class _TestApp(App):
    def __init__(self, screen: DatabaseScreen) -> None:
        super().__init__()
        self.api_client = _APIClient()
        self.keybindings = KeyBindings.load(path=None)
        self._screen = screen

    async def on_mount(self) -> None:
        await self.push_screen(self._screen)


@pytest.mark.asyncio
async def test_get_kick_target_from_connections_tab() -> None:
    screen = DatabaseScreen()
    app = _TestApp(screen)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        assert isinstance(active, DatabaseScreen)
        active._auto_refresh_timer.stop()

        tabs = active.query_one("#table-tabs", TabbedContent)
        tabs.active = "tab-connections"

        table = active.query_one("#table-connections", DataTable)
        table.add_row("user1", "tui", "session-1", "2026-02-05 12:00:00", "00:00:30", "-")

        target = active.get_selected_session_target()
        assert target == ("user1", "session-1")


@pytest.mark.asyncio
async def test_get_kick_target_from_sessions_tab() -> None:
    screen = DatabaseScreen()
    app = _TestApp(screen)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        assert isinstance(active, DatabaseScreen)
        active._auto_refresh_timer.stop()

        tabs = active.query_one("#table-tabs", TabbedContent)
        tabs.active = "tab-sessions"

        table = active.query_one("#table-sessions", DataTable)
        table.add_row(
            "1",
            "user2",
            "browser",
            "session-2",
            "2026-02-05 12:00:00",
            "2026-02-05 12:01:00",
            "-",
        )

        target = active.get_selected_session_target()
        assert target == ("user2", "session-2")
