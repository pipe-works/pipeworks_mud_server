"""PipeWorks MUD Server — The Undertaking.

A procedural, ledger-driven MUD server for interactive fiction where characters
are issued (not built), failure is recorded as data, and optimisation is
resisted.

Version Management
------------------
``__version__`` is read from the installed package metadata at import time.
The single source of truth is the ``version`` field in ``pyproject.toml``,
which release-please bumps automatically on each release.  No manual edits
are needed anywhere else — ``server.py`` and ``health.py`` import
``__version__`` from here.
"""

from __future__ import annotations

import importlib.metadata

# Keep fallback separate from `__version__ = "..."` assignment patterns so
# release automation cannot accidentally rewrite this stable dev marker.
_DEV_FALLBACK_VERSION = "0.0.0-dev"

# ---------------------------------------------------------------------------
# Package version — read from pyproject.toml via importlib.metadata.
#
# When the package is installed (``pip install -e .``), importlib.metadata
# resolves the version from the distribution metadata that pip wrote.  If
# the package is somehow imported without being installed (rare, but
# possible during early bootstrapping), we fall back to `_DEV_FALLBACK_VERSION` so
# the application can still start.
# ---------------------------------------------------------------------------
try:
    __version__: str = importlib.metadata.version("mud_server")
except importlib.metadata.PackageNotFoundError:
    __version__ = _DEV_FALLBACK_VERSION
