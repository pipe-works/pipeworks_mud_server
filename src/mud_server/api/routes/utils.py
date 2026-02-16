"""Shared helpers for API route modules."""

from typing import Any

from mud_server.core.engine import GameEngine
from mud_server.db import database


def get_available_worlds(user_id: int, role: str) -> list[dict[str, Any]]:
    """
    Return world options for account dashboards and world selectors.

    Non-admin users receive invite-only worlds as preview rows so the account
    dashboard can label them as locked/invite without granting access.
    """
    return database.list_worlds_for_user(user_id, role=role, include_invite_worlds=True)


def resolve_zone_id(engine: GameEngine, room_id: str | None, world_id: str | None) -> str | None:
    """
    Resolve a room_id to its zone id using the loaded world data.

    Returns None if the room cannot be mapped to a zone.
    """
    if not room_id or not world_id:
        return None
    try:
        world = engine.world_registry.get_world(world_id)
    except ValueError:
        return None
    for zone_id, zone in world.zones.items():
        if room_id in zone.rooms:
            return zone_id
    return None
