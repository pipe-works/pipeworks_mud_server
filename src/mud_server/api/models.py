"""
Pydantic models for API requests and responses.

This module defines all the data models used for API communication between
the FastAPI backend and clients (admin WebUI, API consumers). Pydantic models provide:
- Automatic request/response validation
- Type checking and conversion
- Clear API documentation via FastAPI's automatic OpenAPI schema generation
- Serialization/deserialization to/from JSON

Models are organized into two categories:
1. Request models: Data sent FROM the client TO the server
2. Response models: Data sent FROM the server TO the client
"""

from typing import Any

from pydantic import BaseModel

# ============================================================================
# REQUEST MODELS (Client → Server)
# ============================================================================


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


class UserManagementRequest(BaseModel):
    """
    Admin request to manage user accounts.

    Requires admin or superuser permissions. Allows role changes, banning,
    unbanning, and password changes of user accounts. Superusers can manage
    all users, admins can only manage users with lower permissions.

    Attributes:
        session_id: Active session ID (must have appropriate permission)
        target_username: Username of the account to manage
        action: Management action - one of:
            - "change_role": Change user's role (requires new_role parameter)
            - "ban" or "deactivate": Deactivate user account (prevents login, removes active session)
            - "delete": Permanently delete user and related data (superuser only)
            - "unban": Reactivate previously banned account
            - "change_password": Change user's password (requires new_password parameter)
        new_role: (Optional) New role when action is "change_role"
            Valid roles: "player", "worldbuilder", "admin", "superuser"
        new_password: (Optional) New password when action is "change_password"
            Must be at least 8 characters
    """

    session_id: str
    target_username: str
    action: str  # "change_role", "ban", "deactivate", "unban", "change_password"
    new_role: str | None = None
    new_password: str | None = None


class CreateUserRequest(BaseModel):
    """
    Admin request to create a new user account.

    Requires admin or superuser permissions. Admins may create Player or
    WorldBuilder accounts. Superusers may create any role, including Admin
    and Superuser.

    Passwords must meet the STANDARD password policy, and password_confirm
    must match password.

    Attributes:
        session_id: Active session ID (must have appropriate permission)
        username: Desired username (2-20 characters, must be unique)
        password: Desired password (must meet STANDARD policy)
        password_confirm: Password confirmation (must match password)
        role: Role to assign to the new account
            Valid roles: "player", "worldbuilder", "admin", "superuser"
    """

    session_id: str
    username: str
    password: str
    password_confirm: str
    role: str


class ServerStopRequest(BaseModel):
    """
    Admin request to stop the server gracefully.

    Requires STOP_SERVER permission (admin or superuser only).
    Server will shutdown 0.5 seconds after sending response to allow
    the HTTP response to be delivered.

    Attributes:
        session_id: Active session ID (must have STOP_SERVER permission)
    """

    session_id: str


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


class ChatRequest(BaseModel):
    """
    Request to send a chat message.

    Note: This model is defined but may not be actively used.
    Chat is typically sent via CommandRequest with "/say" command.

    Attributes:
        session_id: Active session ID for authentication
        message: Chat message text
    """

    session_id: str
    message: str


# ============================================================================
# RESPONSE MODELS (Server → Client)
# ============================================================================


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
    characters: list[dict[str, Any]] = []
    available_worlds: list[dict[str, Any]] = []


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
    """

    success: bool
    message: str
    username: str | None = None


class CreateUserResponse(BaseModel):
    """
    Response to admin user creation request.

    Attributes:
        success: True if account created, False otherwise
        message: Success confirmation or error details
    """

    success: bool
    message: str


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
        inventory: Formatted inventory string (e.g., "Your inventory:\n  - Torch\n  - Rope")
    """

    active_players: list[str]
    current_room: str | None
    inventory: str


class UserListResponse(BaseModel):
    """
    Response containing list of user accounts.

    Used for admin user management interfaces.

    Attributes:
        users: List of user data dictionaries with account information
    """

    users: list[dict[str, Any]]


class DatabasePlayersResponse(BaseModel):
    """
    Admin response containing all user records from database.

    Requires VIEW_LOGS permission. Includes account details and character counts.

    Attributes:
        players: List of user data dictionaries with fields:
            - id: Database record ID
            - username: Account username
            - password_hash: Truncated password hash (first 20 chars + "...")
            - role: User role
            - account_origin: Account provenance ("visitor", "admin", "superuser", "system", "legacy")
            - is_guest: Guest flag
            - guest_expires_at: Guest expiry timestamp
            - character_count: Number of linked characters
            - created_at: Account creation timestamp
            - last_login: Last login timestamp
            - is_active: Account status (True=active, False=banned)
    """

    players: list[dict[str, Any]]


class DatabaseTableInfo(BaseModel):
    """
    Metadata about a single database table.

    Attributes:
        name: Table name.
        columns: List of column names in order.
        row_count: Number of rows in the table.
    """

    name: str
    columns: list[str]
    row_count: int


class DatabaseTablesResponse(BaseModel):
    """
    Admin response containing database table metadata.

    Requires VIEW_LOGS permission. Used for table discovery in the admin UI.

    Attributes:
        tables: List of DatabaseTableInfo entries.
    """

    tables: list[DatabaseTableInfo]


class DatabaseSchemaForeignKey(BaseModel):
    """
    Foreign key metadata for a database table relationship.

    Attributes:
        from_column: Column on the source table.
        ref_table: Referenced table name.
        ref_column: Referenced column name.
        on_update: SQLite ON UPDATE action.
        on_delete: SQLite ON DELETE action.
    """

    from_column: str
    ref_table: str
    ref_column: str
    on_update: str
    on_delete: str


class DatabaseSchemaTable(BaseModel):
    """
    Schema metadata for a database table.

    Attributes:
        name: Table name.
        columns: Column names in order.
        foreign_keys: Foreign key relationships.
    """

    name: str
    columns: list[str]
    foreign_keys: list[DatabaseSchemaForeignKey]


class DatabaseSchemaResponse(BaseModel):
    """
    Admin response containing database schema relationships.

    Requires VIEW_LOGS permission. Used for schema map displays.

    Attributes:
        tables: Schema metadata for all tables.
    """

    tables: list[DatabaseSchemaTable]


class DatabaseTableRowsResponse(BaseModel):
    """
    Admin response containing rows for a specific database table.

    Requires VIEW_LOGS permission. Includes column names and raw row values.

    Attributes:
        table: Table name.
        columns: Column names in order.
        rows: Row values as a list of rows (each row is a list of values).
    """

    table: str
    columns: list[str]
    rows: list[list[Any]]


class DatabasePlayerLocationsResponse(BaseModel):
    """
    Admin response containing character locations with names.

    Requires VIEW_LOGS permission. Useful for cross-referencing room occupancy.

    Attributes:
        locations: List of dicts with fields:
            - character_id
            - character_name
            - zone_id
            - room_id
            - updated_at
    """

    locations: list[dict[str, Any]]


class DatabaseConnectionsResponse(BaseModel):
    """
    Admin response containing active session connections.

    Requires VIEW_LOGS permission. Includes activity age for dashboards.

    Attributes:
        connections: List of session dictionaries with fields:
            - id
            - username
            - session_id
            - created_at
            - last_activity
            - expires_at
            - client_type
            - age_seconds
    """

    connections: list[dict[str, Any]]


class KickSessionRequest(BaseModel):
    """
    Request to force-disconnect a session.

    Requires KICK_USERS permission.

    Attributes:
        session_id: Admin's active session id.
        target_session_id: Session id to disconnect.
        reason: Optional reason for audit/logging.
    """

    session_id: str
    target_session_id: str
    reason: str | None = None


class KickSessionResponse(BaseModel):
    """
    Response for a kick session request.

    Attributes:
        success: True if session was removed.
        message: Human-readable result.
    """

    success: bool
    message: str


class DatabaseSessionsResponse(BaseModel):
    """
    Admin response containing all active sessions from database.

    Requires VIEW_LOGS permission. Shows who is currently logged in.

    Attributes:
        sessions: List of session data dictionaries with fields:
            - id: Database record ID
            - username: Logged in account
            - character_name: Active character for the session (if selected)
            - session_id: UUID session identifier
            - created_at: Login timestamp
            - last_activity: Most recent API request timestamp
            - expires_at: Session expiry timestamp (NULL means no expiry)
            - client_type: Client identifier (tui, browser, api)
    """

    sessions: list[dict[str, Any]]


class DatabaseChatResponse(BaseModel):
    """
    Admin response containing recent chat messages across all rooms.

    Requires VIEW_LOGS permission. Useful for moderation and monitoring.

    Attributes:
        messages: List of chat message dictionaries with fields:
            - id: Database record ID
            - username: Message sender
            - message: Message text (includes [WHISPER], [YELL] prefixes)
            - room: Room ID where message was sent
            - timestamp: Message timestamp
    """

    messages: list[dict[str, Any]]


class UserManagementResponse(BaseModel):
    """
    Response to user management action (role change, ban, unban).

    Attributes:
        success: True if action completed successfully
        message: Confirmation message or error details
    """

    success: bool
    message: str


class ServerStopResponse(BaseModel):
    """
    Response to server stop request.

    Server will shutdown shortly after sending this response.

    Attributes:
        success: True if shutdown initiated
        message: Confirmation message indicating who initiated shutdown
    """

    success: bool
    message: str


class OllamaCommandRequest(BaseModel):
    """
    Request to execute an Ollama command.

    Requires VIEW_LOGS permission (admin or superuser only).

    Attributes:
        session_id: Active session ID (must have appropriate permission)
        server_url: URL of the Ollama server (e.g., "http://localhost:11434")
        command: Ollama command to execute (e.g., "list", "ps", "run llama2")
    """

    session_id: str
    server_url: str
    command: str


class OllamaCommandResponse(BaseModel):
    """
    Response to Ollama command execution.

    Attributes:
        success: True if command executed successfully
        output: Command output or error message
    """

    success: bool
    output: str


class ClearOllamaContextRequest(BaseModel):
    """
    Request to clear Ollama conversation context for the current session.

    Requires VIEW_LOGS permission (admin or superuser only).

    Attributes:
        session_id: Active session ID (must have appropriate permission)
    """

    session_id: str


class ClearOllamaContextResponse(BaseModel):
    """
    Response to clear Ollama context request.

    Attributes:
        success: True if context was cleared successfully
        message: Confirmation message
    """

    success: bool
    message: str
