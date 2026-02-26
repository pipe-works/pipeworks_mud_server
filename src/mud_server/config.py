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
    MUD_SESSION_TTL_MINUTES         -> session.ttl_minutes
    MUD_SESSION_SLIDING_EXPIRATION  -> session.sliding_expiration
    MUD_SESSION_ALLOW_MULTIPLE      -> session.allow_multiple_sessions
    MUD_SESSION_ACTIVE_WINDOW_MINUTES -> session.active_window_minutes
    MUD_CHAR_DEFAULT_SLOTS          -> characters.default_slots
    MUD_CHAR_MAX_SLOTS              -> characters.max_slots
    MUD_ENTITY_STATE_ENABLED        -> integrations.entity_state_enabled
    MUD_ENTITY_STATE_BASE_URL       -> integrations.entity_state_base_url
    MUD_ENTITY_STATE_TIMEOUT_SECONDS -> integrations.entity_state_timeout_seconds
    MUD_ENTITY_STATE_INCLUDE_PROMPTS -> integrations.entity_state_include_prompts
    MUD_NAMEGEN_ENABLED             -> integrations.namegen_enabled
    MUD_NAMEGEN_BASE_URL            -> integrations.namegen_base_url
    MUD_NAMEGEN_TIMEOUT_SECONDS     -> integrations.namegen_timeout_seconds
    MUD_REGISTRATION_MODE           -> registration.account_registration_mode
    MUD_GUEST_REGISTRATION_ENABLED  -> registration.guest_registration_enabled
    MUD_PLAYER_SELF_CREATE_ENABLED  -> character_creation.player_self_create_enabled
    MUD_CHAR_CREATE_DEFAULT_MODE    -> character_creation.default_creation_mode
    MUD_CHAR_CREATE_DEFAULT_NAMING  -> character_creation.default_naming_mode
    MUD_CHAR_CREATE_DEFAULT_SLOT_LIMIT -> character_creation.default_world_slot_limit
    MUD_TRANSLATION_ENABLED         -> ollama_translation.enabled
    MUD_TRANSLATION_OLLAMA_URL      -> ollama_translation.base_url
    MUD_TRANSLATION_TIMEOUT         -> ollama_translation.timeout_seconds
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

    ttl_minutes: int = 480  # 8 hours default
    sliding_expiration: bool = True  # Extend expiry on each validated request
    allow_multiple_sessions: bool = False  # False = single session per user
    active_window_minutes: int = 30  # Active if last_activity within this window


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
class CharacterSettings:
    """Character slot limits and defaults."""

    default_slots: int = 2
    max_slots: int = 10


@dataclass
class RegistrationSettings:
    """Account-registration policy controls."""

    account_registration_mode: Literal["open", "closed"] = "open"
    guest_registration_enabled: bool = True


@dataclass
class WorldCharacterPolicy:
    """
    Character-creation policy for a specific world.

    Attributes:
        creation_mode: ``open`` allows account holders to self-create in the
            world. ``invite`` requires explicit world permission.
        naming_mode: ``generated`` means the server mints names. ``manual`` is
            currently reserved for admin/superuser workflows.
        slot_limit_per_account: Maximum characters an account may own in this
            world.
    """

    creation_mode: Literal["open", "invite"] = "invite"
    naming_mode: Literal["generated", "manual"] = "generated"
    slot_limit_per_account: int = 10


@dataclass
class CharacterCreationSettings:
    """
    Global character-creation policy and world-level overrides.

    The defaults define baseline behavior for all worlds. Per-world sections in
    INI (``[world_policy.<world_id>]``) can override individual fields.
    """

    player_self_create_enabled: bool = True
    default_creation_mode: Literal["open", "invite"] = "invite"
    default_naming_mode: Literal["generated", "manual"] = "generated"
    default_world_slot_limit: int = 10
    world_policy_overrides: dict[str, WorldCharacterPolicy] = field(default_factory=dict)

    def resolve_world_policy(self, world_id: str) -> WorldCharacterPolicy:
        """
        Resolve effective character policy for ``world_id``.

        Resolution order:
            1. ``[world_policy.<world_id>]`` override
            2. Global defaults from ``[character_creation]``
        """
        normalized_world_id = world_id.strip()
        override = self.world_policy_overrides.get(normalized_world_id)
        if override is not None:
            return override
        return WorldCharacterPolicy(
            creation_mode=self.default_creation_mode,
            naming_mode=self.default_naming_mode,
            slot_limit_per_account=self.default_world_slot_limit,
        )


@dataclass
class FeatureSettings:
    """Feature flags."""

    ollama_enabled: bool = True
    verbose_errors: bool = False


@dataclass
class WorldSettings:
    """Multi-world configuration settings."""

    worlds_root: str = "data/worlds"
    default_world_id: str = "pipeworks_web"
    allow_multi_world_characters: bool = False


@dataclass
class IntegrationSettings:
    """External integration settings."""

    entity_state_enabled: bool = True
    entity_state_base_url: str = "https://entity.pipe-works.org"
    entity_state_timeout_seconds: float = 3.0
    entity_state_include_prompts: bool = False
    namegen_enabled: bool = True
    namegen_base_url: str = "https://name.api.pipe-works.org"
    namegen_timeout_seconds: float = 3.0


@dataclass
class OllamaTranslationSettings:
    """Server-level controls for the OOC→IC translation layer.

    Acts as the master switch and provides server-wide defaults.  Per-world
    config in ``world.json`` is checked second; both must be enabled for
    translation to activate.
    """

    enabled: bool = True
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 10.0


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
    characters: CharacterSettings = field(default_factory=CharacterSettings)
    registration: RegistrationSettings = field(default_factory=RegistrationSettings)
    character_creation: CharacterCreationSettings = field(default_factory=CharacterCreationSettings)
    features: FeatureSettings = field(default_factory=FeatureSettings)
    worlds: WorldSettings = field(default_factory=WorldSettings)
    integrations: IntegrationSettings = field(default_factory=IntegrationSettings)
    ollama_translation: OllamaTranslationSettings = field(default_factory=OllamaTranslationSettings)

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

    def resolve_world_character_policy(self, world_id: str) -> WorldCharacterPolicy:
        """Resolve world-level character-creation policy for ``world_id``."""
        return self.character_creation.resolve_world_policy(world_id)


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


def _parse_creation_mode(
    value: str, *, default: Literal["open", "invite"]
) -> Literal["open", "invite"]:
    """
    Parse world creation mode and gracefully fallback on invalid values.

    This parser is intentionally tolerant: invalid deployment values should not
    crash startup and instead fallback to a safe, explicit default.
    """
    normalized = value.strip().lower()
    if normalized in {"open", "invite"}:
        return normalized  # type: ignore[return-value]
    return default


def _parse_registration_mode(
    value: str, *, default: Literal["open", "closed"]
) -> Literal["open", "closed"]:
    """Parse account registration mode and fallback on invalid values."""
    normalized = value.strip().lower()
    if normalized in {"open", "closed"}:
        return normalized  # type: ignore[return-value]
    return default


def _parse_naming_mode(
    value: str, *, default: Literal["generated", "manual"]
) -> Literal["generated", "manual"]:
    """
    Parse world naming mode and fallback on invalid values.

    Current policy keeps ``manual`` naming for privileged admin workflows.
    Player self-service creation currently relies on ``generated`` names.
    """
    normalized = value.strip().lower()
    if normalized in {"generated", "manual"}:
        return normalized  # type: ignore[return-value]
    return default


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
        if parser.has_option("session", "ttl_minutes"):
            cfg.session.ttl_minutes = parser.getint("session", "ttl_minutes")
        if parser.has_option("session", "sliding_expiration"):
            cfg.session.sliding_expiration = _parse_bool(
                parser.get("session", "sliding_expiration")
            )
        if parser.has_option("session", "allow_multiple_sessions"):
            cfg.session.allow_multiple_sessions = _parse_bool(
                parser.get("session", "allow_multiple_sessions")
            )
        if parser.has_option("session", "active_window_minutes"):
            cfg.session.active_window_minutes = parser.getint("session", "active_window_minutes")

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

    # Character slots section
    if parser.has_section("characters"):
        if parser.has_option("characters", "default_slots"):
            cfg.characters.default_slots = parser.getint("characters", "default_slots")
        if parser.has_option("characters", "max_slots"):
            cfg.characters.max_slots = parser.getint("characters", "max_slots")

    # Registration policy section
    if parser.has_section("registration"):
        if parser.has_option("registration", "account_registration_mode"):
            cfg.registration.account_registration_mode = _parse_registration_mode(
                parser.get("registration", "account_registration_mode"),
                default=cfg.registration.account_registration_mode,
            )
        if parser.has_option("registration", "guest_registration_enabled"):
            cfg.registration.guest_registration_enabled = _parse_bool(
                parser.get("registration", "guest_registration_enabled")
            )

    # Character-creation policy section
    if parser.has_section("character_creation"):
        if parser.has_option("character_creation", "player_self_create_enabled"):
            cfg.character_creation.player_self_create_enabled = _parse_bool(
                parser.get("character_creation", "player_self_create_enabled")
            )
        if parser.has_option("character_creation", "default_creation_mode"):
            cfg.character_creation.default_creation_mode = _parse_creation_mode(
                parser.get("character_creation", "default_creation_mode"),
                default=cfg.character_creation.default_creation_mode,
            )
        if parser.has_option("character_creation", "default_naming_mode"):
            cfg.character_creation.default_naming_mode = _parse_naming_mode(
                parser.get("character_creation", "default_naming_mode"),
                default=cfg.character_creation.default_naming_mode,
            )
        if parser.has_option("character_creation", "default_world_slot_limit"):
            cfg.character_creation.default_world_slot_limit = parser.getint(
                "character_creation",
                "default_world_slot_limit",
            )

    # Features section
    if parser.has_section("features"):
        if parser.has_option("features", "ollama_enabled"):
            cfg.features.ollama_enabled = _parse_bool(parser.get("features", "ollama_enabled"))
        if parser.has_option("features", "verbose_errors"):
            cfg.features.verbose_errors = _parse_bool(parser.get("features", "verbose_errors"))

    # Worlds section
    if parser.has_section("worlds"):
        if parser.has_option("worlds", "worlds_root"):
            cfg.worlds.worlds_root = parser.get("worlds", "worlds_root")
        if parser.has_option("worlds", "default_world_id"):
            cfg.worlds.default_world_id = parser.get("worlds", "default_world_id")
        if parser.has_option("worlds", "allow_multi_world_characters"):
            cfg.worlds.allow_multi_world_characters = _parse_bool(
                parser.get("worlds", "allow_multi_world_characters")
            )

    # Integrations section
    if parser.has_section("integrations"):
        if parser.has_option("integrations", "entity_state_enabled"):
            cfg.integrations.entity_state_enabled = _parse_bool(
                parser.get("integrations", "entity_state_enabled")
            )
        if parser.has_option("integrations", "entity_state_base_url"):
            cfg.integrations.entity_state_base_url = parser.get(
                "integrations", "entity_state_base_url"
            )
        if parser.has_option("integrations", "entity_state_timeout_seconds"):
            cfg.integrations.entity_state_timeout_seconds = parser.getfloat(
                "integrations", "entity_state_timeout_seconds"
            )
        if parser.has_option("integrations", "entity_state_include_prompts"):
            cfg.integrations.entity_state_include_prompts = _parse_bool(
                parser.get("integrations", "entity_state_include_prompts")
            )
        if parser.has_option("integrations", "namegen_enabled"):
            cfg.integrations.namegen_enabled = _parse_bool(
                parser.get("integrations", "namegen_enabled")
            )
        if parser.has_option("integrations", "namegen_base_url"):
            cfg.integrations.namegen_base_url = parser.get("integrations", "namegen_base_url")
        if parser.has_option("integrations", "namegen_timeout_seconds"):
            cfg.integrations.namegen_timeout_seconds = parser.getfloat(
                "integrations", "namegen_timeout_seconds"
            )

    # Ollama translation section
    if parser.has_section("ollama_translation"):
        if parser.has_option("ollama_translation", "enabled"):
            cfg.ollama_translation.enabled = _parse_bool(
                parser.get("ollama_translation", "enabled")
            )
        if parser.has_option("ollama_translation", "base_url"):
            cfg.ollama_translation.base_url = parser.get("ollama_translation", "base_url")
        if parser.has_option("ollama_translation", "timeout_seconds"):
            cfg.ollama_translation.timeout_seconds = parser.getfloat(
                "ollama_translation", "timeout_seconds"
            )

    # Per-world character policy sections:
    #   [world_policy.<world_id>]
    # This keeps deployment policy in config rather than requiring schema
    # changes for every policy tweak.
    for section_name in parser.sections():
        if not section_name.startswith("world_policy."):
            continue
        world_id = section_name[len("world_policy.") :].strip()
        if not world_id:
            continue

        resolved_policy = cfg.resolve_world_character_policy(world_id)
        world_policy = WorldCharacterPolicy(
            creation_mode=resolved_policy.creation_mode,
            naming_mode=resolved_policy.naming_mode,
            slot_limit_per_account=resolved_policy.slot_limit_per_account,
        )

        if parser.has_option(section_name, "creation_mode"):
            world_policy.creation_mode = _parse_creation_mode(
                parser.get(section_name, "creation_mode"),
                default=world_policy.creation_mode,
            )
        if parser.has_option(section_name, "naming_mode"):
            world_policy.naming_mode = _parse_naming_mode(
                parser.get(section_name, "naming_mode"),
                default=world_policy.naming_mode,
            )
        if parser.has_option(section_name, "slot_limit_per_account"):
            world_policy.slot_limit_per_account = parser.getint(
                section_name,
                "slot_limit_per_account",
            )

        cfg.character_creation.world_policy_overrides[world_id] = world_policy


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

    # Session settings
    if env_ttl := os.getenv("MUD_SESSION_TTL_MINUTES"):
        cfg.session.ttl_minutes = int(env_ttl)
    if env_sliding := os.getenv("MUD_SESSION_SLIDING_EXPIRATION"):
        cfg.session.sliding_expiration = _parse_bool(env_sliding)
    if env_allow_multiple := os.getenv("MUD_SESSION_ALLOW_MULTIPLE"):
        cfg.session.allow_multiple_sessions = _parse_bool(env_allow_multiple)
    if env_active_window := os.getenv("MUD_SESSION_ACTIVE_WINDOW_MINUTES"):
        cfg.session.active_window_minutes = int(env_active_window)

    # Character slots
    if env_default_slots := os.getenv("MUD_CHAR_DEFAULT_SLOTS"):
        cfg.characters.default_slots = int(env_default_slots)
    if env_max_slots := os.getenv("MUD_CHAR_MAX_SLOTS"):
        cfg.characters.max_slots = int(env_max_slots)

    # Registration policy
    if env_registration_mode := os.getenv("MUD_REGISTRATION_MODE"):
        cfg.registration.account_registration_mode = _parse_registration_mode(
            env_registration_mode,
            default=cfg.registration.account_registration_mode,
        )
    if env_guest_registration := os.getenv("MUD_GUEST_REGISTRATION_ENABLED"):
        cfg.registration.guest_registration_enabled = _parse_bool(env_guest_registration)

    # Character-creation policy
    if env_player_create_enabled := os.getenv("MUD_PLAYER_SELF_CREATE_ENABLED"):
        cfg.character_creation.player_self_create_enabled = _parse_bool(env_player_create_enabled)
    if env_default_create_mode := os.getenv("MUD_CHAR_CREATE_DEFAULT_MODE"):
        cfg.character_creation.default_creation_mode = _parse_creation_mode(
            env_default_create_mode,
            default=cfg.character_creation.default_creation_mode,
        )
    if env_default_naming_mode := os.getenv("MUD_CHAR_CREATE_DEFAULT_NAMING"):
        cfg.character_creation.default_naming_mode = _parse_naming_mode(
            env_default_naming_mode,
            default=cfg.character_creation.default_naming_mode,
        )
    if env_default_slot_limit := os.getenv("MUD_CHAR_CREATE_DEFAULT_SLOT_LIMIT"):
        cfg.character_creation.default_world_slot_limit = int(env_default_slot_limit)

    # World settings
    if env_worlds_root := os.getenv("MUD_WORLDS_ROOT"):
        cfg.worlds.worlds_root = env_worlds_root
    if env_default_world := os.getenv("MUD_DEFAULT_WORLD_ID"):
        cfg.worlds.default_world_id = env_default_world
    if env_allow_multi_world := os.getenv("MUD_ALLOW_MULTI_WORLD_CHARACTERS"):
        cfg.worlds.allow_multi_world_characters = _parse_bool(env_allow_multi_world)

    # Integration settings
    if env_entity_enabled := os.getenv("MUD_ENTITY_STATE_ENABLED"):
        cfg.integrations.entity_state_enabled = _parse_bool(env_entity_enabled)
    if env_entity_base_url := os.getenv("MUD_ENTITY_STATE_BASE_URL"):
        cfg.integrations.entity_state_base_url = env_entity_base_url
    if env_entity_timeout := os.getenv("MUD_ENTITY_STATE_TIMEOUT_SECONDS"):
        cfg.integrations.entity_state_timeout_seconds = float(env_entity_timeout)
    if env_entity_prompts := os.getenv("MUD_ENTITY_STATE_INCLUDE_PROMPTS"):
        cfg.integrations.entity_state_include_prompts = _parse_bool(env_entity_prompts)
    if env_namegen_enabled := os.getenv("MUD_NAMEGEN_ENABLED"):
        cfg.integrations.namegen_enabled = _parse_bool(env_namegen_enabled)
    if env_namegen_base_url := os.getenv("MUD_NAMEGEN_BASE_URL"):
        cfg.integrations.namegen_base_url = env_namegen_base_url
    if env_namegen_timeout := os.getenv("MUD_NAMEGEN_TIMEOUT_SECONDS"):
        cfg.integrations.namegen_timeout_seconds = float(env_namegen_timeout)

    # Ollama translation settings
    if env_translation_enabled := os.getenv("MUD_TRANSLATION_ENABLED"):
        cfg.ollama_translation.enabled = _parse_bool(env_translation_enabled)
    if env_translation_url := os.getenv("MUD_TRANSLATION_OLLAMA_URL"):
        cfg.ollama_translation.base_url = env_translation_url
    if env_translation_timeout := os.getenv("MUD_TRANSLATION_TIMEOUT"):
        cfg.ollama_translation.timeout_seconds = float(env_translation_timeout)


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
    print(f"Session TTL: {config.session.ttl_minutes} minutes")
    print(f"Sliding Exp: {config.session.sliding_expiration}")
    print(f"Multi-Session: {config.session.allow_multiple_sessions}")
    print(f"Active Window: {config.session.active_window_minutes} minutes")
    print(
        "Registration: "
        f"mode={config.registration.account_registration_mode} "
        f"guest_enabled={config.registration.guest_registration_enabled}"
    )
    print(
        "Character Create: "
        f"player_self_create={config.character_creation.player_self_create_enabled} "
        f"default_mode={config.character_creation.default_creation_mode} "
        f"default_naming={config.character_creation.default_naming_mode} "
        f"default_slots={config.character_creation.default_world_slot_limit}"
    )
    print(f"Log level:   {config.logging.level}")
    print(
        f"Entity API:  enabled={config.integrations.entity_state_enabled} "
        f"url={config.integrations.entity_state_base_url} "
        f"timeout={config.integrations.entity_state_timeout_seconds}s"
    )
    print(
        f"Name API:    enabled={config.integrations.namegen_enabled} "
        f"url={config.integrations.namegen_base_url} "
        f"timeout={config.integrations.namegen_timeout_seconds}s"
    )
    print(
        f"Translation: enabled={config.ollama_translation.enabled} "
        f"url={config.ollama_translation.base_url} "
        f"timeout={config.ollama_translation.timeout_seconds}s"
    )
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
