"""
FastAPI backend server for the MUD.

This module initializes and configures the FastAPI application that serves as
the backend API for the Multi-User Dungeon (MUD) game. It sets up:
- CORS middleware for cross-origin requests from the admin WebUI
- The game engine instance that handles all game logic
- All API route endpoints for player actions and admin functions

The server runs on port 8000 by default and accepts connections from any host
to allow network access from other machines. If the default port is in use,
the server will automatically find an available port in the 8000-8099 range.

Configuration:
    Server settings are loaded from config/server.ini with environment variable
    overrides. See mud_server.config for details.

    Key environment variables:
        MUD_HOST: Network interface to bind to
        MUD_PORT: Port number
        MUD_PRODUCTION: Enable production mode
        MUD_CORS_ORIGINS: Comma-separated allowed origins
"""

import asyncio
import socket
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mud_server.api.routes.register import register_routes
from mud_server.config import config, print_config_summary
from mud_server.core.engine import GameEngine
from mud_server.db import database
from mud_server.web.routes import register_web_routes

# ============================================================================
# LIFESPAN EVENTS
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle server startup and shutdown tasks.

    Startup:
        - Clears any stale sessions from previous runs to ensure a clean state.
        - These may exist if the server crashed or was killed without proper shutdown.

    Shutdown:
        - Currently no cleanup needed (sessions cleared on next startup).
    """
    # Startup: Remove expired sessions so stale tokens cannot be reused
    removed = database.cleanup_expired_sessions()
    if removed > 0:
        print(f"Removed {removed} expired session(s) from previous run")

    # Startup: Delete expired guest accounts.
    removed_visitors = database.cleanup_expired_guest_accounts()
    if removed_visitors > 0:
        print(f"Deleted {removed_visitors} expired guest account(s) on startup")

    async def temporary_account_sweeper() -> None:
        """Periodic cleanup for expired guest accounts."""
        while True:
            await asyncio.sleep(24 * 60 * 60)
            removed_temp = database.cleanup_expired_guest_accounts()
            if removed_temp > 0:
                print(f"Deleted {removed_temp} expired guest account(s)")

    sweeper_task = asyncio.create_task(temporary_account_sweeper())

    try:
        yield  # Server runs here
    finally:
        sweeper_task.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper_task

    # Shutdown: (nothing to do - sessions will be cleared on next startup)


# ============================================================================
# APPLICATION INITIALIZATION
# ============================================================================

# Determine docs URL based on configuration
# In production mode with docs_enabled=auto, docs are disabled for security
docs_url = "/docs" if config.docs_should_be_enabled else None
redoc_url = "/redoc" if config.docs_should_be_enabled else None

# Initialize the FastAPI application with metadata and lifespan handler
# This creates the main app instance that will handle all HTTP requests
app = FastAPI(
    title="MUD Server",
    version="0.3.4",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
)

# ============================================================================
# MIDDLEWARE CONFIGURATION
# ============================================================================

# Add CORS (Cross-Origin Resource Sharing) middleware
# Origins are configured in config/server.ini or via MUD_CORS_ORIGINS env var
# SECURITY: Never use "*" with allow_credentials=True in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.security.cors_origins,
    allow_credentials=config.security.cors_allow_credentials,
    allow_methods=config.security.cors_allow_methods,
    allow_headers=config.security.cors_allow_headers,
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
register_web_routes(app)

# ============================================================================
# PORT DISCOVERY
# ============================================================================
# These functions handle automatic port discovery when the default port is
# already in use (e.g., another server instance running). This prevents the
# common "address already in use" error and improves developer experience.
#
# Port Scanning Strategy:
# 1. Try the preferred/configured port first
# 2. If unavailable, scan sequentially through the defined range
# 3. Return None if no ports are available (caller handles the error)
#
# The range is intentionally limited (100 ports) to:
# - Avoid conflicts with well-known ports
# - Provide predictable behavior
# - Fail fast if something is seriously wrong (100 servers running?)
# ============================================================================

# Default port for the API server (standard for development servers)
DEFAULT_PORT = 8000

# Port range for auto-discovery (100 ports should be plenty)
PORT_RANGE_START = 8000
PORT_RANGE_END = 8099


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:  # nosec B104
    """
    Check if a TCP port is available for binding on the specified host.

    This function attempts to bind a socket to the given host:port combination.
    If the bind succeeds, the port is available. If it fails with OSError
    (typically EADDRINUSE), the port is already in use.

    Technical Details:
        - Uses a TCP socket (SOCK_STREAM) for the check
        - Sets SO_REUSEADDR to handle TIME_WAIT state from recently closed sockets
        - The socket is automatically closed via context manager
        - Works correctly even if another process is listening on a different
          interface (e.g., 127.0.0.1 vs 0.0.0.0)

    Args:
        port: TCP port number to check (1-65535)
        host: Host interface to check. Common values:
            - "0.0.0.0": All interfaces (default, most common)
            - "127.0.0.1": Localhost only
            - Specific IP: Check only that interface

    Returns:
        True if the port is available for binding, False otherwise

    Example:
        >>> is_port_available(8000)
        True  # Port 8000 is free
        >>> is_port_available(80)
        False  # Port 80 likely in use by web server
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            # Set SO_REUSEADDR to allow binding to a port in TIME_WAIT state
            # This matches uvicorn's behavior and prevents false negatives
            # after a server is killed (socket may linger in TIME_WAIT for ~60s)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Attempt to bind - this is the definitive test for availability
            sock.bind((host, port))
            return True
        except OSError:
            # OSError is raised for various binding failures:
            # - EADDRINUSE (98): Address already in use (by active listener)
            # - EACCES (13): Permission denied (ports < 1024 on Unix)
            # - EADDRNOTAVAIL (99): Cannot assign requested address
            return False


def find_available_port(
    preferred_port: int = DEFAULT_PORT,
    host: str = "0.0.0.0",  # nosec B104 - intentional for server binding
    range_start: int = PORT_RANGE_START,
    range_end: int = PORT_RANGE_END,
) -> int | None:
    """
    Find an available TCP port, starting with the preferred port.

    This function implements a simple port scanning algorithm:
    1. First, try the preferred port (most common case - it's usually free)
    2. If unavailable, scan sequentially through the range
    3. Skip the preferred port during the scan (already tried)

    The sequential scan ensures deterministic behavior - given the same
    system state, you'll always get the same port. This is important for
    automated testing and reproducible deployments.

    Args:
        preferred_port: The first port to try. Defaults to 8000.
            This is typically the user-configured or default port.
        host: Host interface to check availability on. Defaults to "0.0.0.0"
            (all interfaces). Use "127.0.0.1" for localhost-only binding.
        range_start: First port in the scan range (inclusive). Defaults to 8000.
        range_end: Last port in the scan range (inclusive). Defaults to 8099.

    Returns:
        int: An available port number within the range
        None: If no ports are available in the entire range

    Example:
        >>> # Normal case - preferred port is available
        >>> find_available_port(8000)
        8000

        >>> # Preferred port in use - finds next available
        >>> find_available_port(8000)  # 8000 in use
        8001

        >>> # All ports in use (unusual)
        >>> find_available_port(8000)  # 8000-8099 all in use
        None

    Note:
        There's a small race condition between checking and binding.
        Another process could grab the port between our check and the
        actual server startup. This is acceptable for development servers
        but should be handled in production deployments.
    """
    # Optimization: Try the preferred port first
    # In most cases (single developer, clean environment), this succeeds
    if is_port_available(preferred_port, host):
        return preferred_port

    # Sequential scan through the range
    # This ensures deterministic port selection (always picks lowest available)
    for port in range(range_start, range_end + 1):
        # Skip the preferred port (already tried above)
        if port != preferred_port and is_port_available(port, host):
            return port

    # No ports available in the entire range
    # This is unusual and likely indicates a system configuration issue
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
    Start the MUD API server with configurable host and port.

    This is the main entry point for running the FastAPI backend server.
    It handles configuration resolution from multiple sources and implements
    automatic port discovery when the preferred port is unavailable.

    Configuration Resolution Order:
        For both host and port, configuration is resolved in this priority:
        1. Explicit function parameter (highest priority)
        2. Environment variable (MUD_HOST, MUD_PORT)
        3. Config file (config/server.ini)
        4. Default value (0.0.0.0:8000)

        This allows flexible deployment: developers can use defaults, CI/CD
        can use environment variables, and CLI users can specify exact values.

    Auto-Discovery Behavior:
        When auto_discover=True (default):
        - If the configured port is in use, scans 8000-8099 for an available port
        - Prints a message when using an alternate port
        - Raises RuntimeError only if ALL ports in the range are unavailable

        When auto_discover=False:
        - Fails immediately with OSError if port is unavailable
        - Useful when you need a specific port (e.g., load balancer config)

    Args:
        host: Network interface to bind to. Common values:
            - None: Use config/env var, or "0.0.0.0" (all interfaces)
            - "0.0.0.0": Accept connections from any network interface
            - "127.0.0.1": Accept only local connections (localhost)
            - Specific IP: Bind to a specific network interface
        port: TCP port number to listen on. Values:
            - None: Use config/env var, or 8000
            - Integer: Use this specific port (subject to auto_discover)
        auto_discover: Enable automatic port discovery. Defaults to True.
            Set to False for production deployments where port must be exact.

    Raises:
        RuntimeError: When auto_discover=True but no port is available in
            the 8000-8099 range. This is unusual and indicates a serious
            system configuration issue.
        OSError: When auto_discover=False and the specified port is in use.
            The error message will include details about the conflict.

    Example:
        # Default configuration (most common)
        start_server()  # Uses 0.0.0.0:8000 with auto-discovery

        # Explicit port for development
        start_server(port=9000)  # Uses 0.0.0.0:9000

        # Production deployment (fail if port unavailable)
        start_server(port=8000, auto_discover=False)

        # Local development only
        start_server(host="127.0.0.1")

    Note:
        This function blocks until the server is stopped (Ctrl+C or signal).
        It should typically be called in the main thread or a dedicated process.
    """
    import uvicorn

    # ========================================================================
    # CONFIGURATION RESOLUTION
    # ========================================================================

    # Print configuration summary at startup
    print_config_summary()

    # Resolve host: parameter > config (which includes env var override)
    if host is None:
        host = config.server.host

    # Resolve port: parameter > config (which includes env var override)
    if port is None:
        port = config.server.port

    # ========================================================================
    # PORT AUTO-DISCOVERY
    # ========================================================================

    if auto_discover:
        available_port = find_available_port(port, host)

        # Handle case where no ports are available (very unusual)
        if available_port is None:
            raise RuntimeError(
                f"No available port found in range {PORT_RANGE_START}-{PORT_RANGE_END}. "
                "This may indicate too many server instances running or a system issue."
            )

        # Inform user when using an alternate port
        if available_port != port:
            print(f"Port {port} is in use. Using port {available_port} instead.")

        port = available_port

    # ========================================================================
    # SERVER STARTUP
    # ========================================================================

    print(f"Starting MUD server on {host}:{port}")

    # Run uvicorn ASGI server
    # This blocks until the server is stopped (Ctrl+C, signal, or programmatic stop)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    # Only runs when this file is executed directly (not when imported)
    start_server()
