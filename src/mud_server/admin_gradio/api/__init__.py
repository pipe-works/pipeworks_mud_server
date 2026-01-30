"""
API client modules for MUD server communication.

This package provides domain-specific API clients for communicating with
the FastAPI backend server. All clients inherit from BaseAPIClient for
consistent error handling and request patterns.

Modules:
    base: Base API client with common HTTP request patterns
    auth: Authentication operations (login, register, logout)
    game: Game operations (commands, chat, status)
    admin: Administrative operations (database, user management)
    ollama: Ollama LLM operations (command execution, context)
"""

from mud_server.admin_gradio.api.base import BaseAPIClient

__all__ = ["BaseAPIClient"]
