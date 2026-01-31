"""
Server configuration management.

This module handles loading and accessing server configuration from multiple sources
with a clear priority order:

    1. Environment variables (highest priority) - for containerized deployments
    2. Config file (config/server.ini) - for static deployments
    3. Built-in defaults (lowest priority) - sensible fallbacks

Configuration is loaded once at module import time and cached. The ServerConfig
dataclass provides typed access to all settings.

Usage:
    from mud_server.config import config

    # Access settings
    print(config.server.host)
    print(config.security.cors_origins)
    print(config.is_production)

Environment Variable Mapping:
    MUD_HOST           -> server.host
    MUD_PORT           -> server.port
    MUD_PRODUCTION     -> security.production
    MUD_CORS_ORIGINS   -> security.cors_origins
    MUD_DB_PATH        -> database.path
    MUD_LOG_LEVEL      -> logging.level
"""

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

# Project root directory (contains src/, config/, data/)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Config file paths
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "server.ini"
CONFIG_EXAMPLE = CONFIG_DIR / "server.example.ini"


# =============================================================================
# CONFIGURATION DATACLASSES
# =============================================================================


@dataclass
class ServerSettings:
    """Network server configuration."""

    host: str = "0.0.0.0"  # nosec B104 - intentional for server binding
    port: int = 8000


@dataclass
class SecuritySettings:
    """Security-related configuration."""

    production: bool = False
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:7860"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = field(default_factory=lambda: ["*"])
    docs_enabled: Literal["auto", "enabled", "disabled"] = "auto"


@dataclass
class SessionSettings:
    """Session management configuration."""

    timeout_minutes: int = 0  # 0 = no timeout
    max_sessions_per_user: int = 0  # 0 = unlimited


@dataclass
class DatabaseSettings:
    """Database configuration."""

    path: str = "data/mud.db"

    @property
    def absolute_path(self) -> Path:
        """Get absolute path to database file."""
        p = Path(self.path)
        if p.is_absolute():
            return p
        return PROJECT_ROOT / p


@dataclass
class LoggingSettings:
    """Logging configuration."""

    level: str = "INFO"
    format: Literal["simple", "detailed", "json"] = "detailed"


@dataclass
class RateLimitSettings:
    """Rate limiting configuration."""

    enabled: bool = False
    login_per_minute: int = 5
    register_per_minute: int = 5
    api_per_second: int = 30


@dataclass
class FeatureSettings:
    """Feature flags."""

    ollama_enabled: bool = True
    verbose_errors: bool = False


@dataclass
class ServerConfig:
    """
    Complete server configuration.

    This is the main configuration object that aggregates all settings sections.
    Access via the module-level `config` singleton.
    """

    server: ServerSettings = field(default_factory=ServerSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    session: SessionSettings = field(default_factory=SessionSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    rate_limit: RateLimitSettings = field(default_factory=RateLimitSettings)
    features: FeatureSettings = field(default_factory=FeatureSettings)

    @property
    def is_production(self) -> bool:
        """Convenience property for production mode check."""
        return self.security.production

    @property
    def docs_should_be_enabled(self) -> bool:
        """Determine if API docs should be enabled based on settings."""
        if self.security.docs_enabled == "enabled":
            return True
        if self.security.docs_enabled == "disabled":
            return False
        # "auto" - follow production setting
        return not self.is_production


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================


def _parse_bool(value: str) -> bool:
    """Parse a string value to boolean."""
    return value.lower() in ("true", "yes", "1", "on", "enabled")


def _parse_list(value: str) -> list[str]:
    """Parse a comma-separated string to list, stripping whitespace."""
    if not value or value.strip() == "":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _load_from_ini(parser: configparser.ConfigParser, cfg: ServerConfig) -> None:
    """Load configuration from parsed INI file into ServerConfig."""
    # Server section
    if parser.has_section("server"):
        if parser.has_option("server", "host"):
            cfg.server.host = parser.get("server", "host")
        if parser.has_option("server", "port"):
            cfg.server.port = parser.getint("server", "port")

    # Security section
    if parser.has_section("security"):
        if parser.has_option("security", "production"):
            cfg.security.production = _parse_bool(parser.get("security", "production"))
        if parser.has_option("security", "cors_origins"):
            cfg.security.cors_origins = _parse_list(parser.get("security", "cors_origins"))
        if parser.has_option("security", "cors_allow_credentials"):
            cfg.security.cors_allow_credentials = _parse_bool(
                parser.get("security", "cors_allow_credentials")
            )
        if parser.has_option("security", "cors_allow_methods"):
            cfg.security.cors_allow_methods = _parse_list(
                parser.get("security", "cors_allow_methods")
            )
        if parser.has_option("security", "cors_allow_headers"):
            cfg.security.cors_allow_headers = _parse_list(
                parser.get("security", "cors_allow_headers")
            )
        if parser.has_option("security", "docs_enabled"):
            val = parser.get("security", "docs_enabled").lower()
            if val in ("auto", "enabled", "disabled"):
                cfg.security.docs_enabled = val  # type: ignore[assignment]

    # Session section
    if parser.has_section("session"):
        if parser.has_option("session", "timeout_minutes"):
            cfg.session.timeout_minutes = parser.getint("session", "timeout_minutes")
        if parser.has_option("session", "max_sessions_per_user"):
            cfg.session.max_sessions_per_user = parser.getint("session", "max_sessions_per_user")

    # Database section
    if parser.has_section("database"):
        if parser.has_option("database", "path"):
            cfg.database.path = parser.get("database", "path")

    # Logging section
    if parser.has_section("logging"):
        if parser.has_option("logging", "level"):
            cfg.logging.level = parser.get("logging", "level").upper()
        if parser.has_option("logging", "format"):
            val = parser.get("logging", "format").lower()
            if val in ("simple", "detailed", "json"):
                cfg.logging.format = val  # type: ignore[assignment]

    # Rate limit section
    if parser.has_section("rate_limit"):
        if parser.has_option("rate_limit", "enabled"):
            cfg.rate_limit.enabled = _parse_bool(parser.get("rate_limit", "enabled"))
        if parser.has_option("rate_limit", "login_per_minute"):
            cfg.rate_limit.login_per_minute = parser.getint("rate_limit", "login_per_minute")
        if parser.has_option("rate_limit", "register_per_minute"):
            cfg.rate_limit.register_per_minute = parser.getint("rate_limit", "register_per_minute")
        if parser.has_option("rate_limit", "api_per_second"):
            cfg.rate_limit.api_per_second = parser.getint("rate_limit", "api_per_second")

    # Features section
    if parser.has_section("features"):
        if parser.has_option("features", "ollama_enabled"):
            cfg.features.ollama_enabled = _parse_bool(parser.get("features", "ollama_enabled"))
        if parser.has_option("features", "verbose_errors"):
            cfg.features.verbose_errors = _parse_bool(parser.get("features", "verbose_errors"))


def _apply_env_overrides(cfg: ServerConfig) -> None:
    """Apply environment variable overrides to configuration."""
    # Server settings
    if env_host := os.getenv("MUD_HOST"):
        cfg.server.host = env_host
    if env_port := os.getenv("MUD_PORT"):
        cfg.server.port = int(env_port)

    # Security settings
    if env_production := os.getenv("MUD_PRODUCTION"):
        cfg.security.production = _parse_bool(env_production)
    if env_cors := os.getenv("MUD_CORS_ORIGINS"):
        cfg.security.cors_origins = _parse_list(env_cors)

    # Database settings
    if env_db := os.getenv("MUD_DB_PATH"):
        cfg.database.path = env_db

    # Logging settings
    if env_log := os.getenv("MUD_LOG_LEVEL"):
        cfg.logging.level = env_log.upper()


def load_config() -> ServerConfig:
    """
    Load configuration from all sources with proper priority.

    Priority (highest wins):
        1. Environment variables
        2. config/server.ini
        3. config/server.example.ini (fallback for development)
        4. Built-in defaults

    Returns:
        ServerConfig: Fully populated configuration object.
    """
    cfg = ServerConfig()

    # Determine which config file to use
    config_file = None
    if CONFIG_FILE.exists():
        config_file = CONFIG_FILE
    elif CONFIG_EXAMPLE.exists():
        # Use example as fallback for development
        config_file = CONFIG_EXAMPLE

    # Load from INI file if available
    if config_file:
        parser = configparser.ConfigParser()
        parser.read(config_file)
        _load_from_ini(parser, cfg)

    # Apply environment variable overrides (highest priority)
    _apply_env_overrides(cfg)

    return cfg


def reload_config() -> "ServerConfig":
    """
    Reload configuration from disk and environment.

    This updates the module-level `config` singleton. Use sparingly as it
    doesn't update already-running server middleware.

    Returns:
        ServerConfig: The newly loaded configuration.
    """
    global config
    config = load_config()
    return config


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

# Load configuration once at module import time
config = load_config()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def get_config_status() -> dict:
    """
    Get configuration status for diagnostics.

    Returns a dictionary with configuration source information,
    useful for debugging and admin dashboards.
    """
    return {
        "config_file_exists": CONFIG_FILE.exists(),
        "config_file_path": str(CONFIG_FILE),
        "using_example": not CONFIG_FILE.exists() and CONFIG_EXAMPLE.exists(),
        "production_mode": config.is_production,
        "cors_origins_count": len(config.security.cors_origins),
        "docs_enabled": config.docs_should_be_enabled,
    }


def print_config_summary() -> None:
    """Print a summary of current configuration to stdout."""
    status = get_config_status()
    print("\n" + "=" * 60)
    print("SERVER CONFIGURATION")
    print("=" * 60)
    print(f"Config file: {status['config_file_path']}")
    print(f"File exists: {status['config_file_exists']}")
    if status["using_example"]:
        print("WARNING: Using example config (copy to server.ini for production)")
    print("-" * 60)
    print(f"Server:      {config.server.host}:{config.server.port}")
    print(f"Production:  {config.is_production}")
    print(f"CORS origins: {config.security.cors_origins}")
    print(f"Docs enabled: {config.docs_should_be_enabled}")
    print(f"Database:    {config.database.absolute_path}")
    print(f"Log level:   {config.logging.level}")
    print("=" * 60 + "\n")


# =============================================================================
# TEST HELPERS
# =============================================================================


class use_test_database:
    """
    Context manager for using a temporary test database.

    This is the recommended way to set up test databases. It properly
    configures the config system to use a temporary database path.

    Usage:
        from mud_server.config import use_test_database

        def test_something(tmp_path):
            db_path = tmp_path / "test.db"
            with use_test_database(db_path):
                # Database operations will use db_path
                database.init_database()

    Args:
        db_path: Path to the test database file
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.original_path: str | None = None

    def __enter__(self) -> Path:
        """Set up test database path."""
        self.original_path = config.database.path
        config.database.path = str(self.db_path)
        return self.db_path

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Restore original database path."""
        if self.original_path is not None:
            config.database.path = self.original_path
        return None
