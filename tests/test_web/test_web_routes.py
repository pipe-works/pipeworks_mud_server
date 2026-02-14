"""Tests for WebUI route scaffolding."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mud_server.web.routes import register_web_routes


def test_admin_shell_served_at_root():
    """/admin should return the HTML shell."""
    app = FastAPI()
    register_web_routes(app)

    client = TestClient(app)
    response = client.get("/admin")

    assert response.status_code == 200
    assert "PipeWorks Admin Dashboard" in response.text


def test_admin_shell_served_for_subpaths():
    """/admin/* should return the same HTML shell."""
    app = FastAPI()
    register_web_routes(app)

    client = TestClient(app)
    response = client.get("/admin/users")

    assert response.status_code == 200
    assert "PipeWorks Admin Dashboard" in response.text


def test_admin_shell_served_for_schema():
    """/admin/schema should return the HTML shell."""
    app = FastAPI()
    register_web_routes(app)

    client = TestClient(app)
    response = client.get("/admin/schema")

    assert response.status_code == 200
    assert "PipeWorks Admin Dashboard" in response.text
