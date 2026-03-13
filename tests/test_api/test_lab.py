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

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mud_server.api.routes.register import register_routes
from mud_server.config import use_test_database
from mud_server.core.engine import GameEngine
from mud_server.core.world import World
from mud_server.db import database
from mud_server.services import policy_service
from mud_server.translation.config import TranslationLayerConfig
from mud_server.translation.service import LabTranslateResult, OOCToICTranslationService
from tests.constants import TEST_PASSWORD

_LEGACY_LAB_FILE_AUTHORING_ENV = "MUD_LAB_ENABLE_LEGACY_FILE_AUTHORING"


@pytest.fixture(autouse=True)
def enable_legacy_lab_file_authoring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep legacy file-backed lab routes enabled for existing lab test coverage."""
    monkeypatch.setenv(_LEGACY_LAB_FILE_AUTHORING_ENV, "1")


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
            prompt_template="<raw template>",
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
    world._translation_service = service
    return world


def _build_prompt_world(
    world_root: Path,
    *,
    prompt_template_path: str = "policies/ic_prompt.txt",
) -> World:
    """Build a world rooted at a temporary policies directory for prompt-route tests."""
    service = _make_mock_service()
    cast(Any, service).config = _make_translation_config(
        prompt_template_path=prompt_template_path,
    )
    world = _build_world_with_service(service)
    world._world_root = world_root
    world._world_json_path = world_root / "world.json"
    return world


def _ensure_axis_policy_dir(policy_root: Path) -> Path:
    """Ensure ``policies/axis`` exists and return the directory path."""
    axis_dir = policy_root / "axis"
    axis_dir.mkdir(parents=True, exist_ok=True)
    return axis_dir


def _write_minimal_policy_package(policy_root: Path) -> None:
    """Write a one-axis canonical policy package used by lab route tests."""

    policy_root.mkdir(parents=True, exist_ok=True)
    (_ensure_axis_policy_dir(policy_root) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "source: test\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policy_root) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policy_root) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )


def _write_policy_bundle_draft(
    policy_root: Path,
    *,
    filename: str = "test_world_bundle_alt.json",
    world_id: str = "test_world",
    version: str = "0.2.0",
) -> None:
    """Write one normalized policy bundle draft under ``policies/drafts``."""

    drafts = policy_root / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    payload = {
        "world_id": world_id,
        "version": version,
        "source": "lab draft",
        "policy_hash": None,
        "axes_order": ["demeanor"],
        "axes": {
            "demeanor": {
                "group": "character",
                "ordering": ["timid", "proud"],
                "thresholds": [
                    {"label": "timid", "min": 0.0, "max": 0.44},
                    {"label": "proud", "min": 0.45, "max": 1.0},
                ],
            }
        },
        "chat_rules": {
            "channel_multipliers": {"say": 1.0, "yell": 1.4, "whisper": 0.6},
            "min_gap_threshold": 0.07,
            "axes": {"demeanor": {"resolver": "dominance_shift", "base_magnitude": 0.04}},
        },
    }
    (drafts / filename).write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_manifest_policy_package(policy_root: Path) -> None:
    """Write a minimal manifest-driven package for prompt/image policy tests."""
    policy_root.mkdir(parents=True, exist_ok=True)
    (policy_root / "manifest.yaml").write_text(
        """
schema_version: 0.1.0
policy_schema: pipeworks_policy_v1
world_id: test_world
policy_bundle:
  id: pipeworks_web_default
  version: 1
identity_contract:
  fixed_traits:
    gender:
      type: enum
      allowed_values: [male, female]
      required: true
axis:
  active_bundle:
    id: axis_core_v1
    version: 1
    files:
      axes: policies/axis/axes.yaml
      thresholds: policies/axis/thresholds.yaml
      resolution: policies/axis/resolution.yaml
translation:
  active_prompt:
    id: ic_default_v1
    version: 1
    path: policies/translation/prompts/ic/default_v1.txt
image:
  descriptor_layer:
    id: id_card_v1
    version: 1
    path: policies/image/descriptor_layers/id_card_v1.txt
  tone_profile:
    id: ledger_engraving_v1
    version: 1
    path: policies/image/tone_profiles/ledger_engraving_v1.json
  registries:
    species: policies/image/registries/species_registry.yaml
    clothing: policies/image/registries/clothing_registry.yaml
  composition:
    order:
      - species_canon_block
      - descriptor_layer_output
      - clothing_block
      - tone_profile_block
    required_runtime_inputs:
      - entity.identity.gender
      - entity.species
      - entity.axes
""",
        encoding="utf-8",
    )
    (policy_root / "axis").mkdir(parents=True, exist_ok=True)
    (_ensure_axis_policy_dir(policy_root) / "axes.yaml").write_text(
        "version: 0.1.0\naxes:\n  demeanor:\n    ordering:\n      type: ordinal\n      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policy_root) / "thresholds.yaml").write_text(
        "version: 0.1.0\naxes:\n  demeanor:\n    values:\n      timid: {min: 0.0, max: 0.49}\n      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policy_root) / "resolution.yaml").write_text(
        'version: "1.0"\ninteractions:\n  chat:\n    axes: {}\n', encoding="utf-8"
    )
    (policy_root / "translation" / "prompts" / "ic").mkdir(parents=True, exist_ok=True)
    (policy_root / "translation" / "prompts" / "ic" / "default_v1.txt").write_text(
        "Manifest prompt {{profile_summary}}",
        encoding="utf-8",
    )
    (policy_root / "image" / "descriptor_layers").mkdir(parents=True, exist_ok=True)
    (policy_root / "image" / "descriptor_layers" / "id_card_v1.txt").write_text(
        "Descriptor layer",
        encoding="utf-8",
    )
    (policy_root / "image" / "tone_profiles").mkdir(parents=True, exist_ok=True)
    (policy_root / "image" / "tone_profiles" / "ledger_engraving_v1.json").write_text(
        '{"name":"ledger_engraving_v1"}',
        encoding="utf-8",
    )
    (policy_root / "image" / "registries").mkdir(parents=True, exist_ok=True)
    (policy_root / "image" / "registries" / "species_registry.yaml").write_text(
        "registry: {id: species_registry, version: 1, kind: species}",
        encoding="utf-8",
    )
    (policy_root / "image" / "registries" / "clothing_registry.yaml").write_text(
        "registry: {id: clothing_registry, version: 1, kind: clothing}",
        encoding="utf-8",
    )


def _write_manifest_compile_policy_package(policy_root: Path) -> None:
    """Write manifest policy fixtures with concrete species/clothing block entries."""
    _write_manifest_policy_package(policy_root)

    (policy_root / "image" / "blocks" / "species").mkdir(parents=True, exist_ok=True)
    (policy_root / "image" / "blocks" / "clothing" / "environment").mkdir(
        parents=True, exist_ok=True
    )
    (policy_root / "image" / "blocks" / "clothing" / "activity").mkdir(parents=True, exist_ok=True)
    (policy_root / "image" / "blocks" / "clothing" / "wealth").mkdir(parents=True, exist_ok=True)

    (policy_root / "image" / "blocks" / "species" / "goblin_v1.yaml").write_text(
        "text: A goblin of pipe-works canon with upright humanoid posture.\n",
        encoding="utf-8",
    )
    (policy_root / "image" / "blocks" / "clothing" / "environment" / "coastal_v1.txt").write_text(
        "Practical coastal clothing suited to wind and damp.",
        encoding="utf-8",
    )
    (
        policy_root / "image" / "blocks" / "clothing" / "activity" / "general_labour_v1.txt"
    ).write_text(
        "Garments suggest regular manual work and functional movement.",
        encoding="utf-8",
    )
    (policy_root / "image" / "blocks" / "clothing" / "wealth" / "modest_v1.txt").write_text(
        "Fabrics are modest, durable, and maintained.",
        encoding="utf-8",
    )

    (policy_root / "image" / "tone_profiles" / "ledger_engraving_v1.json").write_text(
        '{"name":"ledger_engraving_v1","prompt_block":"Linocut style with muted sepia palette."}',
        encoding="utf-8",
    )
    (policy_root / "image" / "registries" / "species_registry.yaml").write_text(
        """
registry:
  id: species_registry
  version: 1
  kind: species
entries:
  - id: goblin_pipeworks_v1
    version: 1
    block_type: species
    status: active
    render_priority: 100
    block_path: policies/image/blocks/species/goblin_v1.yaml
    compatible_species: [goblin]
    compatible_genders: [male, female]
    selection_rules:
      when:
        species_any: [goblin]
""",
        encoding="utf-8",
    )
    (policy_root / "image" / "registries" / "clothing_registry.yaml").write_text(
        """
registry:
  id: clothing_registry
  version: 1
  kind: clothing
composition_contract:
  slots: [environment, activity, wealth]
defaults:
  profile_id: clothing_default_v1
slots:
  environment:
    - id: clothing_environment_coastal_v1
      version: 1
      block_type: clothing_fragment
      status: active
      render_priority: 90
      fragment_path: policies/image/blocks/clothing/environment/coastal_v1.txt
      compatible_genders: [male, female]
      selection_rules:
        when:
          world_context_any: [coastal]
  activity:
    - id: clothing_activity_general_labour_v1
      version: 1
      block_type: clothing_fragment
      status: active
      render_priority: 80
      fragment_path: policies/image/blocks/clothing/activity/general_labour_v1.txt
      compatible_genders: [male, female]
      selection_rules:
        when:
          occupation_signal_any: [manual_labour]
  wealth:
    - id: clothing_wealth_modest_v1
      version: 1
      block_type: clothing_fragment
      status: active
      render_priority: 80
      fragment_path: policies/image/blocks/clothing/wealth/modest_v1.txt
      compatible_genders: [male, female]
      selection_rules:
        when:
          axis_labels:
            wealth_any: [modest, well-kept]
profiles:
  - id: clothing_default_v1
    version: 1
    status: active
    render_priority: 100
    strategy: slot_select
    slot_priority: [environment, activity, wealth]
""",
        encoding="utf-8",
    )


def _import_world_policy_files_into_canonical_db(
    *,
    monkeypatch: pytest.MonkeyPatch,
    world_root: Path,
    world_id: str,
) -> None:
    """Import one test world's policy files into canonical DB activation state."""
    monkeypatch.setattr(policy_service.config.worlds, "worlds_root", str(world_root.parent))
    monkeypatch.setattr(policy_service.config.worlds, "default_world_id", world_id)
    summary = policy_service.import_world_policies_from_legacy_files(
        world_id=world_id,
        actor="test-importer",
        activate=True,
        status="active",
    )
    assert summary.error_count == 0, summary


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
    return str(resp.json()["session_id"])


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
        prompt_template="<raw template>",
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
        prompt_template="<raw template>",
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
    call_kwargs = cast(Any, mock_service).translate_with_axes.call_args
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

    call_kwargs = cast(Any, mock_service).translate_with_axes.call_args
    assert call_kwargs.kwargs["seed"] is None


# ── GET /api/lab/world-prompts/{world_id} ─────────────────────────────────────


@pytest.mark.api
def test_world_prompts_returns_410_when_legacy_file_mode_disabled(
    test_db, temp_db_path, db_with_users, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """File-backed prompt routes should be disabled by default for DB-first deployments."""
    monkeypatch.delenv(_LEGACY_LAB_FILE_AUTHORING_ENV, raising=False)
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt {{profile_summary}}")

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world?session_id={sid}")

    assert resp.status_code == 410
    detail = resp.json()["detail"]
    assert "Legacy file-backed lab policy routes are disabled" in detail
    assert "/api/policies" in detail


@pytest.mark.api
def test_world_prompts_returns_files(test_db, temp_db_path, db_with_users, tmp_path):
    """World-prompts endpoint returns .txt files from policies/ with active flag."""
    # Set up a policies directory with two .txt files.
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt {{profile_summary}}")
    (policies / "alt_prompt.txt").write_text("Alternative prompt {{profile_summary}}")
    (policies / "not_a_prompt.yaml").write_text("should be ignored")

    mock_service = _make_mock_service()
    cast(Any, mock_service).config = _make_translation_config(
        prompt_template_path="policies/ic_prompt.txt"
    )

    world = _build_world_with_service(mock_service)
    world._world_root = tmp_path

    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world?session_id={sid}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["world_id"] == "test_world"
    prompts = data["prompts"]
    assert len(prompts) == 2
    names = {p["filename"] for p in prompts}
    assert names == {"alt_prompt.txt", "ic_prompt.txt"}
    active = [p for p in prompts if p["is_active"]]
    assert len(active) == 1
    assert active[0]["filename"] == "ic_prompt.txt"
    assert active[0]["content"] == "Active prompt {{profile_summary}}"


@pytest.mark.api
def test_world_prompts_manifest_nested_prompt_is_listed_and_active(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Manifest-configured nested prompt paths should be listed and marked active."""
    policies = tmp_path / "policies"
    _write_manifest_policy_package(policies)

    # Legacy config path intentionally differs; manifest path should win.
    mock_service = _make_mock_service()
    cast(Any, mock_service).config = _make_translation_config(
        prompt_template_path="policies/ic_prompt.txt"
    )
    world = _build_world_with_service(mock_service)
    world._world_root = tmp_path

    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world?session_id={sid}")

    assert resp.status_code == 200
    prompts = resp.json()["prompts"]
    filenames = {p["filename"] for p in prompts}
    assert "translation/prompts/ic/default_v1.txt" in filenames

    active = [p for p in prompts if p["is_active"]]
    assert len(active) == 1
    assert active[0]["filename"] == "translation/prompts/ic/default_v1.txt"


@pytest.mark.api
def test_world_prompts_no_world_root_returns_empty(test_db, temp_db_path, db_with_users):
    """World-prompts returns an empty list when _world_root is None."""
    mock_service = _make_mock_service()
    world = _build_world_with_service(mock_service)
    world._world_root = None

    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world?session_id={sid}")

    assert resp.status_code == 200
    assert resp.json()["prompts"] == []


@pytest.mark.api
def test_world_prompts_no_policies_dir_returns_empty(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """World-prompts returns an empty list when policies/ directory doesn't exist."""
    mock_service = _make_mock_service()
    world = _build_world_with_service(mock_service)
    # tmp_path exists but has no policies/ subdirectory.
    world._world_root = tmp_path

    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world?session_id={sid}")

    assert resp.status_code == 200
    assert resp.json()["prompts"] == []


@pytest.mark.api
def test_world_prompts_skips_unreadable_file(test_db, temp_db_path, db_with_users, tmp_path):
    """World-prompts skips .txt files that raise OSError on read."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "good.txt").write_text("readable prompt")
    bad_file = policies / "bad.txt"
    bad_file.write_text("will be unreadable")
    bad_file.chmod(0o000)

    mock_service = _make_mock_service()
    cast(Any, mock_service).config = _make_translation_config(
        prompt_template_path="policies/good.txt"
    )
    world = _build_world_with_service(mock_service)
    world._world_root = tmp_path

    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world?session_id={sid}")

    # Restore permissions for cleanup.
    bad_file.chmod(0o644)

    assert resp.status_code == 200
    prompts = resp.json()["prompts"]
    filenames = [p["filename"] for p in prompts]
    assert "good.txt" in filenames
    assert "bad.txt" not in filenames


@pytest.mark.api
def test_world_prompts_unknown_world_returns_404(lab_client, db_with_users, temp_db_path):
    """World-prompts returns 404 for an unknown world_id."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        resp = lab_client.get(f"/api/lab/world-prompts/no_such_world?session_id={sid}")
    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompts_translation_disabled_returns_404(
    lab_client_no_translation, db_with_users, temp_db_path
):
    """World-prompts returns 404 when translation layer is disabled."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client_no_translation, "testadmin")
        resp = lab_client_no_translation.get(f"/api/lab/world-prompts/test_world?session_id={sid}")
    assert resp.status_code == 404


# ── GET /api/lab/world-image-policy-bundle/{world_id} ───────────────────────


@pytest.mark.api
def test_world_image_policy_bundle_returns_manifest_contract(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Image policy bundle endpoint should return manifest-resolved references."""
    policies = tmp_path / "policies"
    _write_manifest_policy_package(policies)

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-image-policy-bundle/test_world?session_id={sid}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["world_id"] == "test_world"
    assert data["policy_schema"] == "pipeworks_policy_v1"
    assert data["policy_bundle_id"] == "pipeworks_web_default"
    assert data["policy_hash"]
    assert data["descriptor_layer_path"] == "policies/image/descriptor_layers/id_card_v1.txt"
    assert data["species_registry_path"] == "policies/image/registries/species_registry.yaml"
    assert "entity.identity.gender" in data["required_runtime_inputs"]


@pytest.mark.api
def test_world_image_policy_bundle_missing_manifest_returns_404(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Image policy bundle endpoint should return 404 without a manifest file."""
    (tmp_path / "policies").mkdir()

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-image-policy-bundle/test_world?session_id={sid}")

    assert resp.status_code == 404


@pytest.mark.api
def test_world_image_policy_bundle_policy_hash_changes_on_content_change(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Bundle policy hash should change when referenced asset content changes."""
    policies = tmp_path / "policies"
    _write_manifest_policy_package(policies)

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp_one = client.get(f"/api/lab/world-image-policy-bundle/test_world?session_id={sid}")
        assert resp_one.status_code == 200
        hash_one = resp_one.json()["policy_hash"]

        descriptor_path = policies / "image" / "descriptor_layers" / "id_card_v1.txt"
        descriptor_path.write_text("Descriptor layer updated for hash test.", encoding="utf-8")

        resp_two = client.get(f"/api/lab/world-image-policy-bundle/test_world?session_id={sid}")
        assert resp_two.status_code == 200
        hash_two = resp_two.json()["policy_hash"]

    assert hash_one != hash_two


# ── POST /api/lab/compile-image-prompt ──────────────────────────────────────


@pytest.mark.api
def test_compile_image_prompt_returns_compiled_prompt(
    test_db, temp_db_path, db_with_users, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Compile endpoint should return deterministic selection metadata + prompt."""
    world_id = database.DEFAULT_WORLD_ID
    world_root = tmp_path / world_id
    policies = world_root / "policies"
    _write_manifest_compile_policy_package(policies)

    world = _build_prompt_world(world_root)
    world.world_id = world_id
    engine = _build_lab_engine(world, world_id=world_id)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        _import_world_policy_files_into_canonical_db(
            monkeypatch=monkeypatch,
            world_root=world_root,
            world_id=world_id,
        )
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/compile-image-prompt",
            json={
                "session_id": sid,
                "world_id": world_id,
                "species": "goblin",
                "gender": "male",
                "axes": {
                    "wealth": {"label": "modest", "score": 0.33},
                    "demeanor": {"label": "alert", "score": 0.70},
                },
                "world_context": ["coastal"],
                "occupation_signals": ["manual_labour"],
                "model_id": "flux-2-klein-4b",
                "aspect_ratio": "1:1",
                "seed": 123,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["world_id"] == world_id
    assert data["selected_species_block_id"] == "goblin_pipeworks_v1"
    assert data["selected_clothing_profile_id"] == "clothing_default_v1"
    assert data["selected_clothing_slot_ids"]["environment"] == "clothing_environment_coastal_v1"
    assert data["selected_clothing_slot_ids"]["activity"] == "clothing_activity_general_labour_v1"
    assert data["selected_clothing_slot_ids"]["wealth"] == "clothing_wealth_modest_v1"
    assert "A goblin of pipe-works canon" in data["compiled_prompt"]
    assert "Practical coastal clothing" in data["compiled_prompt"]
    assert "Linocut style with muted sepia palette." in data["compiled_prompt"]
    assert data["policy_hash"]
    assert data["axis_hash"]
    assert "entity.identity.gender" in data["required_runtime_inputs"]


@pytest.mark.api
def test_compile_image_prompt_returns_409_when_species_block_unmatched(
    test_db, temp_db_path, db_with_users, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Compile endpoint should reject requests with no matching species block."""
    world_id = database.DEFAULT_WORLD_ID
    world_root = tmp_path / world_id
    policies = world_root / "policies"
    _write_manifest_compile_policy_package(policies)

    world = _build_prompt_world(world_root)
    world.world_id = world_id
    engine = _build_lab_engine(world, world_id=world_id)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        _import_world_policy_files_into_canonical_db(
            monkeypatch=monkeypatch,
            world_root=world_root,
            world_id=world_id,
        )
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/compile-image-prompt",
            json={
                "session_id": sid,
                "world_id": world_id,
                "species": "human",
                "gender": "male",
                "axes": {"wealth": {"label": "modest", "score": 0.33}},
            },
        )

    assert resp.status_code == 409
    assert "No active species block matched" in resp.json()["detail"]


@pytest.mark.api
def test_compile_image_prompt_gender_validation(
    test_db,
    temp_db_path,
    db_with_users,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Compile endpoint should reject invalid gender values at request validation."""
    world_id = database.DEFAULT_WORLD_ID
    world_root = tmp_path / world_id
    policies = world_root / "policies"
    _write_manifest_compile_policy_package(policies)

    world = _build_prompt_world(world_root)
    world.world_id = world_id
    engine = _build_lab_engine(world, world_id=world_id)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        _import_world_policy_files_into_canonical_db(
            monkeypatch=monkeypatch,
            world_root=world_root,
            world_id=world_id,
        )
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/compile-image-prompt",
            json={
                "session_id": sid,
                "world_id": world_id,
                "species": "goblin",
                "gender": "invalid",
                "axes": {"wealth": {"label": "modest", "score": 0.33}},
            },
        )

    assert resp.status_code == 422


@pytest.mark.api
def test_compile_image_prompt_missing_axes_when_required_returns_409(
    test_db,
    temp_db_path,
    db_with_users,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Compile endpoint should reject empty axes payload when manifest requires axes."""
    world_id = database.DEFAULT_WORLD_ID
    world_root = tmp_path / world_id
    policies = world_root / "policies"
    _write_manifest_compile_policy_package(policies)

    world = _build_prompt_world(world_root)
    world.world_id = world_id
    engine = _build_lab_engine(world, world_id=world_id)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        _import_world_policy_files_into_canonical_db(
            monkeypatch=monkeypatch,
            world_root=world_root,
            world_id=world_id,
        )
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/compile-image-prompt",
            json={
                "session_id": sid,
                "world_id": world_id,
                "species": "goblin",
                "gender": "male",
                "axes": {},
            },
        )

    assert resp.status_code == 409
    assert "entity.axes" in resp.json()["detail"]


@pytest.mark.api
def test_compile_image_prompt_policy_hash_changes_on_block_content_change(
    test_db,
    temp_db_path,
    db_with_users,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Policy hash should change when referenced block content changes at same path."""
    world_id = database.DEFAULT_WORLD_ID
    world_root = tmp_path / world_id
    policies = world_root / "policies"
    _write_manifest_compile_policy_package(policies)

    world = _build_prompt_world(world_root)
    world.world_id = world_id
    engine = _build_lab_engine(world, world_id=world_id)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    payload = {
        "world_id": world_id,
        "species": "goblin",
        "gender": "male",
        "axes": {
            "wealth": {"label": "modest", "score": 0.33},
            "demeanor": {"label": "alert", "score": 0.70},
        },
        "world_context": ["coastal"],
        "occupation_signals": ["manual_labour"],
    }

    with use_test_database(temp_db_path):
        _import_world_policy_files_into_canonical_db(
            monkeypatch=monkeypatch,
            world_root=world_root,
            world_id=world_id,
        )
        sid = _login(client, "testadmin")
        resp_one = client.post(
            "/api/lab/compile-image-prompt",
            json={"session_id": sid, **payload},
        )
        assert resp_one.status_code == 200
        policy_hash_one = resp_one.json()["policy_hash"]

        # Mutate active canonical DB clothing block content and verify hash changes.
        updated_variant = policy_service.upsert_policy_variant(
            policy_id="clothing_block:image.blocks.clothing.activity:general_labour",
            variant="v1",
            schema_version="1.0",
            policy_version=1,
            status="active",
            content={"text": "Garments suggest sustained manual work with reinforced seams."},
            updated_by="test-editor",
        )
        assert updated_variant["policy_id"].startswith("clothing_block:")

        resp_two = client.post(
            "/api/lab/compile-image-prompt",
            json={"session_id": sid, **payload},
        )
        assert resp_two.status_code == 200
        policy_hash_two = resp_two.json()["policy_hash"]

    assert policy_hash_one != policy_hash_two


# ── prompt draft routes ──────────────────────────────────────────────────────


@pytest.mark.api
def test_world_prompt_draft_create_writes_file(test_db, temp_db_path, db_with_users, tmp_path):
    """Prompt-draft create writes a create-only text draft under policies/drafts."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt {{profile_summary}}", encoding="utf-8")

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts",
            json={
                "session_id": sid,
                "draft_name": "ic_prompt_variant",
                "content": "Draft prompt {{profile_summary}}\nDelivery Mode: {{channel}}\n",
                "based_on_name": "ic_prompt",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "ic_prompt_variant"
    assert data["origin_path"] == "policies/drafts/ic_prompt_variant.txt"
    assert data["world_id"] == "test_world"
    assert (policies / "drafts" / "ic_prompt_variant.txt").read_text(encoding="utf-8") == (
        "Draft prompt {{profile_summary}}\nDelivery Mode: {{channel}}\n"
    )


@pytest.mark.api
def test_world_prompt_draft_create_rejects_invalid_name(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft create rejects names outside the safe draft pattern."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt", encoding="utf-8")

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts",
            json={
                "session_id": sid,
                "draft_name": "Bad Name",
                "content": "Draft prompt",
            },
        )

    assert resp.status_code == 400
    assert "draft names must use lowercase letters" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_prompt_draft_create_rejects_existing_canonical_name(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft create rejects names that collide with canonical prompt files."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt", encoding="utf-8")

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts",
            json={
                "session_id": sid,
                "draft_name": "ic_prompt",
                "content": "Draft prompt",
            },
        )

    assert resp.status_code == 409


@pytest.mark.api
def test_world_prompt_draft_create_returns_404_when_world_missing(
    test_db, temp_db_path, db_with_users
):
    """Prompt-draft create returns 404 when the target world is inactive."""
    engine = _build_lab_engine(_build_world_with_service(_make_mock_service()))
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/missing_world/drafts",
            json={
                "session_id": sid,
                "draft_name": "missing_world_prompt",
                "content": "Draft prompt",
            },
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_draft_create_returns_404_when_translation_disabled(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft create returns 404 when translation is disabled for the world."""
    policies = tmp_path / "policies"
    policies.mkdir()
    world = _build_world_with_service(None)
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts",
            json={"session_id": sid, "draft_name": "disabled_prompt", "content": "Draft prompt"},
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_draft_create_returns_404_when_world_root_missing(
    test_db, temp_db_path, db_with_users
):
    """Prompt-draft create returns 404 when prompt files are unavailable."""
    world = _build_world_with_service(_make_mock_service())
    world._world_root = None
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts",
            json={
                "session_id": sid,
                "draft_name": "missing_root_prompt",
                "content": "Draft prompt",
            },
        )

    assert resp.status_code == 404
    assert "prompt files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_prompt_draft_create_returns_404_when_policies_dir_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft create returns 404 when the policies directory is missing."""
    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts",
            json={"session_id": sid, "draft_name": "no_policies_prompt", "content": "Draft prompt"},
        )

    assert resp.status_code == 404
    assert "prompt files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_prompt_drafts_lists_saved_drafts(test_db, temp_db_path, db_with_users, tmp_path):
    """Prompt-draft listing returns saved text drafts for one world."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt", encoding="utf-8")
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "ic_prompt_variant.txt").write_text("Draft prompt one", encoding="utf-8")
    (drafts / "ic_prompt_variant_two.txt").write_text("Draft prompt two", encoding="utf-8")

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world/drafts?session_id={sid}")

    assert resp.status_code == 200
    drafts_data = resp.json()["drafts"]
    assert [entry["name"] for entry in drafts_data] == [
        "ic_prompt_variant",
        "ic_prompt_variant_two",
    ]


@pytest.mark.api
def test_world_prompt_drafts_returns_empty_when_drafts_dir_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft listing returns an empty list when no drafts directory exists."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt", encoding="utf-8")

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world/drafts?session_id={sid}")

    assert resp.status_code == 200
    assert resp.json()["drafts"] == []


@pytest.mark.api
def test_world_prompt_drafts_skips_unreadable_files(test_db, temp_db_path, db_with_users, tmp_path):
    """Prompt-draft listing skips drafts that raise OSError while being read."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt", encoding="utf-8")
    drafts = policies / "drafts"
    drafts.mkdir()
    good_draft = drafts / "good_prompt.txt"
    bad_draft = drafts / "bad_prompt.txt"
    good_draft.write_text("readable", encoding="utf-8")
    bad_draft.write_text("broken", encoding="utf-8")

    original_read_text = Path.read_text

    def _read_text(self: Path, *args, **kwargs):
        if self == bad_draft:
            raise OSError("unreadable")
        return original_read_text(self, *args, **kwargs)

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with patch.object(Path, "read_text", _read_text):
        with use_test_database(temp_db_path):
            sid = _login(client, "testadmin")
            resp = client.get(f"/api/lab/world-prompts/test_world/drafts?session_id={sid}")

    assert resp.status_code == 200
    assert [entry["name"] for entry in resp.json()["drafts"]] == ["good_prompt"]


@pytest.mark.api
def test_world_prompt_drafts_returns_404_when_world_missing(test_db, temp_db_path, db_with_users):
    """Prompt-draft listing returns 404 when the target world is inactive."""
    engine = _build_lab_engine(_build_world_with_service(_make_mock_service()))
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/missing_world/drafts?session_id={sid}")

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_drafts_returns_404_when_translation_disabled(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft listing returns 404 when translation is disabled for the world."""
    policies = tmp_path / "policies"
    policies.mkdir()
    world = _build_world_with_service(None)
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world/drafts?session_id={sid}")

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_drafts_returns_404_when_world_root_missing(
    test_db, temp_db_path, db_with_users
):
    """Prompt-draft listing returns 404 when prompt files are unavailable."""
    world = _build_world_with_service(_make_mock_service())
    world._world_root = None
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world/drafts?session_id={sid}")

    assert resp.status_code == 404
    assert "prompt files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_prompt_drafts_returns_404_when_policies_dir_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft listing returns 404 when the policies directory is missing."""
    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world/drafts?session_id={sid}")

    assert resp.status_code == 404
    assert "prompt files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_prompt_draft_load_returns_document(test_db, temp_db_path, db_with_users, tmp_path):
    """Prompt-draft load returns the saved prompt text for one world."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt", encoding="utf-8")
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "ic_prompt_variant.txt").write_text(
        "Draft prompt {{profile_summary}}\nDelivery Mode: {{channel}}\n",
        encoding="utf-8",
    )

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-prompts/test_world/drafts/ic_prompt_variant?session_id={sid}"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "ic_prompt_variant"
    assert data["origin_path"] == "policies/drafts/ic_prompt_variant.txt"
    assert data["content"].startswith("Draft prompt")


@pytest.mark.api
def test_world_prompt_draft_load_rejects_invalid_name(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft load rejects names outside the safe draft pattern."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt", encoding="utf-8")

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-prompts/test_world/drafts/Bad Name?session_id={sid}")

    assert resp.status_code == 400


@pytest.mark.api
def test_world_prompt_draft_load_returns_404_when_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft load returns 404 when the named draft does not exist."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt", encoding="utf-8")

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-prompts/test_world/drafts/no_such_prompt?session_id={sid}"
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_draft_load_returns_500_when_unreadable(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft load returns 500 when the draft file cannot be read."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt", encoding="utf-8")
    drafts = policies / "drafts"
    drafts.mkdir()
    target = drafts / "ic_prompt_variant.txt"
    target.write_text("broken", encoding="utf-8")

    original_read_text = Path.read_text

    def _read_text(self: Path, *args, **kwargs):
        if self == target:
            raise OSError("unreadable")
        return original_read_text(self, *args, **kwargs)

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with patch.object(Path, "read_text", _read_text):
        with use_test_database(temp_db_path):
            sid = _login(client, "testadmin")
            resp = client.get(
                f"/api/lab/world-prompts/test_world/drafts/ic_prompt_variant?session_id={sid}"
            )

    assert resp.status_code == 500


@pytest.mark.api
def test_world_prompt_draft_load_returns_404_when_world_missing(
    test_db, temp_db_path, db_with_users
):
    """Prompt-draft load returns 404 when the target world is inactive."""
    engine = _build_lab_engine(_build_world_with_service(_make_mock_service()))
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-prompts/missing_world/drafts/ic_prompt_variant?session_id={sid}"
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_draft_load_returns_404_when_translation_disabled(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft load returns 404 when translation is disabled for the world."""
    policies = tmp_path / "policies"
    policies.mkdir()
    world = _build_world_with_service(None)
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-prompts/test_world/drafts/ic_prompt_variant?session_id={sid}"
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_draft_load_returns_404_when_world_root_missing(
    test_db, temp_db_path, db_with_users
):
    """Prompt-draft load returns 404 when prompt files are unavailable."""
    world = _build_world_with_service(_make_mock_service())
    world._world_root = None
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-prompts/test_world/drafts/ic_prompt_variant?session_id={sid}"
        )

    assert resp.status_code == 404
    assert "prompt files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_prompt_draft_load_returns_404_when_policies_dir_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft load returns 404 when the policies directory is missing."""
    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-prompts/test_world/drafts/ic_prompt_variant?session_id={sid}"
        )

    assert resp.status_code == 404
    assert "prompt files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_prompt_draft_promote_creates_canonical_file_and_activates_it(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft promotion creates a new canonical file and makes it active."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text(
        "Active prompt {{profile_summary}}\n",
        encoding="utf-8",
    )
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "ic_prompt_variant.txt").write_text(
        "Promoted prompt {{profile_summary}}\nDelivery Mode: {{channel}}\n",
        encoding="utf-8",
    )
    (tmp_path / "world.json").write_text(
        "{\n"
        '  "translation_layer": {\n'
        '    "enabled": true,\n'
        '    "prompt_template_path": "policies/ic_prompt.txt"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts/ic_prompt_variant/promote",
            json={"session_id": sid, "target_name": "ic_prompt_v2"},
        )
        prompts_resp = client.get(f"/api/lab/world-prompts/test_world?session_id={sid}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "ic_prompt_variant"
    assert data["canonical_name"] == "ic_prompt_v2"
    assert data["canonical_path"] == "policies/ic_prompt_v2.txt"
    assert data["active_prompt_path"] == "policies/ic_prompt_v2.txt"
    assert (policies / "ic_prompt_v2.txt").read_text(encoding="utf-8") == (
        "Promoted prompt {{profile_summary}}\nDelivery Mode: {{channel}}\n"
    )
    assert '"prompt_template_path": "policies/ic_prompt_v2.txt"' in (
        tmp_path / "world.json"
    ).read_text(encoding="utf-8")
    active = [entry for entry in prompts_resp.json()["prompts"] if entry["is_active"]]
    assert [entry["filename"] for entry in active] == ["ic_prompt_v2.txt"]


@pytest.mark.api
def test_world_prompt_draft_promote_rejects_invalid_draft_name(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft promotion rejects source names outside the safe draft pattern."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt\n", encoding="utf-8")
    (tmp_path / "world.json").write_text(
        '{"translation_layer":{"enabled":true,"prompt_template_path":"policies/ic_prompt.txt"}}\n',
        encoding="utf-8",
    )

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts/Bad Name/promote",
            json={"session_id": sid, "target_name": "ic_prompt_v2"},
        )

    assert resp.status_code == 400


@pytest.mark.api
def test_world_prompt_draft_promote_rejects_invalid_target_name(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft promotion rejects canonical target names outside the safe pattern."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt\n", encoding="utf-8")
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "ic_prompt_variant.txt").write_text("Prompt\n", encoding="utf-8")
    (tmp_path / "world.json").write_text(
        '{"translation_layer":{"enabled":true,"prompt_template_path":"policies/ic_prompt.txt"}}\n',
        encoding="utf-8",
    )

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts/ic_prompt_variant/promote",
            json={"session_id": sid, "target_name": "Bad Name"},
        )

    assert resp.status_code == 400


@pytest.mark.api
def test_world_prompt_draft_promote_returns_404_when_world_missing(
    test_db, temp_db_path, db_with_users
):
    """Prompt-draft promotion returns 404 when the target world is inactive."""
    engine = _build_lab_engine(_build_world_with_service(_make_mock_service()))
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/missing_world/drafts/ic_prompt_variant/promote",
            json={"session_id": sid, "target_name": "ic_prompt_v2"},
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_draft_promote_returns_404_when_translation_disabled(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft promotion returns 404 when translation is disabled for the world."""
    policies = tmp_path / "policies"
    policies.mkdir()
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "ic_prompt_variant.txt").write_text("Prompt\n", encoding="utf-8")
    world = _build_world_with_service(None)
    world._world_root = tmp_path
    world._world_json_path = tmp_path / "world.json"
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts/ic_prompt_variant/promote",
            json={"session_id": sid, "target_name": "ic_prompt_v2"},
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_draft_promote_returns_404_when_world_root_missing(
    test_db, temp_db_path, db_with_users
):
    """Prompt-draft promotion returns 404 when prompt files are unavailable."""
    world = _build_world_with_service(_make_mock_service())
    world._world_root = None
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts/ic_prompt_variant/promote",
            json={"session_id": sid, "target_name": "ic_prompt_v2"},
        )

    assert resp.status_code == 404
    assert "prompt files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_prompt_draft_promote_returns_404_when_policies_dir_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft promotion returns 404 when the policies directory is missing."""
    (tmp_path / "world.json").write_text(
        '{"translation_layer":{"enabled":true,"prompt_template_path":"policies/ic_prompt.txt"}}\n',
        encoding="utf-8",
    )
    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts/ic_prompt_variant/promote",
            json={"session_id": sid, "target_name": "ic_prompt_v2"},
        )

    assert resp.status_code == 404
    assert "prompt files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_prompt_draft_promote_returns_404_when_draft_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft promotion returns 404 when the named draft does not exist."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt\n", encoding="utf-8")
    (tmp_path / "world.json").write_text(
        '{"translation_layer":{"enabled":true,"prompt_template_path":"policies/ic_prompt.txt"}}\n',
        encoding="utf-8",
    )
    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts/no_such_prompt/promote",
            json={"session_id": sid, "target_name": "ic_prompt_v2"},
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_prompt_draft_promote_returns_409_when_target_exists(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft promotion rejects canonical target collisions."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt\n", encoding="utf-8")
    (policies / "ic_prompt_v2.txt").write_text("Existing canonical\n", encoding="utf-8")
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "ic_prompt_variant.txt").write_text("Prompt\n", encoding="utf-8")
    (tmp_path / "world.json").write_text(
        '{"translation_layer":{"enabled":true,"prompt_template_path":"policies/ic_prompt.txt"}}\n',
        encoding="utf-8",
    )
    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts/ic_prompt_variant/promote",
            json={"session_id": sid, "target_name": "ic_prompt_v2"},
        )

    assert resp.status_code == 409


@pytest.mark.api
def test_world_prompt_draft_promote_returns_404_when_world_config_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Prompt-draft promotion returns 404 when world.json is unavailable."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "ic_prompt.txt").write_text("Active prompt\n", encoding="utf-8")
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "ic_prompt_variant.txt").write_text("Prompt\n", encoding="utf-8")

    world = _build_prompt_world(tmp_path)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-prompts/test_world/drafts/ic_prompt_variant/promote",
            json={"session_id": sid, "target_name": "ic_prompt_v2"},
        )

    assert resp.status_code == 404
    assert "world config unavailable" in resp.json()["detail"].lower()


# ── GET /api/lab/world-policy-bundle/{world_id} ─────────────────────────────


@pytest.mark.api
def test_world_policy_bundle_returns_normalized_bundle(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle endpoint returns the canonical policy package as normalized JSON."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-policy-bundle/test_world?session_id={sid}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["world_id"] == "test_world"
    assert data["version"] == "0.1.0"
    assert data["source_files"] == [
        "policies/axis/axes.yaml",
        "policies/axis/thresholds.yaml",
        "policies/axis/resolution.yaml",
    ]
    assert data["axes_order"] == ["demeanor"]
    assert data["axes"]["demeanor"]["ordering"] == ["timid", "proud"]
    assert data["chat_rules"]["axes"]["demeanor"]["resolver"] == "dominance_shift"


@pytest.mark.api
def test_world_policy_bundle_unknown_world_returns_404(lab_client, db_with_users, temp_db_path):
    """Policy-bundle endpoint returns 404 for an unknown world_id."""
    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        resp = lab_client.get(f"/api/lab/world-policy-bundle/no_such_world?session_id={sid}")
    assert resp.status_code == 404


@pytest.mark.api
def test_world_policy_bundle_missing_files_returns_404(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle endpoint returns 404 when the world has no policy package."""
    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-policy-bundle/test_world?session_id={sid}")

    assert resp.status_code == 404


@pytest.mark.api
def test_world_policy_bundle_draft_create_writes_json_file(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft endpoint writes a create-only JSON draft under policies/drafts."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts",
            json={
                "session_id": sid,
                "draft_name": "test_world_bundle_alt",
                "content": {
                    "world_id": "test_world",
                    "version": "0.2.0",
                    "source": "lab draft",
                    "policy_hash": None,
                    "axes_order": ["demeanor"],
                    "axes": {
                        "demeanor": {
                            "group": "character",
                            "ordering": ["timid", "proud"],
                            "thresholds": [
                                {"label": "timid", "min": 0.0, "max": 0.49},
                                {"label": "proud", "min": 0.5, "max": 1.0},
                            ],
                        }
                    },
                    "chat_rules": {
                        "channel_multipliers": {
                            "say": 1.0,
                            "yell": 1.5,
                            "whisper": 0.5,
                        },
                        "min_gap_threshold": 0.05,
                        "axes": {
                            "demeanor": {
                                "resolver": "dominance_shift",
                                "base_magnitude": 0.04,
                            }
                        },
                    },
                },
                "based_on_name": "test_world_policy_bundle",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["origin_path"] == "policies/drafts/test_world_bundle_alt.json"
    draft_file = tmp_path / "policies" / "drafts" / "test_world_bundle_alt.json"
    assert draft_file.exists()
    assert '"world_id": "test_world"' in draft_file.read_text(encoding="utf-8")


@pytest.mark.api
def test_world_policy_bundle_draft_create_rejects_name_collision(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft endpoint refuses to overwrite an existing draft file."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "test_world_bundle_alt.json").write_text("{}\n", encoding="utf-8")

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts",
            json={
                "session_id": sid,
                "draft_name": "test_world_bundle_alt",
                "content": {
                    "world_id": "test_world",
                    "version": "0.2.0",
                    "source": "lab draft",
                    "policy_hash": None,
                    "axes_order": ["demeanor"],
                    "axes": {
                        "demeanor": {
                            "group": "character",
                            "ordering": ["timid", "proud"],
                            "thresholds": [
                                {"label": "timid", "min": 0.0, "max": 0.49},
                                {"label": "proud", "min": 0.5, "max": 1.0},
                            ],
                        }
                    },
                    "chat_rules": {
                        "channel_multipliers": {
                            "say": 1.0,
                            "yell": 1.5,
                            "whisper": 0.5,
                        },
                        "min_gap_threshold": 0.05,
                        "axes": {
                            "demeanor": {
                                "resolver": "dominance_shift",
                                "base_magnitude": 0.04,
                            }
                        },
                    },
                },
            },
        )

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


@pytest.mark.api
def test_world_policy_bundle_drafts_lists_saved_drafts(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft listing returns saved JSON drafts for one world."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "test_world_bundle_alt.json").write_text(
        '{"world_id":"test_world","version":"0.2.0","source":"lab draft","policy_hash":null,"axes_order":["demeanor"],"axes":{"demeanor":{"group":"character","ordering":["timid","proud"],"thresholds":[{"label":"timid","min":0.0,"max":0.49},{"label":"proud","min":0.5,"max":1.0}]}},"chat_rules":{"channel_multipliers":{"say":1.0,"yell":1.5,"whisper":0.5},"min_gap_threshold":0.05,"axes":{"demeanor":{"resolver":"dominance_shift","base_magnitude":0.04}}}}\n',
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-policy-bundle/test_world/drafts?session_id={sid}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["world_id"] == "test_world"
    assert data["drafts"][0]["name"] == "test_world_bundle_alt"


@pytest.mark.api
def test_world_policy_bundle_draft_loads_saved_draft(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft load returns one saved JSON draft document."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "test_world_bundle_alt.json").write_text(
        '{"world_id":"test_world","version":"0.2.0","source":"lab draft","policy_hash":null,"axes_order":["demeanor"],"axes":{"demeanor":{"group":"character","ordering":["timid","proud"],"thresholds":[{"label":"timid","min":0.0,"max":0.49},{"label":"proud","min":0.5,"max":1.0}]}},"chat_rules":{"channel_multipliers":{"say":1.0,"yell":1.5,"whisper":0.5},"min_gap_threshold":0.05,"axes":{"demeanor":{"resolver":"dominance_shift","base_magnitude":0.04}}}}\n',
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-policy-bundle/test_world/drafts/test_world_bundle_alt?session_id={sid}"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test_world_bundle_alt"
    assert data["content"]["world_id"] == "test_world"


@pytest.mark.api
def test_world_policy_bundle_draft_promote_rewrites_canonical_files(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle promotion rewrites canonical YAML and reloads the axis engine."""

    policies = tmp_path / "policies"
    _write_minimal_policy_package(policies)
    _write_policy_bundle_draft(policies)
    (tmp_path / "world.json").write_text(
        "{\n"
        '  "translation_layer": {\n'
        '    "enabled": true,\n'
        '    "active_axes": ["demeanor"]\n'
        "  },\n"
        '  "axis_engine": {"enabled": true}\n'
        "}\n",
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    world._world_json_path = tmp_path / "world.json"
    world._axis_engine = None
    cast(Any, world).reload_axis_engine = lambda _world_data: setattr(
        world, "_axis_engine", MagicMock()
    )
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts/test_world_bundle_alt/promote",
            json={"session_id": sid},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test_world_bundle_alt"
    assert data["canonical_name"] == "test_world_policy_bundle"
    assert data["source_files"] == [
        "policies/axis/axes.yaml",
        "policies/axis/thresholds.yaml",
        "policies/axis/resolution.yaml",
    ]
    assert data["version"] == "0.2.0"
    assert data["policy_hash"]

    axes_payload = yaml.safe_load((policies / "axis" / "axes.yaml").read_text(encoding="utf-8"))
    thresholds_payload = yaml.safe_load(
        (policies / "axis" / "thresholds.yaml").read_text(encoding="utf-8")
    )
    resolution_payload = yaml.safe_load(
        (policies / "axis" / "resolution.yaml").read_text(encoding="utf-8")
    )
    assert axes_payload["version"] == "0.2.0"
    assert axes_payload["source"] == "lab draft"
    assert axes_payload["axes"]["demeanor"]["ordering"]["values"] == ["timid", "proud"]
    assert thresholds_payload["axes"]["demeanor"]["values"]["proud"]["min"] == 0.45
    assert resolution_payload["interactions"]["chat"]["axes"]["demeanor"]["base_magnitude"] == 0.04
    assert world.get_axis_engine() is not None


@pytest.mark.api
def test_world_policy_bundle_draft_promote_rejects_invalid_name(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle promotion rejects source names outside the safe draft pattern."""

    policies = tmp_path / "policies"
    _write_minimal_policy_package(policies)
    (tmp_path / "world.json").write_text('{"axis_engine":{"enabled":true}}\n', encoding="utf-8")

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    world._world_json_path = tmp_path / "world.json"
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts/Bad Name/promote",
            json={"session_id": sid},
        )

    assert resp.status_code == 400


@pytest.mark.api
def test_world_policy_bundle_draft_promote_returns_404_when_world_missing(
    test_db, temp_db_path, db_with_users
):
    """Policy-bundle promotion returns 404 when the target world is inactive."""

    engine = _build_lab_engine(_build_world_with_service(_make_mock_service()))
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/missing_world/drafts/test_world_bundle_alt/promote",
            json={"session_id": sid},
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_policy_bundle_draft_promote_returns_404_when_world_root_missing(
    test_db, temp_db_path, db_with_users
):
    """Policy-bundle promotion returns 404 when policy files are unavailable."""

    world = _build_world_with_service(_make_mock_service())
    world._world_root = None
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts/test_world_bundle_alt/promote",
            json={"session_id": sid},
        )

    assert resp.status_code == 404
    assert "axis policy files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_policy_bundle_draft_promote_returns_404_when_draft_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle promotion returns 404 when the named draft does not exist."""

    policies = tmp_path / "policies"
    _write_minimal_policy_package(policies)
    (tmp_path / "world.json").write_text('{"axis_engine":{"enabled":true}}\n', encoding="utf-8")

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    world._world_json_path = tmp_path / "world.json"
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts/no_such_bundle/promote",
            json={"session_id": sid},
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_policy_bundle_draft_promote_returns_404_when_world_config_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle promotion returns 404 when world.json is unavailable."""

    policies = tmp_path / "policies"
    _write_minimal_policy_package(policies)
    _write_policy_bundle_draft(policies)

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    world._world_json_path = tmp_path / "world.json"
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts/test_world_bundle_alt/promote",
            json={"session_id": sid},
        )

    assert resp.status_code == 404
    assert "world config unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_policy_bundle_draft_promote_returns_409_when_world_mismatches(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle promotion rejects drafts saved for another world."""

    policies = tmp_path / "policies"
    _write_minimal_policy_package(policies)
    _write_policy_bundle_draft(policies, world_id="daily_undertaking")
    (tmp_path / "world.json").write_text('{"axis_engine":{"enabled":true}}\n', encoding="utf-8")

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    world._world_json_path = tmp_path / "world.json"
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts/test_world_bundle_alt/promote",
            json={"session_id": sid},
        )

    assert resp.status_code == 409


@pytest.mark.api
def test_world_policy_bundle_draft_promote_returns_409_when_active_axes_would_drift(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle promotion rejects bundles that drop configured active_axes."""

    policies = tmp_path / "policies"
    _write_minimal_policy_package(policies)
    _write_policy_bundle_draft(policies)
    (tmp_path / "world.json").write_text(
        "{\n"
        '  "translation_layer": {"enabled": true, "active_axes": ["health"]},\n'
        '  "axis_engine": {"enabled": true}\n'
        "}\n",
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    world._world_json_path = tmp_path / "world.json"
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts/test_world_bundle_alt/promote",
            json={"session_id": sid},
        )

    assert resp.status_code == 409
    assert "active_axes" in resp.json()["detail"]


@pytest.mark.api
def test_world_policy_bundle_draft_create_rejects_invalid_name(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft endpoint rejects names outside the safe draft pattern."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts",
            json={
                "session_id": sid,
                "draft_name": "Bad Name",
                "content": {
                    "world_id": "test_world",
                    "version": "0.2.0",
                    "source": "lab draft",
                    "policy_hash": None,
                    "axes_order": ["demeanor"],
                    "axes": {
                        "demeanor": {
                            "group": "character",
                            "ordering": ["timid", "proud"],
                            "thresholds": [
                                {"label": "timid", "min": 0.0, "max": 0.49},
                                {"label": "proud", "min": 0.5, "max": 1.0},
                            ],
                        }
                    },
                    "chat_rules": {
                        "channel_multipliers": {"say": 1.0, "yell": 1.5, "whisper": 0.5},
                        "min_gap_threshold": 0.05,
                        "axes": {
                            "demeanor": {"resolver": "dominance_shift", "base_magnitude": 0.04}
                        },
                    },
                },
            },
        )

    assert resp.status_code == 400
    assert "draft names must use lowercase letters" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_policy_bundle_draft_create_rejects_world_mismatch(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft endpoint rejects payloads whose world_id does not match."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts",
            json={
                "session_id": sid,
                "draft_name": "test_world_bundle_alt",
                "content": {
                    "world_id": "other_world",
                    "version": "0.2.0",
                    "source": "lab draft",
                    "policy_hash": None,
                    "axes_order": ["demeanor"],
                    "axes": {
                        "demeanor": {
                            "group": "character",
                            "ordering": ["timid", "proud"],
                            "thresholds": [
                                {"label": "timid", "min": 0.0, "max": 0.49},
                                {"label": "proud", "min": 0.5, "max": 1.0},
                            ],
                        }
                    },
                    "chat_rules": {
                        "channel_multipliers": {"say": 1.0, "yell": 1.5, "whisper": 0.5},
                        "min_gap_threshold": 0.05,
                        "axes": {
                            "demeanor": {"resolver": "dominance_shift", "base_magnitude": 0.04}
                        },
                    },
                },
            },
        )

    assert resp.status_code == 400
    assert "must match the target world_id" in resp.json()["detail"]


@pytest.mark.api
def test_world_policy_bundle_drafts_returns_empty_when_drafts_dir_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft listing returns an empty list when no drafts directory exists."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-policy-bundle/test_world/drafts?session_id={sid}")

    assert resp.status_code == 200
    assert resp.json()["drafts"] == []


@pytest.mark.api
def test_world_policy_bundle_drafts_skips_invalid_and_mismatched_files(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft listing skips invalid JSON files and mismatched-world drafts."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "invalid.json").write_text('{"bad": }\n', encoding="utf-8")
    (drafts / "other_world.json").write_text(
        '{"world_id":"other_world","version":"0.2.0","source":"lab draft","policy_hash":null,"axes_order":["demeanor"],"axes":{"demeanor":{"group":"character","ordering":["timid","proud"],"thresholds":[{"label":"timid","min":0.0,"max":0.49},{"label":"proud","min":0.5,"max":1.0}]}},"chat_rules":{"channel_multipliers":{"say":1.0,"yell":1.5,"whisper":0.5},"min_gap_threshold":0.05,"axes":{"demeanor":{"resolver":"dominance_shift","base_magnitude":0.04}}}}\n',
        encoding="utf-8",
    )
    (drafts / "test_world_bundle_alt.json").write_text(
        '{"world_id":"test_world","version":"0.2.0","source":"lab draft","policy_hash":null,"axes_order":["demeanor"],"axes":{"demeanor":{"group":"character","ordering":["timid","proud"],"thresholds":[{"label":"timid","min":0.0,"max":0.49},{"label":"proud","min":0.5,"max":1.0}]}},"chat_rules":{"channel_multipliers":{"say":1.0,"yell":1.5,"whisper":0.5},"min_gap_threshold":0.05,"axes":{"demeanor":{"resolver":"dominance_shift","base_magnitude":0.04}}}}\n',
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-policy-bundle/test_world/drafts?session_id={sid}")

    assert resp.status_code == 200
    drafts = resp.json()["drafts"]
    assert [entry["name"] for entry in drafts] == ["test_world_bundle_alt"]


@pytest.mark.api
def test_world_policy_bundle_draft_load_rejects_invalid_name(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft load rejects names outside the safe draft pattern."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-policy-bundle/test_world/drafts/Bad Name?session_id={sid}"
        )

    assert resp.status_code == 400


@pytest.mark.api
def test_world_policy_bundle_draft_load_returns_404_when_missing(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft load returns 404 when the requested draft file is absent."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-policy-bundle/test_world/drafts/no_such_draft?session_id={sid}"
        )

    assert resp.status_code == 404


@pytest.mark.api
def test_world_policy_bundle_draft_load_rejects_invalid_file_on_disk(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft load returns 500 when the saved draft file is invalid JSON."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "test_world_bundle_alt.json").write_text('{"bad": }\n', encoding="utf-8")

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-policy-bundle/test_world/drafts/test_world_bundle_alt?session_id={sid}"
        )

    assert resp.status_code == 500
    assert "invalid on disk" in resp.json()["detail"]


@pytest.mark.api
def test_world_policy_bundle_draft_load_rejects_mismatched_world_file(
    test_db, temp_db_path, db_with_users, tmp_path
):
    """Policy-bundle draft load returns 409 when the saved draft belongs to another world."""
    policies = tmp_path / "policies"
    policies.mkdir()
    (_ensure_axis_policy_dir(policies) / "axes.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    group: character\n"
        "    ordering:\n"
        "      type: ordinal\n"
        "      values: [timid, proud]\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "thresholds.yaml").write_text(
        "version: 0.1.0\n"
        "axes:\n"
        "  demeanor:\n"
        "    scale: ordinal\n"
        "    values:\n"
        "      timid: {min: 0.0, max: 0.49}\n"
        "      proud: {min: 0.5, max: 1.0}\n",
        encoding="utf-8",
    )
    (_ensure_axis_policy_dir(policies) / "resolution.yaml").write_text(
        'version: "1.0"\n'
        "interactions:\n"
        "  chat:\n"
        "    channel_multipliers:\n"
        "      say: 1.0\n"
        "      yell: 1.5\n"
        "      whisper: 0.5\n"
        "    min_gap_threshold: 0.05\n"
        "    axes:\n"
        "      demeanor:\n"
        "        resolver: dominance_shift\n"
        "        base_magnitude: 0.03\n",
        encoding="utf-8",
    )
    drafts = policies / "drafts"
    drafts.mkdir()
    (drafts / "test_world_bundle_alt.json").write_text(
        '{"world_id":"other_world","version":"0.2.0","source":"lab draft","policy_hash":null,"axes_order":["demeanor"],"axes":{"demeanor":{"group":"character","ordering":["timid","proud"],"thresholds":[{"label":"timid","min":0.0,"max":0.49},{"label":"proud","min":0.5,"max":1.0}]}},"chat_rules":{"channel_multipliers":{"say":1.0,"yell":1.5,"whisper":0.5},"min_gap_threshold":0.05,"axes":{"demeanor":{"resolver":"dominance_shift","base_magnitude":0.04}}}}\n',
        encoding="utf-8",
    )

    world = _build_world_with_service(_make_mock_service())
    world._world_root = tmp_path
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-policy-bundle/test_world/drafts/test_world_bundle_alt?session_id={sid}"
        )

    assert resp.status_code == 409
    assert "belongs to a different world" in resp.json()["detail"]


@pytest.mark.api
def test_world_policy_bundle_draft_create_returns_404_when_world_missing(
    test_db, temp_db_path, db_with_users
):
    """Policy-bundle draft create returns 404 when the target world is inactive."""
    engine = _build_lab_engine(MagicMock())
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    payload = {
        "world_id": "missing_world",
        "version": "0.2.0",
        "source": "lab draft",
        "policy_hash": None,
        "axes_order": ["demeanor"],
        "axes": {
            "demeanor": {
                "group": "character",
                "ordering": ["timid", "proud"],
                "thresholds": [
                    {"label": "timid", "min": 0.0, "max": 0.49},
                    {"label": "proud", "min": 0.5, "max": 1.0},
                ],
            }
        },
        "chat_rules": {
            "channel_multipliers": {"say": 1.0, "yell": 1.5, "whisper": 0.5},
            "min_gap_threshold": 0.05,
            "axes": {"demeanor": {"resolver": "dominance_shift", "base_magnitude": 0.04}},
        },
    }

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/missing_world/drafts",
            json={"session_id": sid, "draft_name": "missing_world_bundle", "content": payload},
        )

    assert resp.status_code == 404
    assert "missing_world" in resp.json()["detail"]


@pytest.mark.api
def test_world_policy_bundle_draft_create_returns_404_when_world_root_missing(
    test_db, temp_db_path, db_with_users
):
    """Policy-bundle draft create returns 404 when policy files are unavailable."""
    world = _build_world_with_service(_make_mock_service())
    world._world_root = None
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    payload = {
        "world_id": "test_world",
        "version": "0.2.0",
        "source": "lab draft",
        "policy_hash": None,
        "axes_order": ["demeanor"],
        "axes": {
            "demeanor": {
                "group": "character",
                "ordering": ["timid", "proud"],
                "thresholds": [
                    {"label": "timid", "min": 0.0, "max": 0.49},
                    {"label": "proud", "min": 0.5, "max": 1.0},
                ],
            }
        },
        "chat_rules": {
            "channel_multipliers": {"say": 1.0, "yell": 1.5, "whisper": 0.5},
            "min_gap_threshold": 0.05,
            "axes": {"demeanor": {"resolver": "dominance_shift", "base_magnitude": 0.04}},
        },
    }

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.post(
            "/api/lab/world-policy-bundle/test_world/drafts",
            json={"session_id": sid, "draft_name": "test_world_bundle", "content": payload},
        )

    assert resp.status_code == 404
    assert "policy files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_policy_bundle_drafts_returns_404_when_world_missing(
    test_db, temp_db_path, db_with_users
):
    """Policy-bundle draft listing returns 404 when the target world is inactive."""
    engine = _build_lab_engine(MagicMock())
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-policy-bundle/missing_world/drafts?session_id={sid}")

    assert resp.status_code == 404
    assert "missing_world" in resp.json()["detail"]


@pytest.mark.api
def test_world_policy_bundle_drafts_returns_404_when_world_root_missing(
    test_db, temp_db_path, db_with_users
):
    """Policy-bundle draft listing returns 404 when policy files are unavailable."""
    world = _build_world_with_service(_make_mock_service())
    world._world_root = None
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(f"/api/lab/world-policy-bundle/test_world/drafts?session_id={sid}")

    assert resp.status_code == 404
    assert "policy files unavailable" in resp.json()["detail"].lower()


@pytest.mark.api
def test_world_policy_bundle_draft_load_returns_404_when_world_missing(
    test_db, temp_db_path, db_with_users
):
    """Policy-bundle draft load returns 404 when the target world is inactive."""
    engine = _build_lab_engine(MagicMock())
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-policy-bundle/missing_world/drafts/test_world_bundle?session_id={sid}"
        )

    assert resp.status_code == 404
    assert "missing_world" in resp.json()["detail"]


@pytest.mark.api
def test_world_policy_bundle_draft_load_returns_404_when_world_root_missing(
    test_db, temp_db_path, db_with_users
):
    """Policy-bundle draft load returns 404 when policy files are unavailable."""
    world = _build_world_with_service(_make_mock_service())
    world._world_root = None
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        resp = client.get(
            f"/api/lab/world-policy-bundle/test_world/drafts/test_world_bundle?session_id={sid}"
        )

    assert resp.status_code == 404
    assert "policy files unavailable" in resp.json()["detail"].lower()


# ── prompt_template_override in translate ─────────────────────────────────────


@pytest.mark.api
def test_translate_with_prompt_override(test_db, temp_db_path, db_with_users):
    """Translate passes prompt_template_override to translate_with_axes when provided."""
    mock_service = _make_mock_service()
    world = _build_world_with_service(mock_service)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    override_text = "Custom prompt: {{profile_summary}}\nOOC: {{ooc_message}}"
    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        payload = {
            **_TRANSLATE_PAYLOAD,
            "session_id": sid,
            "prompt_template_override": override_text,
        }
        resp = client.post("/api/lab/translate", json=payload)

    assert resp.status_code == 200
    call_kwargs = cast(Any, mock_service).translate_with_axes.call_args
    assert call_kwargs.kwargs["prompt_template_override"] == override_text


@pytest.mark.api
def test_translate_without_prompt_override(test_db, temp_db_path, db_with_users):
    """Translate passes None for prompt_template_override when not provided."""
    mock_service = _make_mock_service()
    world = _build_world_with_service(mock_service)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        payload = {**_TRANSLATE_PAYLOAD, "session_id": sid}
        resp = client.post("/api/lab/translate", json=payload)

    assert resp.status_code == 200
    call_kwargs = cast(Any, mock_service).translate_with_axes.call_args
    assert call_kwargs.kwargs["prompt_template_override"] is None
