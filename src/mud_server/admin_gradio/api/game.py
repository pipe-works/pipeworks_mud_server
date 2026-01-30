"""
Game API client for MUD Server.

This module handles all game-related API operations:
- Sending game commands (movement, inventory, chat, etc.)
- Retrieving chat messages from current room
- Fetching player status (location, inventory, active players)
- Refreshing game displays

All functions follow a consistent pattern:
    - Validate session state
    - Validate input
    - Make API request using BaseAPIClient
    - Return standardized response dictionaries

Response Format:
    All functions return dictionaries with:
    {
        "success": bool,         # Whether operation succeeded
        "message": str,          # User-facing message or data
        "data": dict | None,     # Additional structured data if applicable
        "error": str | None,     # Error details if failed
    }
"""

from mud_server.admin_gradio.api.base import BaseAPIClient
from mud_server.admin_gradio.ui.validators import validate_command_input, validate_session_state


class GameAPIClient(BaseAPIClient):
    """
    API client for game operations.

    This client handles in-game interactions including commands, chat,
    and status queries.

    Example:
        >>> client = GameAPIClient()
        >>> result = client.send_command("look", session_id="abc123")
        >>> if result["success"]:
        ...     print(result["message"])
    """

    def send_command(self, command: str, session_id: str | None) -> dict:
        """
        Send a game command to the backend for execution.

        Commands can be:
        - Movement: north, south, east, west, n, s, e, w
        - Inventory: take <item>, drop <item>, inventory, i
        - Chat: say <message>
        - Information: look, status, help

        Args:
            command: Command string to execute
            session_id: User's session ID from login

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,          # Command result/output
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = GameAPIClient()
            >>> result = client.send_command("look", session_id="abc123")
            >>> result["success"]
            True
            >>> "You are in" in result["message"]
            True
        """
        # Validate session
        session_state = {"logged_in": bool(session_id)}
        is_valid, error = validate_session_state(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate command
        is_valid, error = validate_command_input(command)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request
        response = self.post(
            "/command",
            json={"session_id": session_id, "command": command},
        )

        if response["success"]:
            # Extract command result
            data = response["data"]
            return {
                "success": True,
                "message": str(data["message"]),
                "data": None,
                "error": None,
            }
        elif response["status_code"] == 401:
            # Session expired
            return {
                "success": False,
                "message": "Session expired. Please log in again.",
                "data": None,
                "error": "Session expired",
            }
        else:
            # Other error
            return {
                "success": False,
                "message": f"Error: {response['error']}",
                "data": None,
                "error": response["error"],
            }

    def get_chat(self, session_id: str | None) -> dict:
        """
        Retrieve recent chat messages from the current room.

        Args:
            session_id: User's session ID from login

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,          # Formatted chat messages
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = GameAPIClient()
            >>> result = client.get_chat(session_id="abc123")
            >>> result["success"]
            True
        """
        # Validate session
        session_state = {"logged_in": bool(session_id)}
        is_valid, error = validate_session_state(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request
        response = self.get(f"/chat/{session_id}")

        if response["success"]:
            # Extract chat messages
            data = response["data"]
            return {
                "success": True,
                "message": str(data["chat"]),
                "data": None,
                "error": None,
            }
        else:
            return {
                "success": False,
                "message": "Failed to retrieve chat.",
                "data": None,
                "error": response["error"],
            }

    def get_status(self, session_id: str | None, username: str, role: str) -> dict:
        """
        Retrieve and format player status information.

        Returns detailed status including:
        - Username and role
        - Current room location
        - Active players in the game
        - Inventory contents

        Args:
            session_id: User's session ID from login
            username: User's username
            role: User's role (player/worldbuilder/admin/superuser)

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,          # Formatted status display
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = GameAPIClient()
            >>> result = client.get_status("abc123", "alice", "player")
            >>> result["success"]
            True
            >>> "Player Status" in result["message"]
            True
        """
        # Validate session
        session_state = {"logged_in": bool(session_id)}
        is_valid, error = validate_session_state(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request
        response = self.get(f"/status/{session_id}")

        if response["success"]:
            # Format status display
            data = response["data"]
            role_display = role.capitalize() if role else "Player"
            active_players = ", ".join(data["active_players"]) if data["active_players"] else "None"

            status = f"""[Player Status]
Username: {username}
Role: {role_display}
Current Room: {data['current_room']}
Active Players: {active_players}

{data['inventory']}"""

            return {
                "success": True,
                "message": status.strip(),
                "data": None,
                "error": None,
            }
        else:
            return {
                "success": False,
                "message": "Failed to retrieve status.",
                "data": None,
                "error": response["error"],
            }

    def refresh_display(self, session_id: str | None) -> dict:
        """
        Refresh both room and chat displays by fetching current data.

        This is a convenience method that calls both send_command("look")
        and get_chat() to refresh the game display.

        Args:
            session_id: User's session ID from login

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,          # Not used for this method
                "data": {
                    "room": str,         # Room description
                    "chat": str,         # Chat messages
                },
                "error": str | None,
            }

        Examples:
            >>> client = GameAPIClient()
            >>> result = client.refresh_display(session_id="abc123")
            >>> result["success"]
            True
            >>> "room" in result["data"]
            True
            >>> "chat" in result["data"]
            True
        """
        # Validate session
        session_state = {"logged_in": bool(session_id)}
        is_valid, error = validate_session_state(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": {"room": "Not logged in.", "chat": ""},
                "error": error,
            }

        # Get room info
        room_result = self.send_command("look", session_id)
        room_info = room_result["message"] if room_result["success"] else "Failed to load room."

        # Get chat info
        chat_result = self.get_chat(session_id)
        chat_info = chat_result["message"] if chat_result["success"] else ""

        return {
            "success": True,
            "message": "",  # Not used
            "data": {
                "room": room_info,
                "chat": chat_info,
            },
            "error": None,
        }
