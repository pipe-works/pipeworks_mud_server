"""Route tests for canonical condition-axis pipeline endpoint.

Coverage focus:
- success payload shape for canonical responses
- structured route-level 422 validation responses
- passthrough mapping for 501/502/504 service errors
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mud_server.api.routes.register import register_routes
from mud_server.core.engine import GameEngine
from mud_server.core.world import World
from mud_server.db import database
from mud_server.services.condition_axis_service import (
    ConditionAxisGenerationResult,
    ConditionAxisProvenance,
    ConditionAxisServiceError,
)


def _build_pipeline_client(world_root: Path | None) -> TestClient:
    """Build a test client with a world that has a concrete world-root path.

    Args:
        world_root: World package root path injected into mocked world object.

    Returns:
        FastAPI TestClient with all routes registered.
    """
    app = FastAPI()

    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
        engine_any = cast(Any, engine)

    with patch.object(World, "_load_world", lambda self: None):
        world = World()
    world.world_id = "pipeworks_web"
    world.world_name = "Pipeworks Web"
    world._world_root = world_root
    world._world_json_path = (world_root or Path("/tmp")) / "world.json"

    def _get_world(world_id: str) -> World:
        if world_id == "pipeworks_web":
            return world
        raise ValueError(f"Unknown world: {world_id!r}")

    engine_any.world_registry = SimpleNamespace(get_world=_get_world)
    register_routes(app, engine)
    return TestClient(app)


def _valid_payload() -> dict[str, Any]:
    """Return canonical request payload used by route tests."""
    return {
        "world_id": "pipeworks_web",
        "seed": 123456,
        "bundle_id": "pipeworks_web_default",
        "inputs": {
            "entity": {
                "identity": {"gender": "male"},
                "species": "human",
            }
        },
    }


@pytest.mark.api
def test_pipeline_condition_axis_generate_success(
    test_db, db_with_users, tmp_path: Path, monkeypatch
):
    """Endpoint should return canonical response payload on service success."""
    client = _build_pipeline_client(tmp_path / "pipeworks_web")
    database.create_session("testplayer", "session-player")

    monkeypatch.setattr(
        "mud_server.api.routes.pipeline.service_generate_condition_axis",
        lambda **_kwargs: ConditionAxisGenerationResult(
            world_id="pipeworks_web",
            bundle_id="pipeworks_web_default",
            bundle_version="1",
            policy_hash="policy-hash",
            seed=123456,
            axes={"demeanor": 0.42, "health": 0.77},
            provenance=ConditionAxisProvenance(
                source="mud_server_canonical",
                served_via="/api/pipeline/condition-axis/generate",
                generator="entity_state_generation",
                generator_version="2.0.0",
                generator_capabilities=("axes_v2", "deterministic_seed"),
                generated_at="2026-03-07T12:00:00Z",
            ),
            entity_state={"axes": {"demeanor": {"score": 0.42}}},
        ),
    )

    response = client.post(
        "/api/pipeline/condition-axis/generate",
        params={"session_id": "session-player"},
        json=_valid_payload(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["world_id"] == "pipeworks_web"
    assert payload["bundle_id"] == "pipeworks_web_default"
    assert payload["seed"] == 123456
    assert payload["axes"]["demeanor"] == pytest.approx(0.42)
    assert payload["provenance"]["source"] == "mud_server_canonical"
    assert payload["provenance"]["generator_capabilities"] == ["axes_v2", "deterministic_seed"]


@pytest.mark.api
def test_pipeline_condition_axis_generate_returns_structured_422_for_invalid_payload(
    test_db, db_with_users, tmp_path: Path
):
    """Invalid payload should map to canonical structured 422 body."""
    client = _build_pipeline_client(tmp_path / "pipeworks_web")
    database.create_session("testplayer", "session-player")

    response = client.post(
        "/api/pipeline/condition-axis/generate",
        params={"session_id": "session-player"},
        json={"world_id": "pipeworks_web"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "CONDITION_AXIS_VALIDATION_ERROR"
    assert payload["stage"] == "axis_input"


@pytest.mark.api
def test_pipeline_condition_axis_generate_maps_501_from_service(
    test_db, db_with_users, tmp_path: Path, monkeypatch
):
    """Service unsupported errors should return canonical 501 payload."""
    client = _build_pipeline_client(tmp_path / "pipeworks_web")
    database.create_session("testplayer", "session-player")

    def _raise_unsupported(**_kwargs):
        raise ConditionAxisServiceError(
            status_code=501,
            code="CONDITION_AXIS_UPSTREAM_UNSUPPORTED",
            detail="Condition-axis generation is not available in the current upstream configuration.",
        )

    monkeypatch.setattr(
        "mud_server.api.routes.pipeline.service_generate_condition_axis", _raise_unsupported
    )

    response = client.post(
        "/api/pipeline/condition-axis/generate",
        params={"session_id": "session-player"},
        json=_valid_payload(),
    )

    assert response.status_code == 501
    payload = response.json()
    assert payload["code"] == "CONDITION_AXIS_UPSTREAM_UNSUPPORTED"
    assert payload["stage"] == "axis_input"


@pytest.mark.api
def test_pipeline_condition_axis_generate_maps_502_from_service(
    test_db, db_with_users, tmp_path: Path, monkeypatch
):
    """Service upstream failures should return canonical 502 payload."""
    client = _build_pipeline_client(tmp_path / "pipeworks_web")
    database.create_session("testplayer", "session-player")

    def _raise_failure(**_kwargs):
        raise ConditionAxisServiceError(
            status_code=502,
            code="CONDITION_AXIS_UPSTREAM_GENERATION_FAILED",
            detail="Failed to generate condition axis from upstream entity generator.",
        )

    monkeypatch.setattr(
        "mud_server.api.routes.pipeline.service_generate_condition_axis", _raise_failure
    )

    response = client.post(
        "/api/pipeline/condition-axis/generate",
        params={"session_id": "session-player"},
        json=_valid_payload(),
    )

    assert response.status_code == 502
    payload = response.json()
    assert payload["code"] == "CONDITION_AXIS_UPSTREAM_GENERATION_FAILED"
    assert payload["stage"] == "axis_input"


@pytest.mark.api
def test_pipeline_condition_axis_generate_maps_504_from_service(
    test_db, db_with_users, tmp_path: Path, monkeypatch
):
    """Service timeout failures should return canonical 504 payload."""
    client = _build_pipeline_client(tmp_path / "pipeworks_web")
    database.create_session("testplayer", "session-player")

    def _raise_timeout(**_kwargs):
        raise ConditionAxisServiceError(
            status_code=504,
            code="CONDITION_AXIS_UPSTREAM_TIMEOUT",
            detail="Timed out waiting for upstream condition-axis generation.",
        )

    monkeypatch.setattr(
        "mud_server.api.routes.pipeline.service_generate_condition_axis", _raise_timeout
    )

    response = client.post(
        "/api/pipeline/condition-axis/generate",
        params={"session_id": "session-player"},
        json=_valid_payload(),
    )

    assert response.status_code == 504
    payload = response.json()
    assert payload["code"] == "CONDITION_AXIS_UPSTREAM_TIMEOUT"
    assert payload["stage"] == "axis_input"


@pytest.mark.api
def test_pipeline_condition_axis_generate_returns_404_for_unknown_world(
    test_db, db_with_users, tmp_path: Path
):
    """Unknown worlds should map to structured 404 world-not-found responses."""
    client = _build_pipeline_client(tmp_path / "pipeworks_web")
    database.create_session("testplayer", "session-player")

    payload = _valid_payload()
    payload["world_id"] = "unknown_world"
    response = client.post(
        "/api/pipeline/condition-axis/generate",
        params={"session_id": "session-player"},
        json=payload,
    )

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "CONDITION_AXIS_WORLD_NOT_FOUND"
    assert body["stage"] == "axis_input"


@pytest.mark.api
def test_pipeline_condition_axis_generate_returns_501_when_world_root_missing(
    test_db, db_with_users
):
    """Worlds without resolved package roots should map to unsupported 501."""
    client = _build_pipeline_client(None)
    database.create_session("testplayer", "session-player")

    response = client.post(
        "/api/pipeline/condition-axis/generate",
        params={"session_id": "session-player"},
        json=_valid_payload(),
    )

    assert response.status_code == 501
    body = response.json()
    assert body["code"] == "CONDITION_AXIS_UPSTREAM_UNSUPPORTED"
    assert body["stage"] == "axis_input"
