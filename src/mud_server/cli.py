"""
Command-line interface for PipeWorks MUD Server.

Provides CLI commands for server management:
- init-db: Initialize the database schema
- create-superuser: Create a superuser account interactively or via environment variables
- import-policy-artifact: Import a published artifact into canonical policy DB rows
- run: Start the MUD server (API and web UI)

Usage:
    mud-server init-db
    mud-server init-db --skip-policy-import
    mud-server create-superuser
    mud-server import-policy-artifact --artifact-path PATH
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
from pathlib import Path


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


def _import_registered_world_artifacts_for_init(
    *, actor: str, world_ids: list[str] | None = None
) -> int:
    """Import canonical policy artifacts for registered worlds during ``init-db``.

    The bootstrap path is DB/artifact-first. Legacy world policy files are no
    longer used as a bootstrap source in this command.

    Returns:
        Number of failed world imports.
    """
    import json

    from mud_server.core.world_registry import WorldRegistry
    from mud_server.services import policy_service
    from mud_server.services.policy.constants import _POLICY_EXPORT_WORLD_DIRNAME
    from mud_server.services.policy.paths import resolve_policy_export_root

    if world_ids is None:
        registry = WorldRegistry()
        worlds = registry.list_worlds(include_inactive=True)
        if not worlds:
            print("No registered worlds found; skipping artifact import bootstrap.")
            return 0
        selected_world_ids = [str(world.get("id") or "").strip() for world in worlds]
    else:
        selected_world_ids = [str(world_id).strip() for world_id in world_ids]

    export_root = resolve_policy_export_root()

    failures = 0
    for world_id in selected_world_ids:
        if not world_id:
            failures += 1
            print("Skipping malformed world id during artifact bootstrap.", file=sys.stderr)
            continue

        latest_path = (
            export_root / _POLICY_EXPORT_WORLD_DIRNAME / world_id / "world" / "latest.json"
        )
        if not latest_path.exists():
            print(
                f"No canonical artifact pointer found for world {world_id}: {latest_path}",
                file=sys.stderr,
            )
            continue

        try:
            latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
            artifact_path = _resolve_artifact_path_from_latest_payload(
                latest_payload=latest_payload,
                export_root=export_root,
                latest_path=latest_path,
            )
            artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            summary = policy_service.import_published_artifact(
                artifact=artifact_payload,
                actor=actor,
                activate=True,
            )
        except policy_service.PolicyServiceError as exc:
            failures += 1
            print(
                f"World artifact import failed for {world_id} [{exc.code}]: {exc.detail}",
                file=sys.stderr,
            )
            continue
        except Exception as exc:
            failures += 1
            print(f"World artifact import failed for {world_id}: {exc}", file=sys.stderr)
            continue

        print(
            "World artifact import summary: "
            f"world={world_id} imported={summary.imported_count} "
            f"updated={summary.updated_count} skipped={summary.skipped_count} "
            f"errors={summary.error_count} activated={summary.activated_count} "
            f"activation_unchanged={summary.activation_skipped_count}"
        )
        if summary.error_count > 0:
            failures += summary.error_count

    return failures


def _resolve_artifact_path_from_latest_payload(
    *,
    latest_payload: dict[str, object],
    export_root: Path,
    latest_path: Path,
) -> Path:
    """Resolve one artifact file path from ``latest.json`` payload fields."""

    artifact_path_value = str(latest_payload.get("artifact_path", "")).strip()
    artifact_file = str(latest_payload.get("artifact_file", "")).strip()
    candidates: list[Path] = []

    if artifact_path_value:
        payload_path = Path(artifact_path_value)
        if payload_path.is_absolute():
            candidates.append(payload_path)
            candidates.append((latest_path.parent / payload_path.name).resolve())
        else:
            candidates.append((export_root / payload_path).resolve())
            candidates.append((latest_path.parent / payload_path).resolve())

    if artifact_file:
        candidates.append((latest_path.parent / artifact_file).resolve())

    deduped_candidates: list[Path] = []
    for candidate in candidates:
        if candidate not in deduped_candidates:
            deduped_candidates.append(candidate)

    for candidate in deduped_candidates:
        if candidate.exists():
            return candidate

    if not deduped_candidates:
        raise ValueError("latest.json is missing artifact_path/artifact_file.")
    raise FileNotFoundError(
        "latest.json artifact pointer does not resolve to an existing file: "
        + ", ".join(str(path) for path in deduped_candidates)
    )


def _sync_world_catalog_from_packages_for_init() -> list[str]:
    """Upsert world catalog rows from on-disk world packages.

    ``init-db`` builds schema first, then synchronizes ``worlds`` table entries
    from ``data/worlds/<world_id>/world.json`` packages so artifact bootstrap
    can target every discovered world, not only the default world id.

    Returns:
        Sorted list of discovered world ids successfully upserted into catalog.
    """
    import json
    from pathlib import Path

    from mud_server.config import PROJECT_ROOT, config
    from mud_server.db.connection import connection_scope

    worlds_root = Path(config.worlds.worlds_root)
    if not worlds_root.is_absolute():
        worlds_root = (PROJECT_ROOT / worlds_root).resolve()

    discovered_rows: list[tuple[str, str, str]] = []
    if worlds_root.exists():
        for world_json_path in sorted(worlds_root.glob("*/world.json")):
            world_id = world_json_path.parent.name.strip()
            if not world_id:
                continue
            try:
                payload = json.loads(world_json_path.read_text(encoding="utf-8"))
            except Exception as exc:
                print(
                    f"Skipping world catalog sync for {world_json_path}: {exc}",
                    file=sys.stderr,
                )
                continue

            raw_name = payload.get("name")
            raw_description = payload.get("description")
            name = str(raw_name).strip() if raw_name is not None else world_id
            description = str(raw_description).strip() if raw_description is not None else ""
            discovered_rows.append((world_id, name or world_id, description))

    if not discovered_rows:
        return []

    with connection_scope(write=True) as conn:
        cursor = conn.cursor()
        for world_id, name, description in discovered_rows:
            cursor.execute(
                """
                INSERT INTO worlds (id, name, description, is_active, config_json)
                VALUES (?, ?, ?, 1, '{}')
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    is_active = 1
                """,
                (world_id, name, description),
            )
        conn.commit()

    return sorted({row[0] for row in discovered_rows})


def cmd_init_db(args: argparse.Namespace) -> int:
    """
    Initialize the database schema.

    Initializes schema and, by default, imports/activates canonical world
    policy objects for discovered world packages. This avoids runtime reliance
    on startup-time legacy file bootstrap.

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

        if getattr(args, "skip_policy_import", False):
            print("Skipping world artifact import bootstrap (--skip-policy-import).")
            return 0

        discovered_world_ids = _sync_world_catalog_from_packages_for_init()
        world_ids_for_bootstrap = discovered_world_ids or [config.worlds.default_world_id]

        failures = _import_registered_world_artifacts_for_init(
            actor="system-bootstrap",
            world_ids=world_ids_for_bootstrap,
        )
        if failures > 0:
            print(
                "Database initialized, but world artifact bootstrap reported failures. "
                "Review output and rerun 'mud-server import-policy-artifact' as needed.",
                file=sys.stderr,
            )
            return 1

        print("World artifact bootstrap completed successfully.")
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


def cmd_import_policy_artifact(args: argparse.Namespace) -> int:
    """Import one publish artifact into canonical DB policy state."""
    import json
    from pathlib import Path

    from mud_server.db import facade as database
    from mud_server.services import policy_service

    artifact_path = Path(str(args.artifact_path)).expanduser()
    actor = (args.actor or "").strip() or "policy-importer"
    activate = bool(args.activate)

    try:
        artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Artifact file not found: {artifact_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(
            f"Artifact file is not valid JSON: {artifact_path} ({exc})",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"Failed to read artifact file {artifact_path}: {exc}", file=sys.stderr)
        return 1

    try:
        database.init_database(skip_superuser=True)
        summary = policy_service.import_published_artifact(
            artifact=artifact_payload,
            actor=actor,
            activate=activate,
        )
    except policy_service.PolicyServiceError as exc:
        print(f"Artifact import failed [{exc.code}]: {exc.detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Artifact import failed: {exc}", file=sys.stderr)
        return 1

    scope_label = (
        summary.world_id
        if not summary.client_profile
        else (f"{summary.world_id}:{summary.client_profile}")
    )
    print(
        "Artifact import summary: "
        f"scope={scope_label} item_count={summary.item_count} "
        f"imported={summary.imported_count} updated={summary.updated_count} "
        f"skipped={summary.skipped_count} errors={summary.error_count}"
    )
    if summary.activate:
        print(
            "Activation summary: "
            f"activated={summary.activated_count} "
            f"unchanged={summary.activation_skipped_count}"
        )
    print(
        "Artifact hashes: "
        f"manifest_hash={summary.manifest_hash} "
        f"items_hash={summary.items_hash} "
        f"variants_hash={summary.variants_hash} "
        f"artifact_hash={summary.artifact_hash}"
    )
    error_entries = [entry for entry in summary.entries if entry.action == "error"]
    if error_entries:
        print("Import errors:", file=sys.stderr)
        for entry in error_entries:
            policy_ref = (
                "<unknown>"
                if not entry.policy_id or not entry.variant
                else f"{entry.policy_id}:{entry.variant}"
            )
            print(f"- {policy_ref}: {entry.detail}", file=sys.stderr)
        return 1
    return 0


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
    host = getattr(args, "host", None) or config.server.host
    api_port = getattr(args, "port", None)

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
        api_port = config.server.port

    # Find an available port (may be different from api_port if it's in use)
    actual_api_port = find_api_port(api_port, host)
    if actual_api_port is None:
        print(
            "Error: No available port found for API server (8000-8099 all in use).", file=sys.stderr
        )
        return 1

    if actual_api_port != api_port:
        print(
            f"Preferred API port {api_port} on {host} is in use. "
            f"Using {actual_api_port} for this run."
        )

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
            "Initialize the database with required tables and bootstrap canonical "
            "world policy objects/activations for registered worlds."
        ),
    )
    init_parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run the multi-world migration script instead of a fresh init.",
    )
    init_parser.add_argument(
        "--skip-policy-import",
        action="store_true",
        help="Skip world artifact bootstrap import during init-db.",
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

    import_artifact_parser = subparsers.add_parser(
        "import-policy-artifact",
        help="Import one publish artifact into canonical policy DB state",
        description=(
            "Ingest a deterministic publish artifact JSON file and upsert canonical "
            "policy variants into the SQLite control plane. Optionally applies "
            "activation pointers for the artifact scope."
        ),
    )
    import_artifact_parser.add_argument(
        "--artifact-path",
        type=str,
        required=True,
        help="Filesystem path to the publish_<manifest_hash>.json artifact file.",
    )
    import_artifact_parser.add_argument(
        "--actor",
        type=str,
        default="policy-importer",
        help="Actor value used for updated_by / activated_by audit fields.",
    )
    import_artifact_parser.add_argument(
        "--no-activate",
        action="store_false",
        dest="activate",
        help="Import variants only; do not apply activation pointers from artifact variants.",
    )
    import_artifact_parser.set_defaults(activate=True)
    import_artifact_parser.set_defaults(func=cmd_import_policy_artifact)

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
