"""Tests for lab API endpoints (``/api/lab/*``).

Covers:
- Role enforcement: player and worldbuilder receive 403; admin and
  superuser are permitted through.
- World not found returns 404 from ``world-config`` and ``translate``.
- Translation layer disabled returns 404 from ``world-config`` and 503
  from ``translate``.
- Happy path: ``worlds`` list, ``world-config``, and ``translate``
  (success, api_error, validation_failed outcomes).
- Invalid session returns 401.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mud_server.api.routes.register import register_routes
from mud_server.config import use_test_database
from mud_server.core.engine import GameEngine
from mud_server.core.world import World
from mud_server.translation.config import TranslationLayerConfig
from mud_server.translation.service import LabTranslateResult, OOCToICTranslationService
from tests.constants import TEST_PASSWORD

# ── Shared test helpers ────────────────────────────────────────────────────────


def _make_translation_config(**overrides) -> TranslationLayerConfig:
    """Build a TranslationLayerConfig with sensible lab-test defaults."""
    data: dict = {
        "enabled": True,
        "model": "gemma2:2b",
        "strict_mode": True,
        "max_output_chars": 280,
        "active_axes": ["demeanor", "health"],
        **overrides,
    }
    return TranslationLayerConfig.from_dict(data, world_root=Path("/fake"))


def _make_mock_service(result: LabTranslateResult | None = None) -> OOCToICTranslationService:
    """Return a mock OOCToICTranslationService with a canned translate_with_axes result."""
    service = MagicMock(spec=OOCToICTranslationService)
    service.config = _make_translation_config()
    if result is None:
        result = LabTranslateResult(
            ic_text="I must find another way out.",
            status="success",
            profile_summary="  Character: Lab Subject\n  Demeanor: timid (0.07)",
            rendered_prompt="<rendered system prompt>",
        )
    service.translate_with_axes.return_value = result
    return service


def _build_lab_engine(
    mock_world: World,
    *,
    world_id: str = "test_world",
    world_name: str = "Test World",
) -> GameEngine:
    """Build a mock GameEngine whose world registry returns ``mock_world``."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
        engine_any = cast(Any, engine)

    def _get_world(wid: str) -> World:
        if wid == world_id:
            return mock_world
        raise ValueError(f"Unknown world: {wid!r}")

    engine_any.world_registry = SimpleNamespace(
        get_world=_get_world,
        list_worlds=lambda: [{"world_id": world_id, "name": world_name, "is_active": True}],
    )
    return engine


def _build_world_with_service(
    service: OOCToICTranslationService | None,
) -> World:
    """Build a bare World instance with ``_translation_service`` set directly."""
    with patch.object(World, "_load_world", lambda self: None):
        world = World()
    world.world_name = "Test World"
    world.world_id = "test_world"
    world._translation_service = service  # type: ignore[attr-defined]
    return world


@pytest.fixture()
def lab_client(test_db, temp_db_path):
    """TestClient backed by a world with the translation layer enabled."""
    world = _build_world_with_service(_make_mock_service())
    engine = _build_lab_engine(world)

    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        yield client


@pytest.fixture()
def lab_client_no_translation(test_db, temp_db_path):
    """TestClient backed by a world with translation layer disabled."""
    world = _build_world_with_service(None)  # service=None → disabled
    engine = _build_lab_engine(world)

    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        yield client


def _login(client: TestClient, username: str) -> str:
    """Log in and return the session_id."""
    resp = client.post("/login", json={"username": username, "password": TEST_PASSWORD})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["session_id"]


# ── Role enforcement ───────────────────────────────────────────────────────────


@pytest.mark.api
def test_worlds_forbidden_for_player(lab_client, db_with_users, temp_db_path):
    """Player role must receive 403 on GET /api/lab/worlds."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testplayer")
        resp = lab_client.get(f"/api/lab/worlds?session_id={sid}")
    assert resp.status_code == 403


@pytest.mark.api
def test_worlds_forbidden_for_worldbuilder(lab_client, db_with_users, temp_db_path):
    """Worldbuilder role must receive 403 on GET /api/lab/worlds."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testbuilder")
        resp = lab_client.get(f"/api/lab/worlds?session_id={sid}")
    assert resp.status_code == 403


@pytest.mark.api
def test_worlds_allowed_for_admin(lab_client, db_with_users, temp_db_path):
    """Admin role must be permitted on GET /api/lab/worlds."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        resp = lab_client.get(f"/api/lab/worlds?session_id={sid}")
    assert resp.status_code == 200


@pytest.mark.api
def test_worlds_allowed_for_superuser(lab_client, db_with_users, temp_db_path):
    """Superuser role must be permitted on GET /api/lab/worlds."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testsuperuser")
        resp = lab_client.get(f"/api/lab/worlds?session_id={sid}")
    assert resp.status_code == 200


@pytest.mark.api
def test_world_config_forbidden_for_player(lab_client, db_with_users, temp_db_path):
    """Player role must receive 403 on GET /api/lab/world-config/{world_id}."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testplayer")
        resp = lab_client.get(f"/api/lab/world-config/test_world?session_id={sid}")
    assert resp.status_code == 403


@pytest.mark.api
def test_translate_forbidden_for_player(lab_client, db_with_users, temp_db_path):
    """Player role must receive 403 on POST /api/lab/translate."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testplayer")
        resp = lab_client.post(
            "/api/lab/translate",
            json={
                "session_id": sid,
                "world_id": "test_world",
                "axes": {"demeanor": {"label": "timid", "score": 0.07}},
                "ooc_message": "Hello",
            },
        )
    assert resp.status_code == 403


# ── Invalid session ────────────────────────────────────────────────────────────


@pytest.mark.api
def test_worlds_invalid_session_returns_401(lab_client, test_db, temp_db_path):
    """Non-existent session_id must return 401."""
    with use_test_database(temp_db_path):
        resp = lab_client.get("/api/lab/worlds?session_id=not-a-real-session")
    assert resp.status_code == 401


# ── GET /api/lab/worlds ────────────────────────────────────────────────────────


@pytest.mark.api
def test_worlds_returns_list_with_translation_flag(lab_client, db_with_users, temp_db_path):
    """Worlds endpoint returns the world list with translation_enabled set."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        resp = lab_client.get(f"/api/lab/worlds?session_id={sid}")

    assert resp.status_code == 200
    data = resp.json()
    assert "worlds" in data
    worlds = data["worlds"]
    assert len(worlds) == 1
    assert worlds[0]["world_id"] == "test_world"
    assert worlds[0]["name"] == "Test World"
    assert worlds[0]["translation_enabled"] is True


@pytest.mark.api
def test_worlds_translation_disabled_flag(lab_client_no_translation, db_with_users, temp_db_path):
    """Worlds endpoint reports translation_enabled=False when service is None."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client_no_translation, "testadmin")
        resp = lab_client_no_translation.get(f"/api/lab/worlds?session_id={sid}")

    assert resp.status_code == 200
    worlds = resp.json()["worlds"]
    assert worlds[0]["translation_enabled"] is False


# ── GET /api/lab/world-config/{world_id} ──────────────────────────────────────


@pytest.mark.api
def test_world_config_returns_config(lab_client, db_with_users, temp_db_path):
    """World-config endpoint returns the translation layer config."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        resp = lab_client.get(f"/api/lab/world-config/test_world?session_id={sid}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["world_id"] == "test_world"
    assert data["model"] == "gemma2:2b"
    assert data["active_axes"] == ["demeanor", "health"]
    assert data["strict_mode"] is True
    assert data["translation_enabled"] is True


@pytest.mark.api
def test_world_config_unknown_world_returns_404(lab_client, db_with_users, temp_db_path):
    """World-config returns 404 for an unknown world_id."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        resp = lab_client.get(f"/api/lab/world-config/no_such_world?session_id={sid}")
    assert resp.status_code == 404


@pytest.mark.api
def test_world_config_translation_disabled_returns_404(
    lab_client_no_translation, db_with_users, temp_db_path
):
    """World-config returns 404 when translation layer is disabled for that world."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client_no_translation, "testadmin")
        resp = lab_client_no_translation.get(f"/api/lab/world-config/test_world?session_id={sid}")
    assert resp.status_code == 404


# ── POST /api/lab/translate ────────────────────────────────────────────────────


_TRANSLATE_PAYLOAD = {
    "world_id": "test_world",
    "axes": {
        "demeanor": {"label": "timid", "score": 0.07},
        "health": {"label": "scarred", "score": 0.65},
    },
    "channel": "say",
    "ooc_message": "I need to get out of here.",
    "character_name": "Lab Subject",
    "seed": -1,
    "temperature": 0.7,
}


@pytest.mark.api
def test_translate_success(lab_client, db_with_users, temp_db_path):
    """Translate endpoint returns IC text, profile_summary, and rendered_prompt."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        payload = {**_TRANSLATE_PAYLOAD, "session_id": sid}
        resp = lab_client.post("/api/lab/translate", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["ic_text"] == "I must find another way out."
    assert "profile_summary" in data
    assert "rendered_prompt" in data
    assert data["model"] == "gemma2:2b"
    assert data["world_config"]["world_id"] == "test_world"
    assert data["world_config"]["active_axes"] == ["demeanor", "health"]


@pytest.mark.api
def test_translate_fallback_api_error(test_db, temp_db_path, db_with_users):
    """Translate endpoint surfaces api_error status when Ollama is unreachable."""
    error_result = LabTranslateResult(
        ic_text=None,
        status="fallback.api_error",
        profile_summary="  Character: Lab Subject",
        rendered_prompt="<rendered>",
    )
    world = _build_world_with_service(_make_mock_service(error_result))
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        payload = {**_TRANSLATE_PAYLOAD, "session_id": sid}
        resp = client.post("/api/lab/translate", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "fallback.api_error"
    assert data["ic_text"] is None


@pytest.mark.api
def test_translate_fallback_validation_failed(test_db, temp_db_path, db_with_users):
    """Translate endpoint surfaces validation_failed status when output is rejected."""
    val_fail_result = LabTranslateResult(
        ic_text=None,
        status="fallback.validation_failed",
        profile_summary="  Character: Lab Subject",
        rendered_prompt="<rendered>",
    )
    world = _build_world_with_service(_make_mock_service(val_fail_result))
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        payload = {**_TRANSLATE_PAYLOAD, "session_id": sid}
        resp = client.post("/api/lab/translate", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "fallback.validation_failed"
    assert data["ic_text"] is None


@pytest.mark.api
def test_translate_unknown_world_returns_404(lab_client, db_with_users, temp_db_path):
    """Translate returns 404 for an unknown world_id."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        payload = {**_TRANSLATE_PAYLOAD, "session_id": sid, "world_id": "no_such_world"}
        resp = lab_client.post("/api/lab/translate", json=payload)
    assert resp.status_code == 404


@pytest.mark.api
def test_translate_translation_disabled_returns_503(
    lab_client_no_translation, db_with_users, temp_db_path
):
    """Translate returns 503 when translation layer is disabled for the world."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client_no_translation, "testadmin")
        payload = {**_TRANSLATE_PAYLOAD, "session_id": sid}
        resp = lab_client_no_translation.post("/api/lab/translate", json=payload)
    assert resp.status_code == 503


@pytest.mark.api
def test_translate_passes_axes_to_service(test_db, temp_db_path, db_with_users):
    """Translate passes axes, channel, seed, and temperature to translate_with_axes."""
    mock_service = _make_mock_service()
    world = _build_world_with_service(mock_service)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        payload = {
            **_TRANSLATE_PAYLOAD,
            "session_id": sid,
            "seed": 42,
            "temperature": 0.3,
            "character_name": "Mira",
            "channel": "whisper",
        }
        resp = client.post("/api/lab/translate", json=payload)

    assert resp.status_code == 200
    call_kwargs = mock_service.translate_with_axes.call_args
    assert call_kwargs.kwargs["character_name"] == "Mira"
    assert call_kwargs.kwargs["channel"] == "whisper"
    assert call_kwargs.kwargs["seed"] == 42
    assert call_kwargs.kwargs["temperature"] == 0.3


@pytest.mark.api
def test_translate_seed_minus_one_passes_none_to_service(test_db, temp_db_path, db_with_users):
    """seed=-1 (random) must be converted to None before calling translate_with_axes."""
    mock_service = _make_mock_service()
    world = _build_world_with_service(mock_service)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        payload = {**_TRANSLATE_PAYLOAD, "session_id": sid, "seed": -1}
        client.post("/api/lab/translate", json=payload)

    call_kwargs = mock_service.translate_with_axes.call_args
    assert call_kwargs.kwargs["seed"] is None
