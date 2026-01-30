"""
Command-line interface for PipeWorks MUD Server.

Provides CLI commands for server management:
- init-db: Initialize the database schema
- create-superuser: Create a superuser account interactively or via environment variables

Usage:
    mud-server init-db
    mud-server create-superuser
    mud-server run

Environment Variables:
    MUD_ADMIN_USER: Username for superuser (used by init-db if set)
    MUD_ADMIN_PASSWORD: Password for superuser (used by init-db if set)
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

    Returns:
        0 on success, 1 on error
    """
    import subprocess

    from mud_server.db.database import DB_PATH, init_database

    # Initialize database if it doesn't exist
    if not DB_PATH.exists():
        print("Database not found. Initializing...")
        init_database()

    # Start the server
    try:
        # Import and run the server directly
        from mud_server.api.server import start_server

        start_server()
        return 0
    except ImportError:
        # Fall back to subprocess if direct import fails
        print("Starting server...")
        result = subprocess.run([sys.executable, "-m", "mud_server.api.server"])
        return result.returncode
    except KeyboardInterrupt:
        print("\nServer stopped.")
        return 0


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
        description="Start both the API server and Gradio client.",
    )
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
