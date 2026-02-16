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


def test_play_shell_served_at_root():
    """/play should return the play HTML shell."""
    app = FastAPI()
    register_web_routes(app)

    client = TestClient(app)
    response = client.get("/play")

    assert response.status_code == 200
    assert "PipeWorks Play" in response.text
    assert "Account username" in response.text
    assert 'id="play-character-select"' in response.text
    assert "Select a world to load available characters." in response.text
    assert "play/css/shell.css" in response.text
    assert "play/js/play.js?v=" in response.text


def test_play_shell_served_for_world():
    """/play/<world_id> should include the world id in the shell."""
    app = FastAPI()
    register_web_routes(app)

    client = TestClient(app)
    response = client.get("/play/pipeworks_web")

    assert response.status_code == 200
    assert 'data-world-id="pipeworks_web"' in response.text
    assert "play/css/fonts.css" in response.text
    assert "play/css/shared-base.css" in response.text
    assert "play/css/shell.css" in response.text
    assert "play/css/worlds/pipeworks_web.css?v=" in response.text
    assert "play/js/worlds/pipeworks_web.js?v=" in response.text


def test_play_shell_served_for_world_subpaths():
    """/play/<world_id>/* should return the same HTML shell."""
    app = FastAPI()
    register_web_routes(app)

    client = TestClient(app)
    response = client.get("/play/pipeworks_web/rooms/spawn")

    assert response.status_code == 200
    assert 'data-world-id="pipeworks_web"' in response.text
    assert "play/css/fonts.css" in response.text
    assert "play/css/shell.css" in response.text
