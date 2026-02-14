"""
WebUI routes for serving the admin dashboard shell and static assets.

This module intentionally keeps server-side logic minimal:
- Serves a single HTML shell for `/admin` and `/admin/*`.
- Delegates all application behavior to client-side JS.
- Uses FastAPI's StaticFiles to serve CSS/JS assets.

No authentication logic lives here; the client authenticates against
existing API endpoints and enforces role checks. Server-side role checks
remain in the API layer.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Resolve paths relative to this file for predictable packaging.
_WEB_ROOT = Path(__file__).resolve().parent
_TEMPLATES_DIR = _WEB_ROOT / "templates"
_STATIC_DIR = _WEB_ROOT / "static"


templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def build_web_router() -> APIRouter:
    """
    Build the WebUI router and mount static assets.

    Returns:
        APIRouter configured to serve the admin dashboard shell and assets.
    """
    router = APIRouter()

    # Static files are mounted at /web/static so the UI can reference them.
    router.mount("/web/static", StaticFiles(directory=str(_STATIC_DIR)), name="web-static")

    @router.get("/admin", response_class=HTMLResponse)
    async def admin_root(request: Request):
        """
        Serve the WebUI shell for the admin dashboard.

        Client-side routing handles the actual view selection.
        """
        return templates.TemplateResponse(request, "admin_shell.html", {})

    @router.get("/admin/{path:path}", response_class=HTMLResponse)
    async def admin_shell(request: Request, path: str):
        """
        Serve the same WebUI shell for all admin routes.

        This supports client-side routing without server-side awareness of
        specific subpaths.
        """
        _ = path  # Path is unused but retained for routing.
        return templates.TemplateResponse(request, "admin_shell.html", {})

    return router
