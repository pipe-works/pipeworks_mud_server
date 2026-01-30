"""
PipeWorks Admin TUI - Terminal User Interface for MUD Server Administration.

This package provides a Textual-based terminal interface for administering
the PipeWorks MUD server. It is designed for use over SSH connections,
running in tmux sessions on remote servers.

The TUI communicates with the MUD server via its REST API, making it
completely decoupled from the server implementation.

Example:
    # Run the admin TUI
    pipeworks-admin-tui --server http://localhost:8000

    # Or with environment variables
    MUD_SERVER_URL=http://10.0.0.1:8000 pipeworks-admin-tui
"""

from mud_server.admin_tui.app import AdminApp, main
from mud_server.admin_tui.config import Config

__all__ = [
    "AdminApp",
    "Config",
    "main",
]

__version__ = "0.1.0"
