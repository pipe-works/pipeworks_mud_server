"""
Pydantic models for API requests and responses.

This module defines all the data models used for API communication between
the FastAPI backend and the Gradio frontend. Pydantic models provide:
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
        username: Player's username (case-sensitive for database lookup)
        password: Plain text password (will be verified against bcrypt hash)
    """

    username: str
    password: str


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
            - Movement: "north", "n", "south", "s", "east", "e", "west", "w"
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
    """

    success: bool
    message: str
    session_id: str | None = None
    role: str | None = None


class RegisterResponse(BaseModel):
    """
    Response to registration request.

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
    Admin response containing all player records from database.

    Requires VIEW_LOGS permission. Includes detailed player information
    including password hash prefixes, roles, and account status.

    Attributes:
        players: List of player data dictionaries with fields:
            - id: Database record ID
            - username: Player username
            - password_hash: Truncated password hash (first 20 chars + "...")
            - role: User role
            - current_room: Current location
            - inventory: JSON string of item IDs
            - created_at: Account creation timestamp
            - last_login: Last login timestamp
            - is_active: Account status (True=active, False=banned)
    """

    players: list[dict[str, Any]]


class DatabaseSessionsResponse(BaseModel):
    """
    Admin response containing all active sessions from database.

    Requires VIEW_LOGS permission. Shows who is currently logged in.

    Attributes:
        sessions: List of session data dictionaries with fields:
            - id: Database record ID
            - username: Logged in player
            - session_id: UUID session identifier
            - connected_at: Login timestamp
            - last_activity: Most recent API request timestamp
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
