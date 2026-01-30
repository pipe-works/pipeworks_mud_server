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
    Interactively prompt for superuser credentials.

    Returns:
        Tuple of (username, password)

    Raises:
        SystemExit: If passwords don't match or validation fails
    """
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

    # Get password with confirmation
    while True:
        password = getpass.getpass("Password: ")
        if len(password) < 8:
            print("Password must be at least 8 characters.")
            continue

        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("Passwords do not match. Try again.")
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

    # Validate password length
    if len(password) < 8:
        print("Error: Password must be at least 8 characters.", file=sys.stderr)
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


def cmd_run(args: argparse.Namespace) -> int:
    """
    Run the MUD server (both API and client).

    Supports configurable ports via CLI arguments or environment variables.
    If a port is in use, automatically finds an available port in the range.

    Args:
        args: Parsed arguments containing:
            - port: API server port (optional)
            - ui_port: UI server port (optional)
            - host: Host to bind to (optional)
            - api_only: Run only the API server (optional)

    Returns:
        0 on success, 1 on error
    """
    import multiprocessing

    from mud_server.db.database import DB_PATH, init_database

    # Initialize database if it doesn't exist
    if not DB_PATH.exists():
        print("Database not found. Initializing...")
        init_database()

    # Get port/host configuration from args
    api_port = getattr(args, "port", None)
    ui_port = getattr(args, "ui_port", None)
    host = getattr(args, "host", None)
    api_only = getattr(args, "api_only", False)

    def run_api_server():
        """Run the API server in a subprocess."""
        from mud_server.api.server import start_server

        start_server(host=host, port=api_port)

    def run_ui_client():
        """Run the Gradio UI client in a subprocess."""
        from mud_server.client.app import launch_client

        launch_client(host=host, port=ui_port)

    try:
        if api_only:
            # Run only the API server
            run_api_server()
        else:
            # Run both API server and UI client in parallel
            api_process = multiprocessing.Process(target=run_api_server)
            ui_process = multiprocessing.Process(target=run_ui_client)

            api_process.start()
            ui_process.start()

            # Wait for both processes
            api_process.join()
            ui_process.join()

        return 0
    except KeyboardInterrupt:
        print("\nServer stopped.")
        return 0
    except Exception as e:
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
