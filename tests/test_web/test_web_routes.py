"""Tests for WebUI route scaffolding."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mud_server.web.routes import build_web_router


def test_admin_shell_served_at_root():
    """/admin should return the HTML shell."""
    app = FastAPI()
    app.include_router(build_web_router())

    client = TestClient(app)
    response = client.get("/admin")

    assert response.status_code == 200
    assert "PipeWorks Admin Dashboard" in response.text


def test_admin_shell_served_for_subpaths():
    """/admin/* should return the same HTML shell."""
    app = FastAPI()
    app.include_router(build_web_router())

    client = TestClient(app)
    response = client.get("/admin/users")

    assert response.status_code == 200
    assert "PipeWorks Admin Dashboard" in response.text
