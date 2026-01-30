"""
Settings API client for MUD Server.

This module handles user settings and server management operations:
- Password changes
- Server control (stop server)

All functions follow a consistent pattern:
    - Validate session state and permissions
    - Validate input
    - Make API request using BaseAPIClient
    - Return standardized response dictionaries

Response Format:
    All functions return dictionaries with:
    {
        "success": bool,         # Whether operation succeeded
        "message": str,          # User-facing message
        "data": None,
        "error": str | None,     # Error details if failed
    }
"""

from mud_server.admin_gradio.api.base import BaseAPIClient
from mud_server.admin_gradio.ui.validators import (
    validate_admin_role,
    validate_password,
    validate_password_confirmation,
    validate_password_different,
    validate_required_field,
    validate_session_state,
)


class SettingsAPIClient(BaseAPIClient):
    """
    API client for settings and server management operations.

    This client handles password changes and server control operations.

    Example:
        >>> client = SettingsAPIClient()
        >>> result = client.change_password(
        ...     session_id="abc123",
        ...     old_password="old123",
        ...     new_password="new456",
        ...     confirm_password="new456"
        ... )
        >>> if result["success"]:
        ...     print("Password changed successfully")
    """

    def change_password(
        self,
        session_id: str | None,
        old_password: str,
        new_password: str,
        confirm_password: str,
    ) -> dict:
        """
        Change the current user's password.

        Validates passwords, sends change request to backend, and returns
        confirmation or error message.

        Args:
            session_id: User's session ID from login
            old_password: Current password (for verification)
            new_password: Desired new password
            confirm_password: New password confirmation

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = SettingsAPIClient()
            >>> result = client.change_password(
            ...     session_id="abc123",
            ...     old_password="old123",
            ...     new_password="new456789",
            ...     confirm_password="new456789"
            ... )
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

        # Validate old password is provided
        is_valid, error = validate_required_field(old_password, "current password")
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate new password meets requirements
        is_valid, error = validate_password(new_password)
        if not is_valid:
            return {
                "success": False,
                "message": "New password must be at least 8 characters.",
                "data": None,
                "error": error,
            }

        # Validate new passwords match
        is_valid, error = validate_password_confirmation(new_password, confirm_password)
        if not is_valid:
            return {
                "success": False,
                "message": "New passwords do not match.",
                "data": None,
                "error": error,
            }

        # Validate new password is different from old
        is_valid, error = validate_password_different(old_password, new_password)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request
        response = self.post(
            "/change-password",
            json={
                "session_id": session_id,
                "old_password": old_password,
                "new_password": new_password,
            },
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

    def stop_server(
        self,
        session_id: str | None,
        role: str,
    ) -> dict:
        """
        Stop the backend server (Admin/Superuser only).

        This operation requires admin or superuser permissions. The server
        will shut down gracefully after responding to this request.

        Args:
            session_id: User's session ID from login
            role: User's role (for permission checking)

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = SettingsAPIClient()
            >>> result = client.stop_server(session_id="abc123", role="admin")
            >>> if result["success"]:
            ...     print("Server shutting down")
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
        response = self.post(
            "/admin/server/stop",
            json={"session_id": session_id},
        )

        if response["success"]:
            data = response["data"]
            return {
                "success": True,
                "message": f"✅ {data['message']}",
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
            # Server might be stopped or unreachable after this call
            error_msg = response["error"]
            if "Cannot connect to server" in error_msg or response["status_code"] == 0:
                return {
                    "success": True,  # Consider this success - server stopped
                    "message": f"Server stopped or cannot connect to {self.server_url}",
                    "data": None,
                    "error": None,
                }
            return {
                "success": False,
                "message": f"❌ {error_msg}",
                "data": None,
                "error": error_msg,
            }
