"""Health and root endpoints."""

from fastapi import APIRouter

from mud_server.api.auth import get_active_session_count

router = APIRouter()


@router.get("/")
async def root():
    """Root endpoint showing API info."""
    return {"message": "MUD Server API", "version": "0.3.2"}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "active_players": get_active_session_count()}
