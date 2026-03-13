"""
Command-line interface for PipeWorks MUD Server.

Provides CLI commands for server management:
- init-db: Initialize the database schema
- create-superuser: Create a superuser account interactively or via environment variables
- import-species-policies: Backfill legacy species YAML into canonical policy DB rows
- import-layer2-policies: Backfill descriptor/registry legacy policies into Layer 2 DB rows
- import-tone-prompt-policies: Backfill tone-profile/prompt legacy policies into Layer 1 DB rows
- import-world-policies: Backfill all legacy policy-like files into canonical policy DB rows
- run: Start the MUD server (API and web UI)

Usage:
    mud-server init-db
    mud-server create-superuser
    mud-server import-species-policies [--world-id WORLD_ID]
    mud-server import-layer2-policies [--world-id WORLD_ID]
    mud-server import-tone-prompt-policies [--world-id WORLD_ID]
    mud-server import-world-policies [--world-id WORLD_ID]
    mud-server run [--port PORT] [--host HOST]

Environment Variables:
    MUD_ADMIN_USER: Username for superuser (used by init-db if set)
    MUD_ADMIN_PASSWORD: Password for superuser (used by init-db if set)
    MUD_HOST: Host to bind API server (default: 0.0.0.0)
    MUD_PORT: Port for API server (default: 8000, auto-discovers if in use)
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
    from datetime import datetime
    from shutil import copy2

    from mud_server.config import config
    from mud_server.db import facade as database

    try:
        db_path = config.database.absolute_path
        if db_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = db_path.with_suffix(f".bak.{timestamp}")
            copy2(db_path, backup_path)
            print(f"Existing database backed up to {backup_path}")

        if getattr(args, "migrate", False):
            import importlib.util
            from pathlib import Path

            script_path = (
                Path(__file__).resolve().parents[2] / "scripts" / "migrate_to_multiworld.py"
            )
            if not script_path.exists():
                print(f"Migration script not found: {script_path}", file=sys.stderr)
                return 1

            spec = importlib.util.spec_from_file_location("migrate_to_multiworld", script_path)
            if not spec or not spec.loader:
                print("Failed to load migration script.", file=sys.stderr)
                return 1

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            migrate_main = getattr(module, "main", None)
            if migrate_main is None:
                print("Migration script missing main() entry point.", file=sys.stderr)
                return 1

            original_argv = sys.argv
            try:
                sys.argv = [str(script_path)]
                return int(migrate_main())
            finally:
                sys.argv = original_argv

        database.init_database()
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
    from mud_server.db import facade as database

    # Ensure database exists (skip superuser creation - we'll do it ourselves)
    database.init_database(skip_superuser=True)

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
    if database.user_exists(username):
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
        success = database.create_user_with_password(
            username, password, role="superuser", account_origin="superuser"
        )
        if success:
            print(f"\nSuperuser '{username}' created successfully.")
            print("No character was created automatically; provision characters separately.")
            return 0
        else:
            print(f"Error: Failed to create user '{username}'.", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error creating superuser: {e}", file=sys.stderr)
        return 1


def cmd_import_species_policies(args: argparse.Namespace) -> int:
    """Import legacy species YAML files into canonical policy DB variants.

    This command performs idempotent backfill/update and can optionally seed
    world-scope activation pointers to the imported variants.
    """
    from mud_server.config import config
    from mud_server.db import facade as database
    from mud_server.services import policy_service

    world_id = (args.world_id or "").strip() or config.worlds.default_world_id
    actor = (args.actor or "").strip() or "policy-importer"
    status = str(args.status)
    activate = bool(args.activate)

    try:
        database.init_database(skip_superuser=True)
        summary = policy_service.import_species_blocks_from_legacy_yaml(
            world_id=world_id,
            actor=actor,
            activate=activate,
            status=status,
        )
    except policy_service.PolicyServiceError as exc:
        print(f"Species import failed [{exc.code}]: {exc.detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Species import failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Species import summary: "
        f"world={summary.world_id} scanned={summary.scanned_files} "
        f"imported={summary.imported_count} updated={summary.updated_count} "
        f"skipped={summary.skipped_count} errors={summary.error_count}"
    )
    if summary.activate:
        print(
            "Activation summary: "
            f"activated={summary.activated_count} "
            f"unchanged={summary.activation_skipped_count}"
        )

    error_entries = [entry for entry in summary.entries if entry.action == "error"]
    if error_entries:
        print("Import errors:", file=sys.stderr)
        for entry in error_entries:
            print(f"- {entry.source_path}: {entry.detail}", file=sys.stderr)
        return 1

    return 0


def cmd_import_layer2_policies(args: argparse.Namespace) -> int:
    """Import legacy descriptor/registry files into canonical Layer 2 policy variants."""
    from mud_server.config import config
    from mud_server.db import facade as database
    from mud_server.services import policy_service

    world_id = (args.world_id or "").strip() or config.worlds.default_world_id
    actor = (args.actor or "").strip() or "policy-importer"
    status = str(args.status)
    activate = bool(args.activate)

    try:
        database.init_database(skip_superuser=True)
        summary = policy_service.import_layer2_policies_from_legacy_files(
            world_id=world_id,
            actor=actor,
            activate=activate,
            status=status,
        )
    except policy_service.PolicyServiceError as exc:
        print(f"Layer 2 import failed [{exc.code}]: {exc.detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Layer 2 import failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Layer 2 import summary: "
        f"world={summary.world_id} descriptors={summary.scanned_descriptor_files} "
        f"registries={summary.scanned_registry_files} imported={summary.imported_count} "
        f"updated={summary.updated_count} skipped={summary.skipped_count} "
        f"errors={summary.error_count}"
    )
    if summary.activate:
        print(
            "Activation summary: "
            f"activated={summary.activated_count} "
            f"unchanged={summary.activation_skipped_count}"
        )

    error_entries = [entry for entry in summary.entries if entry.action == "error"]
    if error_entries:
        print("Import errors:", file=sys.stderr)
        for entry in error_entries:
            print(f"- {entry.source_path}: {entry.detail}", file=sys.stderr)
        return 1

    return 0


def cmd_import_tone_prompt_policies(args: argparse.Namespace) -> int:
    """Import legacy tone-profile/prompt files into canonical Layer 1 policy variants."""
    from mud_server.config import config
    from mud_server.db import facade as database
    from mud_server.services import policy_service

    world_id = (args.world_id or "").strip() or config.worlds.default_world_id
    actor = (args.actor or "").strip() or "policy-importer"
    status = str(args.status)
    activate = bool(args.activate)

    try:
        database.init_database(skip_superuser=True)
        summary = policy_service.import_tone_prompt_policies_from_legacy_files(
            world_id=world_id,
            actor=actor,
            activate=activate,
            status=status,
        )
    except policy_service.PolicyServiceError as exc:
        print(f"Tone/prompt import failed [{exc.code}]: {exc.detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Tone/prompt import failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Tone/prompt import summary: "
        f"world={summary.world_id} tone_profiles={summary.scanned_tone_profile_files} "
        f"prompts={summary.scanned_prompt_files} imported={summary.imported_count} "
        f"updated={summary.updated_count} skipped={summary.skipped_count} "
        f"errors={summary.error_count}"
    )
    if summary.activate:
        print(
            "Activation summary: "
            f"activated={summary.activated_count} "
            f"unchanged={summary.activation_skipped_count}"
        )

    error_entries = [entry for entry in summary.entries if entry.action == "error"]
    if error_entries:
        print("Import errors:", file=sys.stderr)
        for entry in error_entries:
            print(f"- {entry.source_path}: {entry.detail}", file=sys.stderr)
        return 1

    return 0


def cmd_import_world_policies(args: argparse.Namespace) -> int:
    """Import all known legacy policy-like domains into canonical policy state."""
    from mud_server.config import config
    from mud_server.db import facade as database
    from mud_server.services import policy_service

    world_id = (args.world_id or "").strip() or config.worlds.default_world_id
    actor = (args.actor or "").strip() or "policy-importer"
    status = str(args.status)
    activate = bool(args.activate)

    try:
        database.init_database(skip_superuser=True)
        summary = policy_service.import_world_policies_from_legacy_files(
            world_id=world_id,
            actor=actor,
            activate=activate,
            status=status,
        )
    except policy_service.PolicyServiceError as exc:
        print(f"World policy import failed [{exc.code}]: {exc.detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"World policy import failed: {exc}", file=sys.stderr)
        return 1

    print(
        "World policy import summary: "
        f"world={summary.world_id} imported={summary.imported_count} "
        f"updated={summary.updated_count} skipped={summary.skipped_count} "
        f"errors={summary.error_count}"
    )
    if summary.activate:
        print(
            "Activation summary: "
            f"activated={summary.activated_count} "
            f"unchanged={summary.activation_skipped_count}"
        )
    for entry in summary.entries:
        print(f"- {entry}")

    return 1 if summary.error_count > 0 else 0


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


def cmd_run(args: argparse.Namespace) -> int:
    """
    Run the MUD server (API + WebUI).

    This is the main entry point for starting the MUD server. It initializes
    the database if needed, then starts the API server. The WebUI is served
    directly by FastAPI.

    Port Auto-Discovery:
        If the configured port is already in use, the server will automatically
        find an available port in a predefined range:
        - API server: 8000-8099

    Configuration Priority:
        1. CLI arguments (--port, --host)
        2. Environment variables (MUD_PORT, MUD_HOST)
        3. Default values (8000 for API, 0.0.0.0 for host)

    Args:
        args: Parsed command-line arguments from argparse. Expected attributes:
            - port (int | None): API server port override
            - host (str | None): Host interface to bind the server

    Returns:
        0 on successful execution or clean shutdown (Ctrl+C)
        1 on error during startup

    Example:
        # Start with default ports
        mud-server run

        # Specify custom port
        mud-server run --port 9000

    Note:
        The API server runs in the main process.
    """
    from mud_server.api.server import find_available_port as find_api_port
    from mud_server.config import config
    from mud_server.db import facade as database

    # ========================================================================
    # DATABASE INITIALIZATION
    # ========================================================================
    # Ensure the database exists before starting servers. This creates the
    # SQLite database file and all required tables if they don't exist.
    db_path = config.database.absolute_path
    if not db_path.exists():
        print("Database not found. Initializing...")
        database.init_database()

    # ========================================================================
    # CONFIGURATION EXTRACTION
    # ========================================================================
    # Extract port and host configuration from parsed arguments.
    # getattr with default None handles cases where args might not have
    # these attributes (e.g., when called programmatically).
    api_port = getattr(args, "port", None)
    host = getattr(args, "host", None) or os.environ.get("MUD_HOST", "0.0.0.0")  # nosec B104

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

    try:
        # ================================================================
        # API + WEBUI MODE
        # ================================================================
        # Run the API server directly; the WebUI is served by FastAPI.
        # Pass auto_discover=False since we already found the port.
        _run_api_server_on_port(host, actual_api_port)
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
    init_parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run the multi-world migration script instead of a fresh init.",
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

    import_species_parser = subparsers.add_parser(
        "import-species-policies",
        help="Import legacy species YAML files into canonical policy DB state",
        description=(
            "Backfill data/worlds/<world_id>/policies/image/blocks/species/*.yaml "
            "into policy_item/policy_variant and optionally seed world activation pointers."
        ),
    )
    import_species_parser.add_argument(
        "--world-id",
        type=str,
        default=None,
        help=("Target world id. Defaults to configured worlds.default_world_id when omitted."),
    )
    import_species_parser.add_argument(
        "--actor",
        type=str,
        default="policy-importer",
        help="Actor value used for updated_by / activated_by audit fields.",
    )
    import_species_parser.add_argument(
        "--status",
        type=str,
        choices=["draft", "candidate", "active", "archived"],
        default="active",
        help="Status assigned to imported/updated policy variants (default: active).",
    )
    import_species_parser.add_argument(
        "--no-activate",
        action="store_false",
        dest="activate",
        help="Import variants only; do not seed world-scope activation pointers.",
    )
    import_species_parser.set_defaults(activate=True)
    import_species_parser.set_defaults(func=cmd_import_species_policies)

    import_layer2_parser = subparsers.add_parser(
        "import-layer2-policies",
        help="Import legacy descriptor/registry files into canonical Layer 2 policy state",
        description=(
            "Backfill data/worlds/<world_id>/policies/image/descriptor_layers/* and "
            "data/worlds/<world_id>/policies/image/registries/*.yaml into "
            "policy_item/policy_variant and optionally seed world activation pointers."
        ),
    )
    import_layer2_parser.add_argument(
        "--world-id",
        type=str,
        default=None,
        help=("Target world id. Defaults to configured worlds.default_world_id when omitted."),
    )
    import_layer2_parser.add_argument(
        "--actor",
        type=str,
        default="policy-importer",
        help="Actor value used for updated_by / activated_by audit fields.",
    )
    import_layer2_parser.add_argument(
        "--status",
        type=str,
        choices=["draft", "candidate", "active", "archived"],
        default="active",
        help="Status assigned to imported/updated policy variants (default: active).",
    )
    import_layer2_parser.add_argument(
        "--no-activate",
        action="store_false",
        dest="activate",
        help="Import variants only; do not seed world-scope activation pointers.",
    )
    import_layer2_parser.set_defaults(activate=True)
    import_layer2_parser.set_defaults(func=cmd_import_layer2_policies)

    import_tone_prompt_parser = subparsers.add_parser(
        "import-tone-prompt-policies",
        help="Import legacy tone-profile/prompt files into canonical Layer 1 policy state",
        description=(
            "Backfill data/worlds/<world_id>/policies/image/tone_profiles/*.json plus "
            "data/worlds/<world_id>/policies/translation/prompts/**/*.txt and "
            "data/worlds/<world_id>/policies/image/prompts/**/*.txt into "
            "policy_item/policy_variant and optionally seed world activation pointers."
        ),
    )
    import_tone_prompt_parser.add_argument(
        "--world-id",
        type=str,
        default=None,
        help=("Target world id. Defaults to configured worlds.default_world_id when omitted."),
    )
    import_tone_prompt_parser.add_argument(
        "--actor",
        type=str,
        default="policy-importer",
        help="Actor value used for updated_by / activated_by audit fields.",
    )
    import_tone_prompt_parser.add_argument(
        "--status",
        type=str,
        choices=["draft", "candidate", "active", "archived"],
        default="active",
        help="Status assigned to imported/updated policy variants (default: active).",
    )
    import_tone_prompt_parser.add_argument(
        "--no-activate",
        action="store_false",
        dest="activate",
        help="Import variants only; do not seed world-scope activation pointers.",
    )
    import_tone_prompt_parser.set_defaults(activate=True)
    import_tone_prompt_parser.set_defaults(func=cmd_import_tone_prompt_policies)

    import_world_parser = subparsers.add_parser(
        "import-world-policies",
        help="Import all legacy policy-like files into canonical policy state",
        description=(
            "Run the full world-scoped policy migration in dependency order: "
            "species, tone/prompt, clothing blocks, Layer 2, and axis/manifest bundles."
        ),
    )
    import_world_parser.add_argument(
        "--world-id",
        type=str,
        default=None,
        help=("Target world id. Defaults to configured worlds.default_world_id when omitted."),
    )
    import_world_parser.add_argument(
        "--actor",
        type=str,
        default="policy-importer",
        help="Actor value used for updated_by / activated_by audit fields.",
    )
    import_world_parser.add_argument(
        "--status",
        type=str,
        choices=["draft", "candidate", "active", "archived"],
        default="active",
        help="Status assigned to imported/updated policy variants (default: active).",
    )
    import_world_parser.add_argument(
        "--no-activate",
        action="store_false",
        dest="activate",
        help="Import variants only; do not seed world-scope activation pointers.",
    )
    import_world_parser.set_defaults(activate=True)
    import_world_parser.set_defaults(func=cmd_import_world_policies)

    # run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run the MUD server",
        description=(
            "Start the API server and serve the admin WebUI. "
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
        "--host",
        type=str,
        help="Host to bind servers to (default: 0.0.0.0, or MUD_HOST env var)",
    )
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
