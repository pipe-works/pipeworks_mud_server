"""
FastAPI backend server for the MUD.

This module initializes and configures the FastAPI application that serves as
the backend API for the Multi-User Dungeon (MUD) game. It sets up:
- CORS middleware for cross-origin requests from the Gradio frontend
- The game engine instance that handles all game logic
- All API route endpoints for player actions and admin functions

The server runs on port 8000 by default and accepts connections from any host
to allow network access from other machines. If the default port is in use,
the server will automatically find an available port in the 8000-8099 range.

Port Configuration:
    --port CLI argument: Specify exact port (no auto-discovery)
    MUD_PORT env var: Specify preferred port (will auto-discover if in use)
    Default: 8000 (will auto-discover if in use)
"""

import os
import socket

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mud_server.api.routes import register_routes
from mud_server.core.engine import GameEngine

# ============================================================================
# APPLICATION INITIALIZATION
# ============================================================================

# Initialize the FastAPI application with metadata
# This creates the main app instance that will handle all HTTP requests
app = FastAPI(title="MUD Server", version="0.1.0")

# ============================================================================
# MIDDLEWARE CONFIGURATION
# ============================================================================

# Add CORS (Cross-Origin Resource Sharing) middleware
# This allows the Gradio frontend (running on a different port) to make
# requests to this API server. In production, you should restrict
# allow_origins to specific domains instead of using "*" (all origins).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow requests from any origin (frontend can be on different port/host)
    allow_credentials=True,  # Allow cookies and authentication headers
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers in requests
)

# ============================================================================
# GAME ENGINE INITIALIZATION
# ============================================================================

# Create the game engine instance
# This is a singleton that manages all game state, including:
# - World data (rooms, items, exits)
# - Player actions (movement, inventory, chat)
# - Database connections for persistence
# The engine is passed to all route handlers that need game logic
engine = GameEngine()

# ============================================================================
# ROUTE REGISTRATION
# ============================================================================

# Register all API endpoints with the FastAPI app
# This includes routes for:
# - Authentication (login, register, logout)
# - Game commands (move, look, inventory, chat, whisper, yell)
# - Player management (change password)
# - Admin functions (user management, view logs, stop server)
register_routes(app, engine)

# ============================================================================
# PORT DISCOVERY
# ============================================================================

DEFAULT_PORT = 8000
PORT_RANGE_START = 8000
PORT_RANGE_END = 8099


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """
    Check if a port is available for binding.

    Args:
        port: Port number to check
        host: Host interface to check (default: all interfaces)

    Returns:
        True if port is available, False otherwise
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(
    preferred_port: int = DEFAULT_PORT,
    host: str = "0.0.0.0",
    range_start: int = PORT_RANGE_START,
    range_end: int = PORT_RANGE_END,
) -> int | None:
    """
    Find an available port, starting with the preferred port.

    If the preferred port is available, returns it. Otherwise, scans the
    specified range for the first available port.

    Args:
        preferred_port: First port to try (default: 8000)
        host: Host interface to check (default: all interfaces)
        range_start: Start of port range to scan (default: 8000)
        range_end: End of port range to scan (default: 8099)

    Returns:
        Available port number, or None if no port is available in range
    """
    # Try preferred port first
    if is_port_available(preferred_port, host):
        return preferred_port

    # Scan the range for an available port
    for port in range(range_start, range_end + 1):
        if port != preferred_port and is_port_available(port, host):
            return port

    return None


# ============================================================================
# SERVER STARTUP
# ============================================================================


def start_server(
    host: str | None = None,
    port: int | None = None,
    auto_discover: bool = True,
) -> None:
    """
    Start the MUD server with configurable host and port.

    Port resolution order:
    1. Explicit port parameter (if provided)
    2. MUD_PORT environment variable
    3. Default port (8000)

    If auto_discover is True and the chosen port is in use, the server will
    automatically find an available port in the 8000-8099 range.

    Args:
        host: Host interface to bind to. If None, uses MUD_HOST env var or "0.0.0.0"
        port: Port to bind to. If None, uses MUD_PORT env var or 8000
        auto_discover: If True, find available port if preferred port is in use.
            Set to False to fail immediately if port is unavailable.

    Raises:
        RuntimeError: If no available port is found when auto_discover is True
        OSError: If port is in use and auto_discover is False
    """
    import uvicorn

    # Resolve host
    if host is None:
        host = os.getenv("MUD_HOST", "0.0.0.0")

    # Resolve port
    if port is None:
        port = int(os.getenv("MUD_PORT", DEFAULT_PORT))

    # Find available port if needed
    if auto_discover:
        available_port = find_available_port(port, host)
        if available_port is None:
            raise RuntimeError(
                f"No available port found in range {PORT_RANGE_START}-{PORT_RANGE_END}"
            )
        if available_port != port:
            print(f"Port {port} is in use. Using port {available_port} instead.")
        port = available_port

    print(f"Starting MUD server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    # Only runs when this file is executed directly (not when imported)
    start_server()
