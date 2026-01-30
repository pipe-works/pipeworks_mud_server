"""
Authentication API client for MUD Server.

This module handles all authentication-related API operations:
- User login with password authentication
- New user registration
- User logout and session cleanup

All functions follow a consistent pattern:
    - Validate input using validators module
    - Make API request using BaseAPIClient
    - Return standardized response dictionaries

Response Format:
    All functions return dictionaries with:
    {
        "success": bool,         # Whether operation succeeded
        "message": str,          # User-facing message
        "data": dict | None,     # Additional data (session_id, role, etc.)
        "error": str | None,     # Error details if failed
    }
"""

from mud_server.admin_gradio.api.base import BaseAPIClient
from mud_server.admin_gradio.ui.validators import (
    validate_password,
    validate_password_confirmation,
    validate_username,
)


class AuthAPIClient(BaseAPIClient):
    """
    API client for authentication operations.

    This client handles login, registration, and logout operations,
    providing clean separation between API logic and UI concerns.

    Example:
        >>> client = AuthAPIClient()
        >>> result = client.login("alice", "password123")
        >>> if result["success"]:
        ...     print(f"Logged in: {result['data']['session_id']}")
    """

    def login(self, username: str, password: str) -> dict:
        """
        Authenticate user and create session.

        Validates credentials, sends login request to backend, and returns
        session data on success.

        Args:
            username: Username to login with
            password: Plain text password

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,
                "data": {
                    "session_id": str,
                    "username": str,
                    "role": str,
                } | None,
                "error": str | None,
            }

        Examples:
            >>> client = AuthAPIClient()
            >>> result = client.login("alice", "password123")
            >>> result["success"]
            True
            >>> result["data"]["role"]
            'player'
        """
        # Validate username
        is_valid, error = validate_username(username)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate password
        is_valid, error = validate_password(password)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request
        response = self.post(
            "/login",
            json={"username": username.strip(), "password": password},
        )

        if response["success"]:
            # Extract login data from response
            data = response["data"]
            return {
                "success": True,
                "message": data["message"],
                "data": {
                    "session_id": data["session_id"],
                    "username": username.strip(),
                    "role": data.get("role", "player"),
                },
                "error": None,
            }
        else:
            # Return error
            return {
                "success": False,
                "message": f"Login failed: {response['error']}",
                "data": None,
                "error": response["error"],
            }

    def register(
        self,
        username: str,
        password: str,
        password_confirm: str,
    ) -> dict:
        """
        Register a new user account.

        Validates input, sends registration request to backend API, and returns
        status message indicating success or failure.

        Args:
            username: Desired username for new account
            password: Plain text password for new account
            password_confirm: Password confirmation (must match password)

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = AuthAPIClient()
            >>> result = client.register("bob", "password123", "password123")
            >>> result["success"]
            True
            >>> "You can now login" in result["message"]
            True
        """
        # Validate username
        is_valid, error = validate_username(username)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate password length
        is_valid, error = validate_password(password)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate password confirmation
        is_valid, error = validate_password_confirmation(password, password_confirm)
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request
        response = self.post(
            "/register",
            json={
                "username": username.strip(),
                "password": password,
                "password_confirm": password_confirm,
            },
        )

        if response["success"]:
            data = response["data"]
            # Add success indicator and instructions
            message = f"✅ {data['message']}\n\nYou can now login with your credentials."
            return {
                "success": True,
                "message": message,
                "data": None,
                "error": None,
            }
        else:
            return {
                "success": False,
                "message": f"Registration failed: {response['error']}",
                "data": None,
                "error": response["error"],
            }

    def logout(self, session_id: str | None) -> dict:
        """
        Logout user and clean up session.

        Sends logout request to backend API and returns confirmation.

        Args:
            session_id: Session ID to logout (can be None if not logged in)

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = AuthAPIClient()
            >>> result = client.logout("abc123")
            >>> result["success"]
            True
            >>> result["message"]
            'You have been logged out.'
        """
        # If no session ID, user wasn't logged in
        if not session_id:
            return {
                "success": False,
                "message": "Not logged in.",
                "data": None,
                "error": "No active session",
            }

        # Make API request (ignore response, just try to clean up)
        # Note: We don't check the response because we want to clear
        # the client-side session regardless of server response
        try:
            self.post(
                "/logout",
                json={"session_id": session_id, "command": "logout"},
            )
        except Exception:
            # Ignore errors - we'll clear session anyway
            pass

        return {
            "success": True,
            "message": "You have been logged out.",
            "data": None,
            "error": None,
        }
