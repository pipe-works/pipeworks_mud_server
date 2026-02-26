"""
WebUI routes for serving the admin dashboard shell, play shell, and static assets.

This module intentionally keeps server-side logic minimal:
- Serves a single HTML shell for `/admin` and `/admin/*`.
- Serves a single HTML shell for `/play` and `/play/<world_id>/*`.
- Delegates all application behavior to client-side JS.
- Uses FastAPI's StaticFiles to serve CSS/JS assets.

No authentication logic lives here; the client authenticates against
existing API endpoints and enforces role checks. Server-side role checks
remain in the API layer.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Resolve paths relative to this file for predictable packaging.
_WEB_ROOT = Path(__file__).resolve().parent
_TEMPLATES_DIR = _WEB_ROOT / "templates"
_STATIC_DIR = _WEB_ROOT / "static"
# Static asset version token for admin shell cache busting.
# Bump this when frontend assets change and deployments should force refresh.
ADMIN_ASSET_VERSION = "20260220b"
# Static asset version token for play shell cache busting.
# Keep separate from admin so play-shell rollouts can be versioned independently.
PLAY_ASSET_VERSION = "20260226a"


templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def build_admin_router() -> APIRouter:
    """
    Build the admin WebUI router for serving the HTML shell.

    Returns:
        APIRouter configured to serve the admin dashboard shell.
    """
    router = APIRouter()

    def _render_admin_shell(request: Request) -> HTMLResponse:
        """Render the admin shell with static asset version metadata."""
        return templates.TemplateResponse(
            request,
            "admin_shell.html",
            {
                "asset_version": ADMIN_ASSET_VERSION,
            },
        )

    @router.get("/admin", response_class=HTMLResponse)
    async def admin_root(request: Request):
        """
        Serve the WebUI shell for the admin dashboard.

        Client-side routing handles the actual view selection.
        """
        return _render_admin_shell(request)

    @router.get("/admin/{path:path}", response_class=HTMLResponse)
    async def admin_shell(request: Request, path: str):
        """
        Serve the same WebUI shell for all admin routes.

        This supports client-side routing without server-side awareness of
        specific subpaths.
        """
        _ = path  # Path is unused but retained for routing.
        return _render_admin_shell(request)

    return router


def _render_play_shell(request: Request, world_id: str | None) -> HTMLResponse:
    """
    Render the play UI shell with optional world context.

    Args:
        request: The inbound FastAPI request (required by Jinja2 templates).
        world_id: Optional world id extracted from the route.

    Returns:
        HTMLResponse containing the play shell.
    """
    return templates.TemplateResponse(
        request,
        "play_shell.html",
        {
            # Empty string keeps template logic simple when no world is selected.
            "world_id": world_id or "",
            "asset_version": PLAY_ASSET_VERSION,
        },
    )


def build_play_router() -> APIRouter:
    """
    Build the play WebUI router for serving the play shell.

    The play UI is a single-page shell. Client-side routing handles
    specific subpaths like /play/<world_id>/rooms/...
    """
    router = APIRouter()

    @router.get("/play", response_class=HTMLResponse)
    async def play_root(request: Request):
        """
        Serve the play shell landing page.

        This page can show a world picker or default to the configured world.
        """
        return _render_play_shell(request, world_id=None)

    @router.get("/play/{world_id}", response_class=HTMLResponse)
    async def play_world_root(request: Request, world_id: str):
        """
        Serve the play shell for a specific world.

        The client uses the world id to load world-specific assets.
        """
        return _render_play_shell(request, world_id=world_id)

    @router.get("/play/{world_id}/{path:path}", response_class=HTMLResponse)
    async def play_world_shell(request: Request, world_id: str, path: str):
        """
        Serve the play shell for all world subpaths.

        This supports client-side routing without server-side awareness of
        specific subpaths (rooms, inventory, chat, etc.).
        """
        _ = path  # Path is unused but retained for routing.
        return _render_play_shell(request, world_id=world_id)

    return router


def build_web_router() -> APIRouter:
    """
    Backwards-compatible wrapper that returns the admin router.

    Historically, tests and callers referenced build_web_router. Keep it
    as a thin wrapper to avoid breaking imports.
    """
    return build_admin_router()


def register_web_routes(app: FastAPI) -> None:
    """
    Register WebUI routes and static assets on the FastAPI app.

    Static files must be mounted on the FastAPI app (not an APIRouter),
    otherwise Starlette will not serve the assets correctly.
    """
    app.mount("/web/static", StaticFiles(directory=str(_STATIC_DIR)), name="web-static")
    app.include_router(build_admin_router())
    app.include_router(build_play_router())
