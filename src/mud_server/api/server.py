"""
FastAPI backend server for the MUD.

This module initializes and configures the FastAPI application that serves as
the backend API for the Multi-User Dungeon (MUD) game. It sets up:
- CORS middleware for cross-origin requests from the Gradio frontend
- The game engine instance that handles all game logic
- All API route endpoints for player actions and admin functions

The server runs on port 8000 by default and accepts connections from any host
to allow network access from other machines.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mud_server.api.routes import register_routes
from mud_server.core.engine import GameEngine

# ============================================================================
# APPLICATION INITIALIZATION
# ============================================================================

# Initialize the FastAPI application with metadata
# This creates the main app instance that will handle all HTTP requests
app = FastAPI(title="MUD Server", version="0.1.0")

# ============================================================================
# MIDDLEWARE CONFIGURATION
# ============================================================================

# Add CORS (Cross-Origin Resource Sharing) middleware
# This allows the Gradio frontend (running on a different port) to make
# requests to this API server. In production, you should restrict
# allow_origins to specific domains instead of using "*" (all origins).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow requests from any origin (frontend can be on different port/host)
    allow_credentials=True,  # Allow cookies and authentication headers
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers in requests
)

# ============================================================================
# GAME ENGINE INITIALIZATION
# ============================================================================

# Create the game engine instance
# This is a singleton that manages all game state, including:
# - World data (rooms, items, exits)
# - Player actions (movement, inventory, chat)
# - Database connections for persistence
# The engine is passed to all route handlers that need game logic
engine = GameEngine()

# ============================================================================
# ROUTE REGISTRATION
# ============================================================================

# Register all API endpoints with the FastAPI app
# This includes routes for:
# - Authentication (login, register, logout)
# - Game commands (move, look, inventory, chat, whisper, yell)
# - Player management (change password)
# - Admin functions (user management, view logs, stop server)
register_routes(app, engine)

# ============================================================================
# SERVER STARTUP
# ============================================================================

if __name__ == "__main__":
    # Only runs when this file is executed directly (not when imported)
    import uvicorn

    # Get server configuration from environment variables with sensible defaults
    # MUD_HOST: Network interface to bind to (0.0.0.0 = all interfaces, allows remote connections)
    # MUD_PORT: Port number to listen on (default 8000)
    host = os.getenv("MUD_HOST", "0.0.0.0")
    port = int(os.getenv("MUD_PORT", 8000))

    # Start the uvicorn ASGI server
    # This runs the FastAPI app and handles all HTTP requests
    uvicorn.run(app, host=host, port=port)
