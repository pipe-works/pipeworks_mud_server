"""Public DB facade module.

This module is the app-facing import surface for database operations. During
the refactor transition it re-exports the compatibility ``database`` symbols
directly so static typing remains precise while call sites migrate.
"""

from __future__ import annotations

from mud_server.db.database import *  # noqa: F401,F403
