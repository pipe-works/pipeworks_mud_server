"""
Admin API client for MUD Server.

This module handles all administrative operations:
- Database viewing (players, sessions, chat messages)
- User management (role changes, ban/unban)

All functions require admin or superuser role and follow a consistent pattern:
    - Validate session state and admin permissions
    - Validate input
    - Make API request using BaseAPIClient
    - Return standardized response dictionaries

Response Format:
    All functions return dictionaries with:
    {
        "success": bool,         # Whether operation succeeded
        "message": str,          # User-facing message or formatted data
        "data": None,
        "error": str | None,     # Error details if failed
    }
"""

from mud_server.admin_gradio.api.base import BaseAPIClient
from mud_server.admin_gradio.ui.validators import (
    validate_admin_role,
    validate_required_field,
    validate_session_state,
)


class AdminAPIClient(BaseAPIClient):
    """
    API client for administrative operations.

    This client handles database viewing and user management operations
    that require admin or superuser permissions.

    Example:
        >>> client = AdminAPIClient()
        >>> result = client.get_database_players(
        ...     session_id="admin123",
        ...     role="admin"
        ... )
        >>> if result["success"]:
        ...     print(result["message"])
    """

    def get_database_players(
        self,
        session_id: str | None,
        role: str,
    ) -> dict:
        """
        Fetch and format all users from database (Admin/Superuser only).

        Returns detailed information about all accounts including:
        - ID, username, role, status
        - Character count and guest flags
        - Created date and last login
        - Password hash prefix

        Args:
            session_id: User's session ID from login
            role: User's role (for permission checking)

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,          # Formatted player table
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = AdminAPIClient()
            >>> result = client.get_database_players("admin123", "admin")
            >>> result["success"]
            True
            >>> "PLAYERS TABLE" in result["message"]
            True
        """
        # Validate session
        session_state = {"logged_in": bool(session_id), "role": role}
        is_valid, error = validate_session_state(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate admin role
        is_valid, error = validate_admin_role(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request
        response = self.get(
            "/admin/database/players",
            params={"session_id": session_id},
        )

        if response["success"]:
            data = response["data"]
            players = data["players"]

            if not players:
                return {
                    "success": True,
                    "message": "No players found in database.",
                    "data": None,
                    "error": None,
                }

            # Format as text table
            output = [f"=== USERS TABLE ({len(players)} records) ===\n"]
            for player in players:
                status = "ACTIVE" if player["is_active"] else "BANNED"
                output.append(f"ID: {player['id']}")
                output.append(f"  Username: {player['username']}")
                output.append(f"  Role: {player['role']}")
                if "account_origin" in player:
                    output.append(f"  Origin: {player['account_origin']}")
                output.append(f"  Guest: {'Yes' if player.get('is_guest') else 'No'}")
                output.append(f"  Guest Expires: {player.get('guest_expires_at')}")
                output.append(f"  Characters: {player.get('character_count')}")
                output.append(f"  Status: {status}")
                output.append(f"  Created: {player['created_at']}")
                output.append(f"  Last Login: {player['last_login']}")
                output.append(f"  Password Hash: {player['password_hash']}")
                output.append("")

            return {
                "success": True,
                "message": "\n".join(output),
                "data": None,
                "error": None,
            }
        elif response["status_code"] == 403:
            return {
                "success": False,
                "message": "Access Denied: Insufficient permissions.",
                "data": None,
                "error": "Insufficient permissions",
            }
        else:
            return {
                "success": False,
                "message": f"Error: {response['error']}",
                "data": None,
                "error": response["error"],
            }

    def get_database_sessions(
        self,
        session_id: str | None,
        role: str,
    ) -> dict:
        """
        Fetch and format all active sessions from database (Admin/Superuser only).

        Returns information about all active sessions including:
        - Session ID and username
        - Connection time and last activity

        Args:
            session_id: User's session ID from login
            role: User's role (for permission checking)

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,          # Formatted sessions table
                "data": None,
                "error": str | None,
            }
        """
        # Validate session
        session_state = {"logged_in": bool(session_id), "role": role}
        is_valid, error = validate_session_state(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate admin role
        is_valid, error = validate_admin_role(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request
        response = self.get(
            "/admin/database/sessions",
            params={"session_id": session_id},
        )

        if response["success"]:
            data = response["data"]
            sessions = data["sessions"]

            if not sessions:
                return {
                    "success": True,
                    "message": "No active sessions in database.",
                    "data": None,
                    "error": None,
                }

            # Format as text table
            output = [f"=== SESSIONS TABLE ({len(sessions)} records) ===\n"]
            for session in sessions:
                output.append(f"ID: {session['id']}")
                output.append(f"  Username: {session['username']}")
                output.append(f"  Character: {session.get('character_name')}")
                output.append(f"  Session ID: {session['session_id']}")
                output.append(f"  Created: {session['created_at']}")
                output.append(f"  Last Activity: {session['last_activity']}")
                output.append(f"  Expires At: {session.get('expires_at')}")
                output.append("")

            return {
                "success": True,
                "message": "\n".join(output),
                "data": None,
                "error": None,
            }
        elif response["status_code"] == 403:
            return {
                "success": False,
                "message": "Access Denied: Insufficient permissions.",
                "data": None,
                "error": "Insufficient permissions",
            }
        else:
            return {
                "success": False,
                "message": f"Error: {response['error']}",
                "data": None,
                "error": response["error"],
            }

    def get_database_chat(
        self,
        session_id: str | None,
        role: str,
        limit: int = 50,
    ) -> dict:
        """
        Fetch and format recent chat messages from database (Admin/Superuser only).

        Returns recent chat messages from all rooms including:
        - Message ID, room, timestamp
        - Username and message content

        Args:
            session_id: User's session ID from login
            role: User's role (for permission checking)
            limit: Maximum number of messages to retrieve (default: 50)

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,          # Formatted chat messages
                "data": None,
                "error": str | None,
            }
        """
        # Validate session
        session_state = {"logged_in": bool(session_id), "role": role}
        is_valid, error = validate_session_state(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate admin role
        is_valid, error = validate_admin_role(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request
        response = self.get(
            "/admin/database/chat-messages",
            params={"session_id": session_id, "limit": limit},
        )

        if response["success"]:
            data = response["data"]
            messages = data["messages"]

            if not messages:
                return {
                    "success": True,
                    "message": "No chat messages in database.",
                    "data": None,
                    "error": None,
                }

            # Format as text table
            output = [f"=== CHAT MESSAGES ({len(messages)} recent messages) ===\n"]
            for msg in messages:
                output.append(f"ID: {msg['id']} | Room: {msg['room']} | Time: {msg['timestamp']}")
                output.append(f"  [{msg['username']}]: {msg['message']}")
                output.append("")

            return {
                "success": True,
                "message": "\n".join(output),
                "data": None,
                "error": None,
            }
        elif response["status_code"] == 403:
            return {
                "success": False,
                "message": "Access Denied: Insufficient permissions.",
                "data": None,
                "error": "Insufficient permissions",
            }
        else:
            return {
                "success": False,
                "message": f"Error: {response['error']}",
                "data": None,
                "error": response["error"],
            }

    def manage_user(
        self,
        session_id: str | None,
        role: str,
        target_username: str,
        action: str,
        new_role: str = "",
    ) -> dict:
        """
        Perform user management actions (Admin/Superuser only).

        Supported actions:
        - change_role: Change user's role (requires new_role parameter)
        - ban: Ban/deactivate user account
        - unban: Unban/reactivate user account

        Args:
            session_id: User's session ID from login
            role: User's role (for permission checking)
            target_username: Username of user to manage
            action: Action to perform (change_role, ban, unban)
            new_role: New role for change_role action (optional)

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = AdminAPIClient()
            >>> result = client.manage_user(
            ...     session_id="admin123",
            ...     role="admin",
            ...     target_username="alice",
            ...     action="change_role",
            ...     new_role="worldbuilder"
            ... )
            >>> result["success"]
            True
        """
        # Validate session
        session_state = {"logged_in": bool(session_id), "role": role}
        is_valid, error = validate_session_state(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate admin role
        is_valid, error = validate_admin_role(session_state)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate target username
        is_valid, error = validate_required_field(target_username, "target username")
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate action
        is_valid, error = validate_required_field(action, "action")
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Build request data
        request_data = {
            "session_id": session_id,
            "target_username": target_username.strip(),
            "action": action,
        }

        # Validate new_role for change_role action
        if action == "change_role":
            is_valid, error = validate_required_field(new_role, "new role")
            if not is_valid:
                return {
                    "success": False,
                    "message": "New role is required for change_role action.",
                    "data": None,
                    "error": error,
                }
            request_data["new_role"] = new_role.strip().lower()

        # Make API request
        response = self.post(
            "/admin/user/manage",
            json=request_data,
        )

        if response["success"]:
            data = response["data"]
            return {
                "success": True,
                "message": f"✅ {data['message']}",
                "data": None,
                "error": None,
            }
        else:
            return {
                "success": False,
                "message": f"❌ {response['error']}",
                "data": None,
                "error": response["error"],
            }
