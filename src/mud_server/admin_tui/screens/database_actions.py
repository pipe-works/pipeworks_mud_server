"""
Action helpers for the admin database screen.

This module keeps the DatabaseScreen focused on orchestration by
encapsulating user/session actions and UI flows (modals, selection,
error handling) in a dedicated helper.
"""

from __future__ import annotations

from typing import Any

from textual.widget import SkipAction
from textual.widgets import DataTable

from mud_server.admin_tui.screens.character_detail import CharacterDetailScreen
from mud_server.admin_tui.screens.database_modals import ConfirmKickScreen, ConfirmUserRemovalScreen
from mud_server.admin_tui.screens.user_detail import UserDetailScreen


class DatabaseActions:
    """
    Encapsulate user/session actions for DatabaseScreen.

    The helper keeps UI flows (confirmations, selection resolution, refresh)
    in one place so new actions can be added without bloating the screen.
    """

    def __init__(self, screen: Any) -> None:
        """Bind to the owning DatabaseScreen instance."""
        self._screen = screen

    def open_user_detail(self) -> None:
        """
        Open user detail screen for the currently selected user row.

        Uses the cached users list from the UsersTab to avoid extra API calls.
        """
        table = self._screen.query_one("#table-players", DataTable)
        selected_row = table.get_row_at(table.cursor_row)
        if not selected_row:
            return

        user_id = str(selected_row[0])
        if not user_id:
            return

        user = self._screen._tabs["users"].resolve_user(user_id)
        if not user:
            self._screen.notify("Unable to resolve user details", severity="warning")
            return

        self._screen.app.push_screen(UserDetailScreen(user=user))

    def open_character_detail_from_locations(self) -> None:
        """
        Open character detail for the selected character location row.

        Character Location rows only provide id/name, so the detail screen
        hydrates missing fields on mount.
        """
        table = self._screen.query_one("#table-player-locations", DataTable)
        selected_row = table.get_row_at(table.cursor_row)
        if not selected_row:
            return

        self._screen.app.push_screen(
            CharacterDetailScreen(
                character={
                    "id": str(selected_row[0]),
                    "name": str(selected_row[1]) if len(selected_row) > 1 else "",
                }
            )
        )

    async def kick_selected(self) -> None:
        """
        Prompt and kick the selected session from the connections/sessions table.

        Handles modal confirmation, permission errors, and table refreshes.
        """
        target = self._screen.get_selected_session_target()
        if not target:
            self._screen.notify("Select a session to kick", severity="warning")
            return

        username, session_id = target
        if username == (self._screen.app.api_client.session.username or ""):
            self._screen.notify("Cannot kick your own session", severity="warning")
            return

        result = await self._screen.app.push_screen_wait(
            ConfirmKickScreen(username=username, session_id=session_id)
        )
        if not result:
            return

        try:
            response = await self._screen.app.api_client.kick_session(
                target_username=username, target_session_id=session_id
            )
        except Exception as exc:  # pragma: no cover - UI feedback path
            self._screen.notify(f"Failed to kick session: {exc}", severity="error")
            return

        if response.get("success"):
            self._screen.notify("Session disconnected", severity="success")
            self._screen._load_connections()
            self._screen._load_sessions()
            return

        self._screen.notify(response.get("message", "Failed to kick session"), severity="error")

    async def remove_selected_user(self) -> None:
        """
        Prompt and remove the selected user (deactivate or delete).

        Uses the confirmation modal and refreshes user-related tables.
        """
        target = self._screen.get_selected_user_target()
        if not target:
            self._screen.notify("Select a user to remove", severity="warning")
            return

        username, role = target
        if username == (self._screen.app.api_client.session.username or ""):
            self._screen.notify("Cannot remove your own account", severity="warning")
            return

        action = await self._screen.app.push_screen_wait(
            ConfirmUserRemovalScreen(username=username, role=role)
        )
        if not action:
            return

        try:
            response = await self._screen.app.api_client.manage_user(username, action)
        except Exception as exc:  # pragma: no cover - UI feedback path
            self._screen.notify(f"Failed to update user: {exc}", severity="error")
            return

        if not response.get("success"):
            self._screen.notify(response.get("message", "Failed to update user"), severity="error")
            return

        self._screen.notify(response.get("message", "User updated"), severity="success")
        self._screen._load_players()
        self._screen._load_player_locations()

    def safe_cursor_left(self) -> None:
        """
        Move cursor left without crashing if horizontal scroll is disabled.

        Textual raises SkipAction when horizontal scrolling is disabled.
        """
        table = self._screen.get_active_table()
        if not table:
            return
        try:
            table.action_cursor_left()
        except SkipAction:
            return

    def safe_cursor_right(self) -> None:
        """
        Move cursor right without crashing if horizontal scroll is disabled.

        Textual raises SkipAction when horizontal scrolling is disabled.
        """
        table = self._screen.get_active_table()
        if not table:
            return
        try:
            table.action_cursor_right()
        except SkipAction:
            return
