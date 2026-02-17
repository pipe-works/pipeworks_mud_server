"""Tests for the DB facade forwarding module."""

from __future__ import annotations

from unittest.mock import patch

from mud_server.db import database, facade


def test_facade_forwards_db_attributes():
    """Facade should forward exported functions from compatibility module."""
    assert callable(facade.get_connection)
    assert callable(facade.init_database)


def test_facade_reflects_runtime_monkeypatches(monkeypatch):
    """
    Facade lookups should resolve the current database attribute at call time.

    This protects API/core modules that import ``mud_server.db.facade`` while
    tests monkeypatch symbols on ``mud_server.db.database``. If facade were to
    bind function objects eagerly, these monkeypatches would stop intercepting
    and many error-path tests would silently lose coverage.
    """

    def _always_true(_username: str) -> bool:
        return True

    monkeypatch.setattr(database, "user_exists", _always_true)
    assert facade.user_exists("any-user") is True


def test_facade_patch_teardown_restores_database_attribute():
    """
    Proxy patching should restore symbols back onto ``db.database``.

    ``unittest.mock.patch`` teardown performs ``delattr`` then ``setattr`` when
    patching proxy objects. The facade module must keep this cycle routed to
    ``mud_server.db.database`` so DB API symbols are never dropped from the
    canonical module after test teardown.
    """

    original = database.get_players_in_room
    assert "get_players_in_room" not in facade.__dict__

    with patch("mud_server.db.facade.get_players_in_room", return_value=[]):
        assert facade.get_players_in_room("spawn") == []

    assert database.get_players_in_room is original
    assert "get_players_in_room" not in facade.__dict__
