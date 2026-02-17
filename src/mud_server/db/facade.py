"""Public DB facade module.

This module is the app-facing import surface for database operations.

Design goals:
1. Keep application layers importing a stable module path (``mud_server.db.facade``).
2. Preserve existing test monkeypatch behavior that targets
   ``mud_server.db.database.<symbol>``.
3. Avoid duplicating function wrappers while the refactor still routes through
   the compatibility ``database`` module.

Implementation notes:
- Attribute access is forwarded dynamically via ``__getattr__``.
- Because lookup is dynamic, monkeypatches applied to
  ``mud_server.db.database`` are visible to callers that imported this module
  as ``facade``.
- Attribute writes/deletes are forwarded to ``mud_server.db.database`` via a
  custom module type. This prevents test monkeypatch operations from leaving
  stale shadow attributes on the facade module itself.
"""

from __future__ import annotations

import sys
import types
from typing import TYPE_CHECKING, Any

from mud_server.db import database as _database

if TYPE_CHECKING:
    # Type-checking view: expose database module symbols with precise types.
    # Runtime forwarding still happens via __getattr__ below.
    from mud_server.db.database import *  # noqa: F401,F403


def __getattr__(name: str) -> Any:
    """
    Forward unresolved attribute lookups to ``mud_server.db.database``.

    This allows call sites to import ``mud_server.db.facade`` while tests can
    still patch symbols on ``mud_server.db.database`` and have those patches
    observed at call time.
    """
    return getattr(_database, name)


def __dir__() -> list[str]:
    """
    Return combined attribute names for introspection tools and shells.

    This keeps interactive discovery (``dir(facade)``) aligned with the
    forwarded database module contents.
    """
    return sorted(set(globals()) | set(dir(_database)))


__all__ = [name for name in dir(_database) if not name.startswith("_")]


class _FacadeModule(types.ModuleType):
    """
    Module type that forwards public attribute writes to ``db.database``.

    Why this exists:
        ``pytest`` monkeypatch/patch utilities sometimes target attributes on
        imported module objects (for example ``auth.database``). If those writes
        land on the facade module, they can shadow ``__getattr__`` forwarding
        and leak stale function objects between tests. Forwarding writes/deletes
        to the backing ``db.database`` module keeps behavior consistent.
    """

    _INTERNAL_ATTRS = {
        "_database",
        "_FacadeModule",
        "__all__",
        "__getattr__",
        "__dir__",
        "_FORWARDED_ATTRS",
    }
    _FORWARDED_ATTRS = set(__all__)

    def __setattr__(self, name: str, value: Any) -> None:
        """Forward public attribute writes to the backing database module."""
        if name.startswith("__") or name in self._INTERNAL_ATTRS:
            super().__setattr__(name, value)
            return
        # Forward known DB API symbols even if they were temporarily deleted by
        # patch teardown flows. This prevents accidental local shadow attributes.
        if name in self._FORWARDED_ATTRS or hasattr(_database, name):
            setattr(_database, name, value)
            return
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        """Forward public attribute deletes to the backing database module."""
        if name.startswith("__") or name in self._INTERNAL_ATTRS:
            super().__delattr__(name)
            return
        if name in self._FORWARDED_ATTRS or hasattr(_database, name):
            # ``unittest.mock.patch`` for proxy modules performs delete-then-set
            # on exit. Deleting on the backing module is required so the
            # subsequent restore set writes through to ``db.database``.
            if hasattr(_database, name):
                delattr(_database, name)
            return
        super().__delattr__(name)


# Replace module runtime behavior so patch/monkeypatch writes flow through.
sys.modules[__name__].__class__ = _FacadeModule
