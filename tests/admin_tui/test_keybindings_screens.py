"""
Tests for screen-level keybinding handling in the Admin TUI.

These tests validate that screens interpret user keybinding overrides
via on_key without relying on dynamic bind() calls.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from textual import events
from textual.app import App

from mud_server.admin_tui.keybindings import KeyBindings
from mud_server.admin_tui.screens.dashboard import DashboardScreen
from mud_server.admin_tui.screens.login import LoginScreen


@dataclass
class _SessionState:
    """Minimal session state for dashboard tests."""

    is_authenticated: bool = True
    is_superuser: bool = True
    username: str = "tester"
    role: str = "superuser"


@dataclass
class _Config:
    """Minimal config for dashboard tests."""

    server_url: str = "http://localhost:8000"


class _APIClient:
    """Minimal API client stub used by dashboard tests."""

    def __init__(self) -> None:
        self.session = _SessionState()

    async def get_health(self) -> dict[str, object]:
        return {"status": "ok", "active_players": 0}


class _TestApp(App):
    """Minimal app wrapper to mount a single screen for testing."""

    def __init__(self, screen, keybindings: KeyBindings) -> None:
        super().__init__()
        self.keybindings = keybindings
        self.api_client = _APIClient()
        self.config = _Config()
        self._screen = screen

    async def on_mount(self) -> None:
        await self.push_screen(self._screen)


@pytest.mark.asyncio
async def test_dashboard_keybindings_dispatch() -> None:
    """Dashboard should dispatch configured keys to action methods."""
    keybindings = KeyBindings(
        bindings={
            "refresh": ["r"],
            "view_database": ["d"],
            "logout": ["l"],
            "quit": ["q"],
            "unknown": ["x"],
        }
    )

    screen = DashboardScreen()
    app = _TestApp(screen, keybindings)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        assert isinstance(active, DashboardScreen)

        calls: list[str] = []
        active.action_refresh = lambda: calls.append("refresh")  # type: ignore[method-assign]

        event = events.Key("r", "r")
        active.on_key(event)

        assert calls == ["refresh"]
        assert event._stop_propagation is True
        assert "x" not in getattr(active, "_keybindings_by_key", {})


@pytest.mark.asyncio
async def test_login_keybindings_dispatch() -> None:
    """Login screen should dispatch configured keys to action methods."""
    keybindings = KeyBindings(
        bindings={
            "quit": ["q"],
            "unknown": ["x"],
        }
    )

    screen = LoginScreen()
    app = _TestApp(screen, keybindings)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        assert isinstance(active, LoginScreen)

        calls: list[str] = []
        active.action_quit = lambda: calls.append("quit")  # type: ignore[method-assign]

        event = events.Key("q", "q")
        active.on_key(event)

        assert calls == ["quit"]
        assert event._stop_propagation is True
        assert "x" not in getattr(active, "_keybindings_by_key", {})
