"""Tests for the DB facade forwarding module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

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

    original = database.get_characters_in_room
    assert "get_characters_in_room" not in facade.__dict__

    with patch("mud_server.db.facade.get_characters_in_room", return_value=[]):
        assert facade.get_characters_in_room("spawn") == []

    assert database.get_characters_in_room is original
    assert "get_characters_in_room" not in facade.__dict__


def test_facade_dir_exposes_forwarded_attributes():
    """Facade ``dir()`` should include explicit public API symbols."""
    names = dir(facade)
    assert "user_exists" in names
    assert "get_characters_in_room" in names
    assert "Any" not in names


def test_facade_all_tracks_explicit_api_contract():
    """Facade ``__all__`` should include public DB symbols and exclude removed aliases."""
    assert "user_exists" in facade.__all__
    assert "get_characters_in_room" in facade.__all__
    assert "player_exists" not in facade.__all__


def test_facade_removed_alias_raises_clear_error():
    """Removed legacy aliases should raise a directed migration error."""
    with pytest.raises(AttributeError, match="removed in 0.3.10"):
        _ = facade.player_exists


def test_facade_allows_local_attribute_set_and_delete_for_unknown_names():
    """Unknown names should be stored and removed on facade-local module state."""
    local_name = "_facade_local_attr_for_test"

    setattr(facade, local_name, 42)
    assert getattr(facade, local_name) == 42
    assert local_name in facade.__dict__
    assert not hasattr(database, local_name)

    delattr(facade, local_name)
    assert local_name not in facade.__dict__


def test_facade_internal_dunder_attribute_set_and_delete():
    """Dunder attributes should use the module's local setattr/delattr path."""
    dunder_name = "__facade_dunder_attr_for_test__"

    setattr(facade, dunder_name, "ok")
    assert facade.__dict__[dunder_name] == "ok"

    delattr(facade, dunder_name)
    assert dunder_name not in facade.__dict__
