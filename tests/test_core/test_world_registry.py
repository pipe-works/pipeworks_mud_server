"""Tests for the WorldRegistry loader and permission filtering."""

import json

import pytest

from mud_server.core.world_registry import WorldRegistry
from mud_server.db import database


@pytest.mark.unit
@pytest.mark.db
def test_world_registry_get_world_loads_from_disk(test_db, tmp_path):
    """WorldRegistry should load a world package from disk when requested."""
    world_id = "pipeworks_web"
    world_root = tmp_path / world_id
    zones_dir = world_root / "zones"
    zones_dir.mkdir(parents=True)

    (world_root / "world.json").write_text(
        json.dumps({"name": "Pipeworks Web", "default_spawn": {"room": "spawn"}, "zones": []})
    )

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
        VALUES (?, ?, '', 1, '{}')
        """,
        (world_id, world_id),
    )
    conn.commit()
    conn.close()

    registry = WorldRegistry(worlds_root=tmp_path)
    world = registry.get_world(world_id)

    assert world.world_name == "Pipeworks Web"


@pytest.mark.unit
@pytest.mark.db
def test_world_registry_rejects_inactive_world(test_db, tmp_path):
    """WorldRegistry should reject inactive worlds."""
    world_id = "inactive_world"
    world_root = tmp_path / world_id
    (world_root / "zones").mkdir(parents=True)
    (world_root / "world.json").write_text(
        json.dumps({"name": "Inactive", "default_spawn": {"room": "spawn"}, "zones": []})
    )

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO worlds (id, name, description, is_active, config_json)
        VALUES (?, ?, '', 0, '{}')
        """,
        (world_id, world_id),
    )
    conn.commit()
    conn.close()

    registry = WorldRegistry(worlds_root=tmp_path)
    with pytest.raises(ValueError):
        registry.get_world(world_id)
