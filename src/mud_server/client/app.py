"""
Gradio-based web client for the MUD server.

This is the main entry point for the MUD client interface. It creates a
multi-tab Gradio interface by composing individual tab modules.

The application has been refactored into a modular structure:
    - api_client.py: All backend API communication
    - utils.py: Shared utility functions
    - static/styles.css: Centralized CSS styling
    - tabs/: Individual tab modules (login, game, settings, etc.)

Interface Structure:
    Tab 1: Login - User authentication
    Tab 2: Register - New account creation
    Tab 3: Game - Main gameplay interface with auto-refresh
    Tab 4: Settings - Password change and server control (admin only)
    Tab 5: Database - Admin database viewer (admin/superuser only)
    Tab 6: Ollama - Ollama server management and AI model control (admin/superuser only)
    Tab 7: Help - Game instructions and command reference

Key Features:
    - Per-user session state using gr.State (prevents cross-user contamination)
    - Auto-refresh timer (3 seconds) for real-time game updates
    - Role-based UI elements (admin features hidden for regular players)
    - Chat system with support for say, yell, and whisper commands
    - Modular architecture for easy maintenance and extensibility

State Management:
    Each user has their own gr.State dictionary containing:
    - session_id: UUID from successful login
    - username: Player's username
    - role: User role (player, worldbuilder, admin, superuser)
    - logged_in: Boolean login status

API Communication:
    All game operations communicate with the FastAPI backend via HTTP requests
    through the api_client module.

Port Configuration:
    --ui-port CLI argument: Specify exact port (no auto-discovery)
    MUD_UI_PORT env var: Specify preferred port (will auto-discover if in use)
    Default: 7860 (will auto-discover if in use)
"""

import os
import socket

import gradio as gr

from mud_server.client.api.auth import AuthAPIClient
from mud_server.client.tabs import (
    database_tab,
    game_tab,
    help_tab,
    login_tab,
    ollama_tab,
    register_tab,
    settings_tab,
)
from mud_server.client.ui.state import (
    build_logged_in_state,
    build_login_failed_state,
    clear_session_state,
    is_admin_role,
    update_session_state,
)
from mud_server.client.utils import create_session_state, load_css

# Create module-level API client instance for reuse
_auth_client = AuthAPIClient()


def login(username: str, password: str, session_state: dict) -> tuple:
    """
    Handle user login with password authentication.

    Sends credentials to backend via AuthAPIClient, stores session data on success,
    and returns updated UI state for tab visibility and user info display.

    This function wraps the new AuthAPIClient.login() method and uses UI state
    builders to maintain compatibility with the Gradio interface.

    Migration Notes:
        - Migrated from old api_client.py to new modular structure
        - Uses AuthAPIClient for authentication
        - Uses state builders (build_logged_in_state, build_login_failed_state)
        - Updates session_state using update_session_state helper
        - Returns tuple matching Gradio output expectations

    Args:
        username: Username to login with
        password: Plain text password
        session_state: User's session state dictionary

    Returns:
        Tuple of (session_state, login_result, clear_username, clear_password,
                  login_tab, register_tab, game_tab, settings_tab, db_tab, ollama_tab, help_tab)

    Examples:
        >>> session = {}
        >>> result = login("alice", "password123", session)
        >>> isinstance(result, tuple) and len(result) == 11
        True
    """
    # Call the new API client
    api_result = _auth_client.login(username, password)

    # Build UI state based on result
    if api_result["success"]:
        # Update session state with login data
        session_state = update_session_state(
            session_state,
            session_id=api_result["data"]["session_id"],
            username=api_result["data"]["username"],
            role=api_result["data"]["role"],
        )

        # Check if user has admin access
        has_admin_access = is_admin_role(api_result["data"]["role"])

        # Build and return logged-in UI state
        return build_logged_in_state(
            session_state,
            message=api_result["message"],
            has_admin_access=has_admin_access,
        )
    else:
        # Build and return login-failed UI state
        return build_login_failed_state(session_state, api_result["message"])


def logout(session_state: dict) -> tuple:
    """
    Handle user logout and clean up session state.

    Sends logout request to backend via AuthAPIClient, clears session data,
    and returns updated UI state to hide game tabs and show login tabs.

    This function wraps the new AuthAPIClient.logout() method and uses UI state
    builders to maintain compatibility with the Gradio interface.

    Migration Notes:
        - Migrated from old api_client.py to new modular structure
        - Uses AuthAPIClient for logout
        - Uses clear_session_state helper to reset session
        - Uses build_logged_out_state (via manual construction) for UI updates
        - Returns tuple matching Gradio output expectations

    Args:
        session_state: User's session state dictionary

    Returns:
        Tuple of (session_state, message, blank, login_tab, register_tab,
                  game_tab, settings_tab, db_tab, ollama_tab, help_tab)

    Examples:
        >>> session = {"session_id": "abc123", "logged_in": True}
        >>> result = logout(session)
        >>> isinstance(result, tuple) and len(result) == 10
        True
    """
    # Extract session_id from session state
    session_id = session_state.get("session_id")

    # Call the new API client
    api_result = _auth_client.logout(session_id=session_id)

    # Clear session state
    session_state = clear_session_state(session_state)

    # Build and return logged-out UI state
    # Format: (session_state, message, blank, tabs...)
    return (
        session_state,
        api_result["message"],
        "",  # blank field
        gr.update(visible=True),  # login tab
        gr.update(visible=True),  # register tab
        gr.update(visible=False),  # game tab
        gr.update(visible=False),  # settings tab
        gr.update(visible=False),  # database tab
        gr.update(visible=False),  # ollama tab
        gr.update(visible=False),  # help tab
    )


def create_interface():
    """
    Create and configure the complete Gradio web interface.

    Builds the entire multi-tab UI by composing individual tab modules.
    Each tab module is responsible for its own layout, components, and
    event handlers. This function handles only top-level integration and
    tab visibility control based on authentication state.

    Returns:
        gr.Blocks: Configured Gradio interface ready to launch
    """
    # Load CSS from external file
    custom_css = load_css("styles.css")

    with gr.Blocks(title="MUD Client", theme=gr.themes.Soft(), css=custom_css) as interface:
        gr.Markdown("# MUD Client")
        gr.Markdown("A simple Multi-User Dungeon client")

        # Session state (per-user)
        session_state = gr.State(create_session_state())

        with gr.Tabs():
            # Create all tabs
            (
                login_tab_component,
                login_btn,
                login_username_input,
                login_password_input,
                login_output,
            ) = login_tab.create()

            register_tab_component = register_tab.create()
            game_tab_component, game_logout_btn = game_tab.create(session_state)
            settings_tab_component = settings_tab.create(session_state)
            database_tab_component = database_tab.create(session_state)
            ollama_tab_component = ollama_tab.create(session_state)
            help_tab_component = help_tab.create()

        # Wire up login event handler
        login_btn.click(
            login,
            inputs=[login_username_input, login_password_input, session_state],
            outputs=[
                session_state,
                login_output,
                login_username_input,
                login_password_input,
                login_tab_component,
                register_tab_component,
                game_tab_component,
                settings_tab_component,
                database_tab_component,
                ollama_tab_component,
                help_tab_component,
            ],
        )

        # Wire up logout button to update tab visibility
        # This needs to be separate from the Game tab handler because tabs aren't defined yet there
        def logout_and_hide_tabs(session_st):
            """
            Handle logout button click and update tab visibility.

            This is a separate handler from the one in the Game tab because
            tab visibility components need to be wired at the top level after
            all tabs are defined. Calls logout() and extracts the relevant
            outputs for session state, message, and tab visibility updates.

            Returns:
                Tuple for Gradio outputs: (session_state, message, login_tab,
                register_tab, game_tab, settings_tab, database_tab, ollama_tab, help_tab)
            """
            result = logout(session_st)
            return (
                result[0],
                result[1],
                result[3],
                result[4],
                result[5],
                result[6],
                result[7],
                result[8],
                result[9],
            )

        game_logout_btn.click(
            logout_and_hide_tabs,
            inputs=[session_state],
            outputs=[
                session_state,
                login_output,
                login_tab_component,
                register_tab_component,
                game_tab_component,
                settings_tab_component,
                database_tab_component,
                ollama_tab_component,
                help_tab_component,
            ],
        )

    return interface


# ============================================================================
# PORT DISCOVERY
# ============================================================================
# These functions handle automatic port discovery for the Gradio UI client.
# This mirrors the API server's port discovery but uses the 7860-7899 range,
# which is the standard range for Gradio applications.
#
# Rationale for separate implementation (not shared with server.py):
# - Different default ports (7860 vs 8000)
# - Different port ranges to avoid conflicts
# - Keeps client and server modules independent
# - Allows running multiple instances without conflicts
# ============================================================================

# Default port for Gradio UI (standard Gradio default)
DEFAULT_UI_PORT = 7860

# Port range for UI auto-discovery (40 ports should be sufficient)
UI_PORT_RANGE_START = 7860
UI_PORT_RANGE_END = 7899


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """
    Check if a TCP port is available for binding on the specified host.

    This function is identical to the one in server.py but kept separate
    to maintain module independence. The Gradio UI client should be able
    to function without depending on the API server module.

    Technical Details:
        - Uses a TCP socket (SOCK_STREAM) for the availability check
        - Socket is automatically closed via context manager
        - Handles various OSError conditions (EADDRINUSE, EACCES, etc.)

    Args:
        port: TCP port number to check (1-65535)
        host: Host interface to check. Common values:
            - "0.0.0.0": All interfaces (default)
            - "127.0.0.1": Localhost only

    Returns:
        True if the port is available for binding, False otherwise

    Example:
        >>> is_port_available(7860)
        True  # Port 7860 is free for Gradio
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(
    preferred_port: int = DEFAULT_UI_PORT,
    host: str = "0.0.0.0",
    range_start: int = UI_PORT_RANGE_START,
    range_end: int = UI_PORT_RANGE_END,
) -> int | None:
    """
    Find an available TCP port for the Gradio UI, starting with preferred port.

    Implements sequential port scanning to find an available port:
    1. Try the preferred port first (usually 7860)
    2. If unavailable, scan 7860-7899 sequentially
    3. Return None if no ports available (caller handles error)

    Args:
        preferred_port: The first port to try. Defaults to 7860 (Gradio default).
        host: Host interface to check availability on. Defaults to "0.0.0.0".
        range_start: First port in scan range (inclusive). Defaults to 7860.
        range_end: Last port in scan range (inclusive). Defaults to 7899.

    Returns:
        int: An available port number within the range
        None: If no ports are available (all 40 ports in use)

    Example:
        >>> find_available_port(7860)
        7860  # Normal case - default port available

        >>> find_available_port(7860)  # 7860 in use
        7861  # Returns next available port
    """
    # Try preferred port first (common case - it's usually available)
    if is_port_available(preferred_port, host):
        return preferred_port

    # Sequential scan through the Gradio port range
    for port in range(range_start, range_end + 1):
        if port != preferred_port and is_port_available(port, host):
            return port

    # No ports available in range
    return None


# ============================================================================
# CLIENT STARTUP
# ============================================================================


def launch_client(
    host: str | None = None,
    port: int | None = None,
    auto_discover: bool = True,
) -> None:
    """
    Launch the Gradio web client with configurable host and port.

    This is the main entry point for running the Gradio-based web interface.
    It handles configuration resolution and implements automatic port discovery
    to avoid "address already in use" errors.

    Configuration Resolution Order:
        For both host and port, configuration is resolved in this priority:
        1. Explicit function parameter (highest priority)
        2. Environment variable (MUD_UI_HOST, MUD_UI_PORT)
        3. Default value (0.0.0.0:7860)

    Auto-Discovery Behavior:
        When auto_discover=True (default):
        - If port 7860 is in use, scans 7860-7899 for an available port
        - Prints a message when using an alternate port
        - Raises RuntimeError only if ALL ports in range are unavailable

        When auto_discover=False:
        - Fails immediately if the specified port is unavailable
        - Useful when port must match external configuration (proxy, etc.)

    Args:
        host: Network interface to bind to. Common values:
            - None: Use MUD_UI_HOST env var, or "0.0.0.0" (all interfaces)
            - "0.0.0.0": Accept connections from any network interface
            - "127.0.0.1": Accept only local connections (localhost)
        port: TCP port number for the web UI. Values:
            - None: Use MUD_UI_PORT env var, or 7860 (Gradio default)
            - Integer: Use this specific port (subject to auto_discover)
        auto_discover: Enable automatic port discovery. Defaults to True.

    Raises:
        RuntimeError: When auto_discover=True but no port is available in
            the 7860-7899 range.
        OSError: When auto_discover=False and the specified port is in use.

    Example:
        # Default configuration
        launch_client()  # Uses 0.0.0.0:7860 with auto-discovery

        # Custom port for development
        launch_client(port=8080)

        # Local development only
        launch_client(host="127.0.0.1")

    Note:
        This function blocks until the Gradio server is stopped.
        The interface is accessible at http://{host}:{port} once started.
    """
    # ========================================================================
    # CONFIGURATION RESOLUTION
    # ========================================================================

    # Resolve host: parameter > env var > default
    if host is None:
        host = os.getenv("MUD_UI_HOST", "0.0.0.0")

    # Resolve port: parameter > env var > default
    if port is None:
        port = int(os.getenv("MUD_UI_PORT", DEFAULT_UI_PORT))

    # ========================================================================
    # PORT AUTO-DISCOVERY
    # ========================================================================

    if auto_discover:
        available_port = find_available_port(port, host)

        if available_port is None:
            raise RuntimeError(
                f"No available port found in range {UI_PORT_RANGE_START}-{UI_PORT_RANGE_END}. "
                "This may indicate too many Gradio instances running."
            )

        if available_port != port:
            print(f"Port {port} is in use. Using port {available_port} instead.")

        port = available_port

    # ========================================================================
    # GRADIO STARTUP
    # ========================================================================

    print(f"Starting MUD client on {host}:{port}")

    # Create the Gradio interface
    interface = create_interface()

    # Launch the Gradio server
    # This blocks until the server is stopped (Ctrl+C or programmatic stop)
    interface.launch(
        server_name=host,
        server_port=port,
        share=False,  # Don't create a public Gradio link
        show_error=True,  # Display errors in the UI for debugging
    )


if __name__ == "__main__":
    launch_client()
