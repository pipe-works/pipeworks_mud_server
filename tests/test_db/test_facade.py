"""Tests for the DB facade forwarding module."""

from __future__ import annotations

from mud_server.db import facade


def test_facade_forwards_db_attributes():
    """Facade should forward exported functions from compatibility module."""
    assert callable(facade.get_connection)
    assert callable(facade.init_database)
