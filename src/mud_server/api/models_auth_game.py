"""Authentication and game-facing Pydantic models for the API layer."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """
    Login request with username and password.

    Attributes:
        username: Account username (case-sensitive for database lookup)
        password: Plain text password (will be verified against bcrypt hash)
        world_id: Optional world id used to filter characters on login
    """

    username: str
    password: str
    world_id: str | None = None


class RegisterRequest(BaseModel):
    """
    Registration request for creating a new player account.

    Attributes:
        username: Desired username (2-20 characters, must be unique)
        password: Desired password (minimum 8 characters)
        password_confirm: Password confirmation (must match password)
    """

    username: str
    password: str
    password_confirm: str


class RegisterGuestRequest(BaseModel):
    """
    Registration request for creating a temporary guest account.

    Attributes:
        password: Desired password (validated against STANDARD policy)
        password_confirm: Password confirmation (must match password)
        character_name: Initial character name for the guest account
    """

    password: str
    password_confirm: str
    character_name: str


class SelectCharacterRequest(BaseModel):
    """
    Request to select an active character for a session.

    Attributes:
        session_id: Active session ID for authentication
        character_id: Character id to bind to the session
        world_id: World id to bind to the session (must match character's world)
    """

    session_id: str
    character_id: int
    world_id: str | None = None


class PlayerCreateCharacterRequest(BaseModel):
    """
    Authenticated account request to self-provision a generated character.

    Attributes:
        session_id: Active account session id.
        world_id: Target world id for character creation.
    """

    session_id: str
    world_id: str


class ConditionAxisIdentityInputs(BaseModel):
    """Identity inputs required by canonical condition-axis generation.

    Attributes:
        gender: Canonical gender token used by policy/runtime selection.
    """

    model_config = ConfigDict(extra="forbid")

    gender: str


class ConditionAxisEntityInputs(BaseModel):
    """Entity-level inputs accepted by condition-axis generation.

    Attributes:
        identity: Required identity metadata block.
        species: Canonical species token.
        axes: Optional pre-resolved axis payload for future parity flows.
    """

    model_config = ConfigDict(extra="forbid")

    identity: ConditionAxisIdentityInputs
    species: str
    axes: dict[str, Any] | None = None


class ConditionAxisGenerateInputs(BaseModel):
    """Runtime input wrapper for condition-axis generation requests.

    Attributes:
        entity: Runtime entity input block consumed by strict validation.
    """

    model_config = ConfigDict(extra="forbid")

    entity: ConditionAxisEntityInputs


class ConditionAxisGenerateRequest(BaseModel):
    """Canonical request for ``POST /api/pipeline/condition-axis/generate``.

    Attributes:
        world_id: Target canonical world identifier.
        seed: Optional deterministic seed in ``1..2147483647``.
        bundle_id: Optional policy-bundle override.
        inputs: Runtime input payload validated against strict schema.
    """

    model_config = ConfigDict(extra="forbid")

    world_id: str
    seed: int | None = Field(default=None, ge=1, le=2_147_483_647)
    bundle_id: str | None = None
    inputs: ConditionAxisGenerateInputs


class ConditionAxisProvenanceResponse(BaseModel):
    """Provenance metadata for one condition-axis generation response.

    Attributes:
        source: Canonical source/ownership identifier.
        served_via: API path that served the generated payload.
        generator: Upstream generator system name.
        generator_version: Upstream version/capability identifier.
        generator_capabilities: Ordered upstream capability tokens.
        generated_at: Generation completion timestamp (ISO-8601).
    """

    source: str
    served_via: str
    generator: str
    generator_version: str
    generator_capabilities: list[str] = Field(default_factory=list)
    generated_at: str


class ConditionAxisGenerateResponse(BaseModel):
    """Canonical response for ``POST /api/pipeline/condition-axis/generate``.

    Attributes:
        world_id: Target world identifier.
        bundle_id: Effective policy bundle id.
        bundle_version: Effective policy bundle version.
        policy_hash: Deterministic policy hash for reproducibility.
        seed: Deterministic generation seed used upstream.
        axes: Canonical axis map of ``axis_name -> score``.
        provenance: Canonical provenance block.
    """

    world_id: str
    bundle_id: str
    bundle_version: str
    policy_hash: str | None
    seed: int
    axes: dict[str, float]
    provenance: ConditionAxisProvenanceResponse


class LoginDirectRequest(BaseModel):
    """
    Direct login request that binds a session to a world + character.

    Attributes:
        username: Account username (case-sensitive for database lookup)
        password: Plain text password (will be verified against bcrypt hash)
        world_id: Target world id (must be accessible by the user)
        character_name: Existing character name (optional)
        create_character: When true, create the character if missing
    """

    username: str
    password: str
    world_id: str
    character_name: str | None = None
    create_character: bool = False


class ChangePasswordRequest(BaseModel):
    """
    Request to change the current user's password.

    Attributes:
        session_id: Active session ID for authentication
        old_password: Current password (verified before change)
        new_password: New password (minimum 8 characters, must differ from old)
    """

    session_id: str
    old_password: str
    new_password: str


class LogoutRequest(BaseModel):
    """
    Request to logout and end the current session.

    Attributes:
        session_id: Active session ID to be terminated
    """

    session_id: str


class CommandRequest(BaseModel):
    """
    Request to execute a game command.

    Supports all game commands including movement, inventory management,
    chat, and special commands. Commands can be prefixed with "/" or not.

    Attributes:
        session_id: Active session ID for authentication
        command: Game command to execute, examples:
            - Movement: "north", "n", "south", "s", "east", "e", "west", "w", "up", "u", "down", "d"
            - Actions: "look", "inventory", "get <item>", "drop <item>"
            - Chat: "say <message>", "yell <message>", "whisper <player> <message>"
            - Info: "who", "help"
    """

    session_id: str
    command: str


class LoginResponse(BaseModel):
    """
    Response to login request.

    Attributes:
        success: True if login succeeded, False otherwise
        message: Welcome message on success, error message on failure
        session_id: (Optional) UUID session identifier on successful login
        role: (Optional) User's role on successful login
            ("player", "worldbuilder", "admin", or "superuser")
        characters: List of available characters for selection
        available_worlds: List of available worlds for selection
    """

    success: bool
    message: str
    session_id: str | None = None
    role: str | None = None
    characters: list[dict[str, Any]] = Field(default_factory=list)
    available_worlds: list[dict[str, Any]] = Field(default_factory=list)


class LoginDirectResponse(BaseModel):
    """
    Response to direct login request.

    Attributes:
        success: True if login succeeded, False otherwise
        message: Welcome message on success, error message on failure
        session_id: Session identifier on successful login
        role: User's role on successful login
        character_name: Selected character name on success
        world_id: World bound to the session
    """

    success: bool
    message: str
    session_id: str | None = None
    role: str | None = None
    character_name: str | None = None
    world_id: str | None = None


class SelectCharacterResponse(BaseModel):
    """
    Response to character selection request.

    Attributes:
        success: True if character selected
        message: Success or error message
        character_name: Selected character name on success
    """

    success: bool
    message: str
    character_name: str | None = None


class CharactersResponse(BaseModel):
    """
    Response containing the user's characters.

    Attributes:
        characters: List of character summaries
    """

    characters: list[dict[str, Any]]


class RegisterResponse(BaseModel):
    """
    Response to registration request.

    Attributes:
        success: True if account created, False otherwise
        message: Success confirmation or error details
    """

    success: bool
    message: str


class RegisterGuestResponse(BaseModel):
    """
    Response to guest registration request.

    Attributes:
        success: True if account created, False otherwise
        message: Success confirmation or error details
        username: Generated guest username for login
        character_id: Created character id for the guest account
        character_name: Created character name
        world_id: Character world id
        entity_state: Optional entity-state payload from the entity service
        entity_state_error: Optional entity-state integration error message
    """

    success: bool
    message: str
    username: str | None = None
    character_id: int | None = None
    character_name: str | None = None
    world_id: str | None = None
    entity_state: dict[str, Any] | None = None
    entity_state_error: str | None = None


class CommandResponse(BaseModel):
    """
    Response to game command execution.

    Attributes:
        success: True if command executed successfully, False for errors
        message: Command result, room description, error message, etc.
            For movement: includes new room description
            For inventory: lists items in inventory
            For chat: confirmation message
            For errors: explanation of what went wrong
    """

    success: bool
    message: str


class StatusResponse(BaseModel):
    """
    Response containing player's current game status.

    Used for periodic status updates to keep the UI synchronized.

    Attributes:
        active_players: List of usernames currently online
        current_room: Player's current room ID (e.g., "spawn", "forest_1")
        inventory: Formatted inventory string (e.g., "Your inventory:\\n  - Torch\\n  - Rope")
    """

    active_players: list[str]
    current_room: str | None
    inventory: str
