"""
Route registration entry point for the FastAPI application.

Keeps the public `register_routes(app, engine)` API unchanged while
splitting implementation into focused router modules.
"""

from fastapi import FastAPI

from mud_server.api.routes import admin, auth, game, health, lab, ollama, pipeline, policies, policy
from mud_server.core.engine import GameEngine


def register_routes(app: FastAPI, engine: GameEngine) -> None:
    """Register all API routes with the FastAPI app.

    Registration order is intentional:
    - baseline auth/game/admin/lab routes first for existing clients
    - pipeline routes after base modules to keep new primitives additive

    Args:
        app: FastAPI application instance to attach routers to.
        engine: Shared game engine dependency passed to route factories.
    """
    app.include_router(health.router)
    app.include_router(auth.router(engine))
    app.include_router(game.router(engine))
    app.include_router(admin.router(engine))
    app.include_router(ollama.router(engine))
    app.include_router(lab.router(engine))
    app.include_router(policy.router(engine))
    app.include_router(policies.router(engine))
    # Pipeline routes expose stateless generation primitives under /api/pipeline/*.
    app.include_router(pipeline.router(engine))
