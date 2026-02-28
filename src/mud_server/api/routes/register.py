"""
Route registration entry point for the FastAPI application.

Keeps the public `register_routes(app, engine)` API unchanged while
splitting implementation into focused router modules.
"""

from fastapi import FastAPI

from mud_server.api.routes import admin, auth, game, health, lab, ollama
from mud_server.core.engine import GameEngine


def register_routes(app: FastAPI, engine: GameEngine) -> None:
    """Register all API routes with the FastAPI app."""
    app.include_router(health.router)
    app.include_router(auth.router(engine))
    app.include_router(game.router(engine))
    app.include_router(admin.router(engine))
    app.include_router(ollama.router(engine))
    app.include_router(lab.router(engine))
