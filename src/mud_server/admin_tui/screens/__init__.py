"""
Screen components for PipeWorks Admin TUI.

This package contains the Textual Screen classes that make up the
different views of the admin interface.

Screens are full-window views that can be pushed/popped from the
application's screen stack.

Available Screens:
    LoginScreen: Authentication form for logging into the server.
    DashboardScreen: Main admin dashboard showing server status.
    CharactersScreen: Admin list view for all characters.
    CharacterDetailScreen: Placeholder detail view for a single character.
    DatabaseScreen: Database table viewer for superusers.
    CreateUserScreen: Admin form for creating new user accounts.
    UserDetailScreen: Admin detail view for a single user.
"""

from mud_server.admin_tui.screens.character_detail import CharacterDetailScreen
from mud_server.admin_tui.screens.characters import CharactersScreen
from mud_server.admin_tui.screens.create_user import CreateUserScreen
from mud_server.admin_tui.screens.dashboard import DashboardScreen
from mud_server.admin_tui.screens.database import DatabaseScreen
from mud_server.admin_tui.screens.login import LoginScreen
from mud_server.admin_tui.screens.user_detail import UserDetailScreen

__all__ = [
    "CharacterDetailScreen",
    "CharactersScreen",
    "CreateUserScreen",
    "DashboardScreen",
    "DatabaseScreen",
    "LoginScreen",
    "UserDetailScreen",
]
