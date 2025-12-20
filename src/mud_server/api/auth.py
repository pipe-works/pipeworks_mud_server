"""Session management and authentication."""

from typing import Dict, Optional
from fastapi import HTTPException
from mud_server.db import database

# Store active sessions (session_id -> username)
active_sessions: Dict[str, str] = {}


def get_username_from_session(session_id: str) -> Optional[str]:
    """Get username from session ID."""
    return active_sessions.get(session_id)


def validate_session(session_id: str) -> Optional[str]:
    """Validate session and return username."""
    username = get_username_from_session(session_id)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    database.update_session_activity(username)
    return username
