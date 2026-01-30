"""
Command-line interface for PipeWorks MUD Server.

Provides CLI commands for server management:
- init-db: Initialize the database schema
- create-superuser: Create a superuser account interactively or via environment variables
- run: Start the MUD server (API and web UI)

Usage:
    mud-server init-db
    mud-server create-superuser
    mud-server run [--port PORT] [--ui-port PORT] [--host HOST]

Environment Variables:
    MUD_ADMIN_USER: Username for superuser (used by init-db if set)
    MUD_ADMIN_PASSWORD: Password for superuser (used by init-db if set)
    MUD_HOST: Host to bind API server (default: 0.0.0.0)
    MUD_PORT: Port for API server (default: 8000, auto-discovers if in use)
    MUD_UI_HOST: Host to bind UI server (default: 0.0.0.0)
    MUD_UI_PORT: Port for UI server (default: 7860, auto-discovers if in use)
"""

import argparse
import getpass
import os
import sys


def get_superuser_credentials_from_env() -> tuple[str, str] | None:
    """
    Get superuser credentials from environment variables.

    Returns:
        Tuple of (username, password) if both MUD_ADMIN_USER and MUD_ADMIN_PASSWORD are set.
        None if either is missing.
    """
    username = os.environ.get("MUD_ADMIN_USER")
    password = os.environ.get("MUD_ADMIN_PASSWORD")

    if username and password:
        return username, password
    return None


def prompt_for_credentials() -> tuple[str, str]:
    """
    Interactively prompt for superuser credentials with password policy enforcement.

    This function guides the user through creating secure credentials by:
    1. Validating username length (2-20 characters)
    2. Displaying password requirements before input
    3. Validating password against the STANDARD security policy
    4. Requiring password confirmation

    The STANDARD password policy requires:
    - Minimum 12 characters
    - Not a commonly used password
    - No sequential characters (abc, 123)
    - No excessive repeated characters (aaa)

    Returns:
        Tuple of (username, password) that meet security requirements.

    Raises:
        SystemExit: If the user cancels (Ctrl+C) during input.

    See Also:
        mud_server.api.password_policy: Full policy configuration details.
    """
    from mud_server.api.password_policy import (
        PolicyLevel,
        get_password_requirements,
        validate_password_strength,
    )

    print("\n" + "=" * 60)
    print("CREATE SUPERUSER")
    print("=" * 60)

    # Get username
    while True:
        username = input("Username: ").strip()
        if len(username) < 2:
            print("Username must be at least 2 characters.")
            continue
        if len(username) > 20:
            print("Username must be at most 20 characters.")
            continue
        break

    # Display password requirements
    print("\n" + get_password_requirements(PolicyLevel.STANDARD))
    print()

    # Get password with policy validation and confirmation
    while True:
        password = getpass.getpass("Password: ")

        # Validate against password policy
        result = validate_password_strength(password, level=PolicyLevel.STANDARD)
        if not result.is_valid:
            print("\nPassword does not meet requirements:")
            for error in result.errors:
                print(f"  - {error}")
            print()
            continue

        # Show strength feedback
        if result.score >= 80:
            strength = "Excellent"
        elif result.score >= 60:
            strength = "Good"
        elif result.score >= 40:
            strength = "Fair"
        else:
            strength = "Weak"
        print(f"Password strength: {strength} ({result.score}/100)")

        # Show warnings if any
        if result.warnings:
            print("Suggestions for improvement:")
            for warning in result.warnings:
                print(f"  - {warning}")

        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("Passwords do not match. Try again.\n")
            continue
        break

    return username, password


def cmd_init_db(args: argparse.Namespace) -> int:
    """
    Initialize the database schema.

    If MUD_ADMIN_USER and MUD_ADMIN_PASSWORD environment variables are set,
    creates a superuser with those credentials. Otherwise, just creates the
    schema and prints instructions for creating a superuser.

    Returns:
        0 on success, 1 on error
    """
    from mud_server.db.database import init_database

    try:
        init_database()
        print("Database initialized successfully.")
        return 0
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        return 1


def cmd_create_superuser(args: argparse.Namespace) -> int:
    """
    Create a superuser account.

    Checks for MUD_ADMIN_USER and MUD_ADMIN_PASSWORD environment variables first.
    If not set, prompts interactively for credentials.

    Returns:
        0 on success, 1 on error
    """
    from mud_server.db.database import create_player_with_password, init_database, player_exists

    # Ensure database exists (skip superuser creation - we'll do it ourselves)
    init_database(skip_superuser=True)

    # Try environment variables first
    env_creds = get_superuser_credentials_from_env()

    if env_creds:
        username, password = env_creds
        print(f"Using credentials from environment variables for user '{username}'")
    else:
        # Check if running interactively
        if not sys.stdin.isatty():
            print(
                "Error: No credentials provided.\n"
                "Set MUD_ADMIN_USER and MUD_ADMIN_PASSWORD environment variables,\n"
                "or run interactively to be prompted for credentials.",
                file=sys.stderr,
            )
            return 1

        username, password = prompt_for_credentials()

    # Check if user already exists
    if player_exists(username):
        print(f"Error: User '{username}' already exists.", file=sys.stderr)
        return 1

    # Validate password against security policy
    # This is especially important for environment variable credentials
    # which bypass interactive validation
    from mud_server.api.password_policy import PolicyLevel, validate_password_strength

    result = validate_password_strength(password, level=PolicyLevel.STANDARD)
    if not result.is_valid:
        print("Error: Password does not meet security requirements:", file=sys.stderr)
        for error in result.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    # Create the superuser
    try:
        success = create_player_with_password(username, password, role="superuser")
        if success:
            print(f"\nSuperuser '{username}' created successfully.")
            return 0
        else:
            print(f"Error: Failed to create user '{username}'.", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error creating superuser: {e}", file=sys.stderr)
        return 1


# ============================================================================
# SERVER PROCESS FUNCTIONS
# ============================================================================
# These functions must be defined at module level (not inside cmd_run) because
# multiprocessing on macOS/Windows uses 'spawn' which pickles the target function.
# Local functions cannot be pickled, causing "Can't get local object" errors.
# ============================================================================


def _run_api_server(host: str | None, port: int | None) -> None:
    """
    Run the FastAPI server in a subprocess with auto-discovery.

    This function is called by multiprocessing.Process and must be defined at
    module level to be picklable. It imports and starts the API server with
    the provided host and port configuration, using auto-discovery if the
    specified port is in use.

    Args:
        host: Host interface to bind to (e.g., "0.0.0.0" for all interfaces,
              "127.0.0.1" for localhost only). If None, uses MUD_HOST env var
              or defaults to "0.0.0.0".
        port: Port number for the API server. If None, uses MUD_PORT env var
              or defaults to 8000. If the port is in use, auto-discovers an
              available port in the 8000-8099 range.

    Note:
        The import is done inside the function to avoid import cycles and to
        ensure the server module is loaded fresh in the subprocess.
    """
    from mud_server.api.server import start_server

    start_server(host=host, port=port)


def _run_api_server_on_port(host: str, port: int) -> None:
    """
    Run the FastAPI server on a specific port WITHOUT auto-discovery.

    This variant is used when the port has already been discovered and validated
    by the main process. It skips auto-discovery to avoid race conditions and
    ensures the server binds to exactly the specified port.

    This is the preferred function when running both API and UI together,
    as the main process discovers the port first and sets MUD_SERVER_URL
    before spawning the UI process.

    Args:
        host: Host interface to bind to. Must not be None.
        port: Port number to bind to. Must not be None and must be available.

    Raises:
        OSError: If the port is unexpectedly in use (should not happen if
                 the main process discovered it correctly).

    Note:
        auto_discover=False is critical here - we want to fail immediately
        if the port isn't available rather than silently binding to a
        different port that the UI client doesn't know about.
    """
    from mud_server.api.server import start_server

    start_server(host=host, port=port, auto_discover=False)


def _run_ui_client(host: str | None, port: int | None) -> None:
    """
    Run the Gradio UI client in a subprocess.

    This function is called by multiprocessing.Process and must be defined at
    module level to be picklable. It imports and launches the Gradio interface
    with the provided host and port configuration.

    Args:
        host: Host interface to bind to (e.g., "0.0.0.0" for all interfaces,
              "127.0.0.1" for localhost only). If None, uses MUD_UI_HOST env var
              or defaults to "0.0.0.0".
        port: Port number for the UI client. If None, uses MUD_UI_PORT env var
              or defaults to 7860. If the port is in use, auto-discovers an
              available port in the 7860-7899 range.

    Note:
        The import is done inside the function to avoid import cycles and to
        ensure the client module is loaded fresh in the subprocess.
    """
    from mud_server.admin_gradio.app import launch_client

    launch_client(host=host, port=port)


def cmd_run(args: argparse.Namespace) -> int:
    """
    Run the MUD server (both API and client).

    This is the main entry point for starting the MUD server. It initializes
    the database if needed, then starts the API server and optionally the
    Gradio UI client in parallel processes.

    Port Auto-Discovery:
        If the configured port is already in use, the server will automatically
        find an available port in a predefined range:
        - API server: 8000-8099
        - UI client: 7860-7899

        IMPORTANT: When both servers are started together, the API port is
        discovered first and communicated to the UI client via the MUD_SERVER_URL
        environment variable. This ensures the UI always knows where to find
        the API server, even when using auto-discovered ports.

    Configuration Priority:
        1. CLI arguments (--port, --ui-port, --host)
        2. Environment variables (MUD_PORT, MUD_UI_PORT, MUD_HOST, MUD_UI_HOST)
        3. Default values (8000 for API, 7860 for UI, 0.0.0.0 for host)

    Args:
        args: Parsed command-line arguments from argparse. Expected attributes:
            - port (int | None): API server port override
            - ui_port (int | None): UI server port override
            - host (str | None): Host interface to bind both servers
            - api_only (bool): If True, only start API server (no Gradio UI)

    Returns:
        0 on successful execution or clean shutdown (Ctrl+C)
        1 on error during startup

    Example:
        # Start with default ports
        mud-server run

        # Specify custom ports
        mud-server run --port 9000 --ui-port 8080

        # Start API server only
        mud-server run --api-only

    Note:
        Both servers run as separate processes using multiprocessing.Process.
        This allows them to run truly in parallel and handle their own signals.
        The main process waits for both to complete (join).
    """
    import multiprocessing

    from mud_server.api.server import find_available_port as find_api_port
    from mud_server.db.database import DB_PATH, init_database

    # ========================================================================
    # DATABASE INITIALIZATION
    # ========================================================================
    # Ensure the database exists before starting servers. This creates the
    # SQLite database file and all required tables if they don't exist.
    if not DB_PATH.exists():
        print("Database not found. Initializing...")
        init_database()

    # ========================================================================
    # CONFIGURATION EXTRACTION
    # ========================================================================
    # Extract port and host configuration from parsed arguments.
    # getattr with default None handles cases where args might not have
    # these attributes (e.g., when called programmatically).
    api_port = getattr(args, "port", None)
    ui_port = getattr(args, "ui_port", None)
    host = getattr(args, "host", None) or os.environ.get("MUD_HOST", "0.0.0.0")
    api_only = getattr(args, "api_only", False)

    # ========================================================================
    # API PORT DISCOVERY (BEFORE STARTING PROCESSES)
    # ========================================================================
    # Discover the actual API port BEFORE starting processes. This ensures
    # the UI client knows which port to connect to, even if auto-discovery
    # selects a different port than the default.
    #
    # Resolution order:
    # 1. CLI argument (--port)
    # 2. MUD_PORT environment variable
    # 3. Auto-discovered port in 8000-8099 range
    if api_port is None:
        api_port = int(os.environ.get("MUD_PORT", 8000))

    # Find an available port (may be different from api_port if it's in use)
    actual_api_port = find_api_port(api_port, host)
    if actual_api_port is None:
        print(
            "Error: No available port found for API server (8000-8099 all in use).", file=sys.stderr
        )
        return 1

    if actual_api_port != api_port:
        print(f"API port {api_port} is in use. Using port {actual_api_port} instead.")

    # ========================================================================
    # SET MUD_SERVER_URL FOR UI CLIENT
    # ========================================================================
    # Set the environment variable so the UI client knows where to connect.
    # This is critical for proper communication between the UI and API server.
    # Use localhost for the client connection (it's running on the same machine).
    api_url = f"http://localhost:{actual_api_port}"
    os.environ["MUD_SERVER_URL"] = api_url

    try:
        if api_only:
            # ================================================================
            # API-ONLY MODE
            # ================================================================
            # Run the API server directly in the main process without spawning
            # a subprocess. This is useful for development, debugging, or when
            # the Gradio UI is not needed (e.g., headless server deployment).
            # Pass auto_discover=False since we already found the port.
            _run_api_server_on_port(host, actual_api_port)
        else:
            # ================================================================
            # FULL SERVER MODE (API + UI)
            # ================================================================
            # Start both servers as separate processes. Using multiprocessing
            # ensures true parallelism and independent signal handling.
            #
            # Note: We pass the actual discovered port to the API server with
            # auto_discover=False to avoid double discovery. The UI client
            # reads MUD_SERVER_URL from the environment (set above).
            api_process = multiprocessing.Process(
                target=_run_api_server_on_port,
                args=(host, actual_api_port),
                name="mud-api-server",
            )
            ui_process = multiprocessing.Process(
                target=_run_ui_client,
                args=(host, ui_port),
                name="mud-ui-client",
            )

            # Start both processes
            api_process.start()
            ui_process.start()

            # Wait for both processes to complete. In normal operation, these
            # run indefinitely until interrupted (Ctrl+C) or terminated.
            api_process.join()
            ui_process.join()

        return 0

    except KeyboardInterrupt:
        # ====================================================================
        # GRACEFUL SHUTDOWN
        # ====================================================================
        # Handle Ctrl+C gracefully. The subprocesses should also receive
        # the interrupt signal and shut down on their own.
        print("\nServer stopped.")
        return 0

    except Exception as e:
        # ====================================================================
        # ERROR HANDLING
        # ====================================================================
        # Catch any unexpected errors during startup and report them.
        print(f"Error starting server: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="mud-server",
        description="PipeWorks MUD Server - A multiplayer text game engine",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init-db command
    init_parser = subparsers.add_parser(
        "init-db",
        help="Initialize the database schema",
        description=(
            "Initialize the database with required tables. "
            "If MUD_ADMIN_USER and MUD_ADMIN_PASSWORD are set, creates a superuser."
        ),
    )
    init_parser.set_defaults(func=cmd_init_db)

    # create-superuser command
    superuser_parser = subparsers.add_parser(
        "create-superuser",
        help="Create a superuser account",
        description=(
            "Create a superuser account. Uses MUD_ADMIN_USER and MUD_ADMIN_PASSWORD "
            "environment variables if set, otherwise prompts interactively."
        ),
    )
    superuser_parser.set_defaults(func=cmd_create_superuser)

    # run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run the MUD server",
        description=(
            "Start both the API server and Gradio client. "
            "If a port is in use, automatically finds an available port in the range."
        ),
    )
    run_parser.add_argument(
        "--port",
        "-p",
        type=int,
        help="API server port (default: 8000, or MUD_PORT env var). Auto-discovers if in use.",
    )
    run_parser.add_argument(
        "--ui-port",
        type=int,
        help="UI server port (default: 7860, or MUD_UI_PORT env var). Auto-discovers if in use.",
    )
    run_parser.add_argument(
        "--host",
        type=str,
        help="Host to bind servers to (default: 0.0.0.0, or MUD_HOST env var)",
    )
    run_parser.add_argument(
        "--api-only",
        action="store_true",
        help="Run only the API server (no Gradio UI)",
    )
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
