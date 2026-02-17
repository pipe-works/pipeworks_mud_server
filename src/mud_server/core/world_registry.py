"""
World registry and loader for multi-world support.

The registry is responsible for:
- Listing available worlds from the database catalog
- Filtering worlds by user permissions
- Loading world packages from disk on demand
- Caching World instances for reuse
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mud_server.config import config
from mud_server.core.world import World
from mud_server.db import facade as database


class WorldRegistry:
    """
    World registry with lazy-loading and permission filtering.

    This class centralizes access to worlds and avoids repeated disk loads
    by caching World instances in memory.
    """

    def __init__(self, *, worlds_root: str | Path | None = None) -> None:
        self._worlds_root = Path(worlds_root or config.worlds.worlds_root)
        self._cache: dict[str, World] = {}

    def list_worlds(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        """Return all worlds in the catalog."""
        return database.list_worlds(include_inactive=include_inactive)

    def list_worlds_for_user(
        self, user_id: int, *, role: str | None = None, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        """Return worlds accessible to the given user."""
        return database.list_worlds_for_user(user_id, role=role, include_inactive=include_inactive)

    def get_world(self, world_id: str) -> World:
        """
        Load and return the World for the given world_id.

        Raises:
            ValueError: If the world does not exist or is inactive.
        """
        if world_id in self._cache:
            return self._cache[world_id]

        world_row = database.get_world_by_id(world_id)
        if not world_row:
            raise ValueError(f"Unknown world_id: {world_id}")
        if not world_row.get("is_active", False):
            raise ValueError(f"World is inactive: {world_id}")

        world_path = self._worlds_root / world_id
        world = World(world_root=world_path)
        self._cache[world_id] = world
        return world

    def clear_cache(self) -> None:
        """Clear cached world instances (used for tests or hot reloads)."""
        self._cache.clear()
