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
"""

from __future__ import annotations

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
