"""
Configuration management for PipeWorks Admin TUI.

This module handles configuration from multiple sources with the following
precedence (highest to lowest):

1. Command-line arguments (--server, --timeout)
2. Environment variables (MUD_SERVER_URL, MUD_REQUEST_TIMEOUT)
3. Default values

The configuration is immutable once created, ensuring consistent behavior
throughout the application lifecycle.

Example:
    # Create config from CLI args
    config = Config.from_args(["--server", "http://localhost:8000"])

    # Access configuration
    print(config.server_url)  # "http://localhost:8000"
    print(config.timeout)     # 30.0 (default)
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass

# =============================================================================
# DEFAULT CONFIGURATION VALUES
# =============================================================================

# Default server URL - assumes TUI is running on the same machine as the server.
# This is the typical case when SSH'd into the server and running in tmux.
DEFAULT_SERVER_URL = "http://localhost:8000"

# Default HTTP request timeout in seconds.
# Set conservatively high to handle slow operations like database queries.
DEFAULT_TIMEOUT = 30.0

# Environment variable names for configuration.
# These allow configuration without modifying command-line arguments,
# useful for systemd services or shell rc files.
ENV_SERVER_URL = "MUD_SERVER_URL"
ENV_TIMEOUT = "MUD_REQUEST_TIMEOUT"


# =============================================================================
# CONFIGURATION DATACLASS
# =============================================================================


@dataclass(frozen=True)
class Config:
    """
    Immutable configuration container for the Admin TUI.

    This dataclass holds all configuration values needed by the application.
    It is frozen (immutable) to prevent accidental modification after creation.

    Attributes:
        server_url: Base URL of the MUD server API (e.g., "http://localhost:8000").
                    Should NOT include a trailing slash.
        timeout: HTTP request timeout in seconds. Applied to all API calls.

    Example:
        config = Config(server_url="http://localhost:8000", timeout=30.0)
    """

    server_url: str
    timeout: float

    def __post_init__(self) -> None:
        """
        Validate configuration values after initialization.

        Raises:
            ValueError: If server_url is empty or timeout is not positive.
        """
        # Validate server_url is not empty
        if not self.server_url:
            raise ValueError("server_url cannot be empty")

        # Validate timeout is positive
        if self.timeout <= 0:
            raise ValueError("timeout must be a positive number")

    @classmethod
    def from_args(cls, args: Sequence[str] | None = None) -> Config:
        """
        Create a Config instance from command-line arguments.

        This method parses command-line arguments and falls back to environment
        variables and then default values for any unspecified options.

        Args:
            args: Command-line arguments to parse. If None, uses sys.argv[1:].

        Returns:
            Config: A fully populated configuration object.

        Example:
            # From explicit args
            config = Config.from_args(["--server", "http://example.com:8000"])

            # From sys.argv (typical usage in main())
            config = Config.from_args()
        """
        parser = argparse.ArgumentParser(
            prog="pipeworks-admin-tui",
            description="Terminal UI for PipeWorks MUD Server administration",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  pipeworks-admin-tui                              # Connect to localhost:8000
  pipeworks-admin-tui --server http://10.0.0.1:8000  # Connect to remote server
  MUD_SERVER_URL=http://10.0.0.1:8000 pipeworks-admin-tui  # Via environment

Environment Variables:
  MUD_SERVER_URL       Server URL (default: http://localhost:8000)
  MUD_REQUEST_TIMEOUT  Request timeout in seconds (default: 30)
            """,
        )

        # Server URL argument
        parser.add_argument(
            "--server",
            "-s",
            dest="server_url",
            default=None,  # None means "check env var, then use default"
            help=f"MUD server URL (default: {DEFAULT_SERVER_URL})",
        )

        # Timeout argument
        parser.add_argument(
            "--timeout",
            "-t",
            type=float,
            default=None,  # None means "check env var, then use default"
            help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
        )

        # Parse the arguments
        parsed = parser.parse_args(args)

        # Resolve server_url with precedence: CLI > ENV > DEFAULT
        server_url = parsed.server_url or os.environ.get(ENV_SERVER_URL) or DEFAULT_SERVER_URL

        # Remove trailing slash if present for consistency
        server_url = server_url.rstrip("/")

        # Resolve timeout with precedence: CLI > ENV > DEFAULT
        if parsed.timeout is not None:
            timeout = parsed.timeout
        elif ENV_TIMEOUT in os.environ:
            timeout = float(os.environ[ENV_TIMEOUT])
        else:
            timeout = DEFAULT_TIMEOUT

        return cls(server_url=server_url, timeout=timeout)
