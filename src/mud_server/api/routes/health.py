"""Health and root endpoints.

Provides the root ``/`` endpoint (API identity and version) and the
``/health`` endpoint (liveness check with active session count).

The version string is read from ``mud_server.__version__`` which is
resolved at import time via ``importlib.metadata`` — the single source
of truth is ``pyproject.toml``, bumped automatically by release-please.
"""

from fastapi import APIRouter

from mud_server import __version__
from mud_server.api.auth import get_active_session_count

router = APIRouter()


@router.get("/")
async def root():
    """Root endpoint showing API identity and current version.

    Returns a JSON object with the API name and the version read from
    the installed package metadata (``pyproject.toml``).
    """
    return {"message": "MUD Server API", "version": __version__}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "active_players": get_active_session_count()}
