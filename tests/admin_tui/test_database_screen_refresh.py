"""
Tests for database screen auto-refresh behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from textual.app import App
from textual.widgets import TabbedContent

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
async def test_refresh_active_tab_players() -> None:
    screen = DatabaseScreen()
    app = _TestApp(screen)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        assert isinstance(active, DatabaseScreen)
        active._auto_refresh_timer.stop()

        calls: list[str] = []
        active._load_players = lambda: calls.append("players")

        tabs = active.query_one("#table-tabs", TabbedContent)
        tabs.active = "tab-players"

        active._refresh_active_tab()
        assert calls == ["players"]


@pytest.mark.asyncio
async def test_refresh_active_tab_worlds() -> None:
    screen = DatabaseScreen()
    app = _TestApp(screen)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        assert isinstance(active, DatabaseScreen)
        active._auto_refresh_timer.stop()

        calls: list[str] = []
        active._load_worlds = lambda: calls.append("worlds")

        tabs = active.query_one("#table-tabs", TabbedContent)
        tabs.active = "tab-worlds"

        active._refresh_active_tab()
        assert calls == ["worlds"]


@pytest.mark.asyncio
async def test_refresh_table_data_uses_active_table() -> None:
    screen = DatabaseScreen()
    app = _TestApp(screen)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        assert isinstance(active, DatabaseScreen)
        active._auto_refresh_timer.stop()

        calls: list[str] = []
        active._load_table_data = lambda name: calls.append(name)

        active._active_table_name = "players"
        tabs = active.query_one("#table-tabs", TabbedContent)
        tabs.active = "tab-table-data"

        active._refresh_active_tab()
        assert calls == ["players"]


@pytest.mark.asyncio
async def test_refresh_table_data_no_selection() -> None:
    screen = DatabaseScreen()
    app = _TestApp(screen)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        assert isinstance(active, DatabaseScreen)
        active._auto_refresh_timer.stop()

        calls: list[str] = []
        active._load_table_data = lambda name: calls.append(name)

        active._active_table_name = None
        tabs = active.query_one("#table-tabs", TabbedContent)
        tabs.active = "tab-table-data"

        active._refresh_active_tab()
        assert calls == []
