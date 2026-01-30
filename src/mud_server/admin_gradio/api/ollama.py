"""
Ollama API client for MUD Server.

This module handles all Ollama LLM-related operations:
- Executing Ollama commands on specified servers
- Clearing conversation context

All functions require admin or superuser role and follow a consistent pattern:
    - Validate session state and admin permissions
    - Validate input
    - Make API request using BaseAPIClient with extended timeout
    - Return standardized response dictionaries

Response Format:
    All functions return dictionaries with:
    {
        "success": bool,         # Whether operation succeeded
        "message": str,          # Command output or status message
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


class OllamaAPIClient(BaseAPIClient):
    """
    API client for Ollama LLM operations.

    This client handles Ollama command execution and context management
    for admin and superuser roles.

    Example:
        >>> client = OllamaAPIClient()
        >>> result = client.execute_command(
        ...     session_id="admin123",
        ...     role="admin",
        ...     server_url="http://localhost:11434",
        ...     command="list"
        ... )
        >>> if result["success"]:
        ...     print(result["message"])
    """

    def execute_command(
        self,
        session_id: str | None,
        role: str,
        server_url: str,
        command: str,
    ) -> dict:
        """
        Execute an Ollama command on the specified server (Admin/Superuser only).

        Supported commands:
        - list: List available models
        - ps: Show running models
        - pull <model>: Download a model
        - rm <model>: Remove a model
        - And other Ollama CLI commands

        Args:
            session_id: User's session ID from login
            role: User's role (for permission checking)
            server_url: URL of the Ollama server
            command: Ollama command to execute

        Returns:
            Dictionary with structure:
            {
                "success": bool,
                "message": str,          # Command output
                "data": None,
                "error": str | None,
            }

        Examples:
            >>> client = OllamaAPIClient()
            >>> result = client.execute_command(
            ...     session_id="admin123",
            ...     role="admin",
            ...     server_url="http://localhost:11434",
            ...     command="list"
            ... )
            >>> result["success"]
            True

        Note:
            Long-running operations like 'pull' use a 5-minute timeout.
            If the request times out, the operation may still be running
            on the server. Use 'ps' to check status.
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

        # Validate server URL
        is_valid, error = validate_required_field(server_url, "server URL")
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Validate command
        is_valid, error = validate_required_field(command, "command")
        if not is_valid:
            return {
                "success": False,
                "message": error,
                "data": None,
                "error": error,
            }

        # Make API request with extended timeout for long operations like 'pull'
        response = self.post(
            "/admin/ollama/command",
            json={
                "session_id": session_id,
                "server_url": server_url.strip(),
                "command": command.strip(),
            },
            timeout=300,  # 5 minute timeout
        )

        if response["success"]:
            # Extract command output
            data = response["data"]
            output = data.get("output", "No output returned")
            return {
                "success": True,
                "message": str(output),
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
        elif response["status_code"] == 0 and "timed out" in response["error"]:
            # Timeout - operation may still be running
            return {
                "success": False,
                "message": "Request timed out. Long operations like 'pull' may still be running. Check 'ps' to verify.",
                "data": None,
                "error": "Timeout",
            }
        else:
            return {
                "success": False,
                "message": f"Error: {response['error']}",
                "data": None,
                "error": response["error"],
            }

    def clear_context(
        self,
        session_id: str | None,
        role: str,
    ) -> dict:
        """
        Clear Ollama conversation context for the current session (Admin/Superuser only).

        This resets the conversation history, allowing you to start fresh without
        previous context affecting new queries.

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
            >>> client = OllamaAPIClient()
            >>> result = client.clear_context(session_id="admin123", role="admin")
            >>> result["success"]
            True
            >>> "Context cleared" in result["message"]
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
        response = self.post(
            "/admin/ollama/clear-context",
            json={"session_id": session_id},
            timeout=10,
        )

        if response["success"]:
            data = response["data"]
            message = data.get("message", "Context cleared.")
            return {
                "success": True,
                "message": str(message),
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
