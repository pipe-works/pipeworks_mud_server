"""Tests for the DB facade forwarding module."""

from __future__ import annotations

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
