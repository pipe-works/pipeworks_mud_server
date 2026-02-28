"""Tests for dynamic version management.

Verifies that ``mud_server.__version__`` is correctly resolved from the
installed package metadata (``pyproject.toml``) and that every place the
version is surfaced — the package attribute, the FastAPI OpenAPI schema,
and the root ``/`` endpoint — all agree.

The version string is the single source of truth managed by release-please
in ``pyproject.toml``.  These tests ensure nothing drifts.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

import mud_server

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Matches semver-ish strings: major.minor.patch with optional pre-release
# suffix (e.g. "0.4.2", "1.0.0-rc.1", "0.0.0-dev").
_SEMVER_RE = re.compile(
    r"^\d+\.\d+\.\d+"  # major.minor.patch
    r"(-[A-Za-z0-9]+(\.[A-Za-z0-9]+)*)?$"  # optional pre-release
)


# ---------------------------------------------------------------------------
# Unit tests — no server or HTTP required
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVersionAttribute:
    """Verify the ``mud_server.__version__`` package attribute."""

    def test_version_is_a_string(self) -> None:
        """__version__ must be a non-empty string."""
        assert isinstance(mud_server.__version__, str)
        assert len(mud_server.__version__) > 0

    def test_version_matches_semver(self) -> None:
        """__version__ must look like a valid semantic version."""
        assert _SEMVER_RE.match(mud_server.__version__), (
            f"__version__ {mud_server.__version__!r} does not match "
            f"expected semver pattern (major.minor.patch[-prerelease])"
        )

    def test_version_is_not_fallback(self) -> None:
        """__version__ should not be the dev fallback in a normal install.

        The fallback ``0.0.0-dev`` only appears when the package is imported
        without being installed.  In a test environment (where ``pip install
        -e .`` has been run) we expect the real version from pyproject.toml.
        """
        assert (
            mud_server.__version__ != "0.0.0-dev"
        ), "__version__ is the fallback value — is the package installed?"


# ---------------------------------------------------------------------------
# Integration tests — require the FastAPI app
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVersionInApp:
    """Verify version consistency across the FastAPI app surfaces."""

    def test_openapi_version_matches_package(self) -> None:
        """The OpenAPI schema version must match __version__.

        The FastAPI ``app`` is constructed with ``version=__version__`` in
        ``server.py``.  This test confirms the wiring is correct.
        """
        from mud_server.api.server import app

        assert app.version == mud_server.__version__, (
            f"FastAPI app.version ({app.version!r}) does not match "
            f"mud_server.__version__ ({mud_server.__version__!r})"
        )

    def test_root_endpoint_version_matches_package(self) -> None:
        """The root ``/`` endpoint must report the same version.

        Uses the HTTPX test client to hit the root endpoint and checks the
        ``version`` field in the JSON response body.
        """
        import asyncio

        from httpx import ASGITransport, AsyncClient

        from mud_server.api.server import app

        async def _fetch_root() -> dict[str, Any]:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/")
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result

        data = asyncio.run(_fetch_root())
        assert data["version"] == mud_server.__version__, (
            f"Root endpoint version ({data['version']!r}) does not match "
            f"mud_server.__version__ ({mud_server.__version__!r})"
        )
