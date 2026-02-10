"""
Tests for CreateUserScreen behavior.
"""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Static

from mud_server.admin_tui.keybindings import KeyBindings
from mud_server.admin_tui.screens.create_user import ROLE_DESCRIPTIONS, CreateUserScreen


class _TestApp(App):
    def __init__(self, screen: CreateUserScreen) -> None:
        super().__init__()
        self.api_client = None
        self.keybindings = KeyBindings.load(path=None)
        self._screen = screen

    async def on_mount(self) -> None:
        await self.push_screen(self._screen)


@pytest.mark.asyncio
async def test_role_description_defaults_to_first_role() -> None:
    screen = CreateUserScreen(allowed_roles=["player", "worldbuilder"])
    app = _TestApp(screen)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        description = active.query_one("#role-description", Static).content
        assert description == ROLE_DESCRIPTIONS["player"]


@pytest.mark.asyncio
async def test_role_description_updates() -> None:
    screen = CreateUserScreen(allowed_roles=["player", "worldbuilder"])
    app = _TestApp(screen)

    async with app.run_test() as pilot:
        active = pilot.app.screen
        active._update_role_description("worldbuilder")
        description = active.query_one("#role-description", Static).content
        assert description == ROLE_DESCRIPTIONS["worldbuilder"]
