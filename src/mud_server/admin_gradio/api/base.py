"""
Base API Client for MUD Server.

This module provides the foundational HTTP client for communicating with the
FastAPI backend server. It handles common patterns like request execution,
error handling, and response parsing.

All domain-specific API clients (auth, game, admin, ollama) inherit from
BaseAPIClient to get consistent error handling and request patterns.

Configuration:
    SERVER_URL: Backend API server URL (can be overridden with MUD_SERVER_URL env var)
"""

import os
from typing import Any

import requests


class BaseAPIClient:
    """
    Base API client providing common HTTP request patterns and error handling.

    This class handles:
    - Server URL configuration
    - Common request patterns (GET, POST)
    - Consistent error handling and formatting
    - Response parsing and validation

    Attributes:
        server_url: Backend API server URL
    """

    def __init__(self, server_url: str | None = None):
        """
        Initialize the base API client.

        Args:
            server_url: Optional server URL override. If not provided,
                       uses MUD_SERVER_URL environment variable or defaults
                       to http://localhost:8000
        """
        self.server_url = server_url or os.getenv("MUD_SERVER_URL", "http://localhost:8000")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json: dict | None = None,
        params: dict | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Make an HTTP request to the backend API.

        This method handles common error cases and returns a standardized
        response format with success flag and message/data.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., "/login", "/command")
            json: Optional JSON body for POST requests
            params: Optional query parameters for GET requests
            timeout: Request timeout in seconds (default: 30)

        Returns:
            Dictionary with structure:
                {
                    "success": bool,
                    "data": dict | None,      # Response data if successful
                    "error": str | None,      # Error message if failed
                    "status_code": int        # HTTP status code
                }

        Note:
            This method never raises exceptions. All errors are caught and
            returned in the response dictionary.
        """
        url = f"{self.server_url}{endpoint}"

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                json=json,
                params=params,
                timeout=timeout,
            )

            # Parse response JSON
            try:
                data = response.json()
            except ValueError:
                data = {}

            # Check if request was successful
            if response.status_code == 200:
                return {
                    "success": True,
                    "data": data,
                    "error": None,
                    "status_code": response.status_code,
                }
            else:
                # Extract error message from response
                error_msg = data.get("detail", f"Request failed with status {response.status_code}")
                return {
                    "success": False,
                    "data": None,
                    "error": error_msg,
                    "status_code": response.status_code,
                }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "data": None,
                "error": f"Cannot connect to server at {self.server_url}",
                "status_code": 0,
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "data": None,
                "error": f"Request timed out after {timeout} seconds",
                "status_code": 0,
            }

        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": f"Unexpected error: {str(e)}",
                "status_code": 0,
            }

    def get(
        self,
        endpoint: str,
        params: dict | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Make a GET request to the API.

        Args:
            endpoint: API endpoint path
            params: Optional query parameters
            timeout: Request timeout in seconds

        Returns:
            Standardized response dictionary (see _make_request)
        """
        return self._make_request("GET", endpoint, params=params, timeout=timeout)

    def post(
        self,
        endpoint: str,
        json: dict | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Make a POST request to the API.

        Args:
            endpoint: API endpoint path
            json: Optional JSON body
            timeout: Request timeout in seconds

        Returns:
            Standardized response dictionary (see _make_request)
        """
        return self._make_request("POST", endpoint, json=json, timeout=timeout)
