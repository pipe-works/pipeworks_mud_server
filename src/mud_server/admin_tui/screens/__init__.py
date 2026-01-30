"""
Screen components for PipeWorks Admin TUI.

This package contains the Textual Screen classes that make up the
different views of the admin interface.

Screens are full-window views that can be pushed/popped from the
application's screen stack.

Available Screens:
    LoginScreen: Authentication form for logging into the server.
    DashboardScreen: Main admin dashboard showing server status.
"""

from mud_server.admin_tui.screens.dashboard import DashboardScreen
from mud_server.admin_tui.screens.login import LoginScreen

__all__ = [
    "DashboardScreen",
    "LoginScreen",
]
