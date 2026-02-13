"""Tests for shared API route helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mud_server.api.routes.utils import resolve_zone_id


@pytest.mark.api
def test_resolve_zone_id_returns_none_without_room_or_world(mock_engine):
    """resolve_zone_id should return None when inputs are missing."""
    assert resolve_zone_id(mock_engine, None, "pipeworks_web") is None
    assert resolve_zone_id(mock_engine, "spawn", None) is None


@pytest.mark.api
def test_resolve_zone_id_handles_unknown_world(mock_engine):
    """resolve_zone_id should return None when the world registry rejects the id."""

    def raise_world(_world_id: str):
        raise ValueError("unknown world")

    mock_engine.world_registry = SimpleNamespace(get_world=raise_world)
    assert resolve_zone_id(mock_engine, "spawn", "missing_world") is None


@pytest.mark.api
def test_resolve_zone_id_returns_zone_for_room(mock_engine):
    """resolve_zone_id should map a room id to its containing zone."""
    zone_id = resolve_zone_id(mock_engine, "spawn", "pipeworks_web")
    assert zone_id == "test_zone"
