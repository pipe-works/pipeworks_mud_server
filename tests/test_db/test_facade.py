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
    Facade patching should not mutate canonical symbols on ``db.database``.

    Under the explicit-export model, ``mud_server.db.facade`` owns wrapper
    callables while runtime dispatch still resolves targets from
    ``mud_server.db.database``. Patching the facade symbol should therefore
    patch and restore only the facade wrapper, leaving the canonical database
    function unchanged throughout.
    """

    original = database.get_characters_in_room
    facade_original = facade.get_characters_in_room
    assert "get_characters_in_room" in facade.__dict__

    with patch("mud_server.db.facade.get_characters_in_room", return_value=[]):
        assert facade.get_characters_in_room("spawn", world_id=database.DEFAULT_WORLD_ID) == []
        assert database.get_characters_in_room is original

    assert database.get_characters_in_room is original
    assert facade.get_characters_in_room is facade_original


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


def test_facade_resolve_public_attr_rejects_removed_alias_directly():
    """
    Helper-level resolution should reject removed legacy aliases.

    This covers direct helper usage so the explicit migration message remains
    stable even when call sites invoke internal facade helpers in tests.
    """

    with pytest.raises(AttributeError, match="removed in 0.3.10"):
        facade._resolve_public_attr("player_exists")  # noqa: SLF001 - branch coverage


def test_facade_resolve_public_attr_rejects_unknown_symbol():
    """
    Helper-level resolution should reject symbols outside the public contract.

    Unknown names must fail with a normal module-style attribute error rather
    than silently delegating to the backing database module.
    """

    with pytest.raises(AttributeError, match="has no attribute"):
        facade._resolve_public_attr("not_a_real_symbol")  # noqa: SLF001 - branch coverage


def test_facade_resolve_public_attr_fails_when_public_symbol_missing(monkeypatch):
    """
    Declared public symbols should fail fast when missing in ``db.database``.

    This protects against contract drift where ``_PUBLIC_API`` names diverge
    from the canonical compatibility module exports.
    """

    monkeypatch.delattr(database, "user_exists", raising=False)
    with pytest.raises(AttributeError, match="declared public but missing"):
        facade._resolve_public_attr("user_exists")  # noqa: SLF001 - branch coverage


def test_facade_forwarder_raises_when_backing_symbol_is_not_callable(monkeypatch):
    """
    Forwarders should enforce callability of runtime-resolved DB symbols.

    If a test patch accidentally replaces a callable DB function with a
    non-callable sentinel, the facade should fail with an explicit ``TypeError``
    instead of producing a confusing ``'object is not callable'`` traceback.
    """

    monkeypatch.setattr(database, "user_exists", 1)
    forwarder = facade._build_callable_forwarder("user_exists")  # noqa: SLF001 - branch coverage
    with pytest.raises(TypeError, match="is not callable"):
        forwarder("alice")


def test_facade_getattr_unknown_symbol_raises_standard_error():
    """Unknown names should raise a standard module attribute error message."""
    with pytest.raises(AttributeError, match="has no attribute"):
        facade.__getattr__("nope")  # noqa: SLF001 - direct branch coverage


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
