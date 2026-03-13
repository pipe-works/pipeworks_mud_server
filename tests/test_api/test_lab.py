"""DB-first tests for retained lab API endpoints (``/api/lab/*``).

This suite intentionally targets only the canonical lab surface that remains
after legacy file-authoring routes were removed:

- ``GET /api/lab/worlds``
- ``GET /api/lab/world-config/{world_id}``
- ``GET /api/lab/world-image-policy-bundle/{world_id}``
- ``POST /api/lab/compile-image-prompt``
- ``POST /api/lab/translate``

Legacy prompt/policy draft routes are asserted as absent (HTTP 404) to ensure
DB-only behavior stays explicit and regressions are caught quickly.
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
from mud_server.db import database
from mud_server.services import policy_service
from mud_server.translation.config import TranslationLayerConfig
from mud_server.translation.service import LabTranslateResult, OOCToICTranslationService
from tests.constants import TEST_PASSWORD

TEST_WORLD_ID = database.DEFAULT_WORLD_ID


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_translation_config(**overrides: Any) -> TranslationLayerConfig:
    """Build a translation config fixture with deterministic lab defaults."""

    data: dict[str, Any] = {
        "enabled": True,
        "model": "gemma2:2b",
        "strict_mode": True,
        "max_output_chars": 280,
        "active_axes": ["demeanor", "wealth"],
        **overrides,
    }
    return TranslationLayerConfig.from_dict(data, world_root=Path("/tmp/lab-world-root"))


def _make_mock_service(result: LabTranslateResult | None = None) -> OOCToICTranslationService:
    """Return a mocked translation service with one canned response payload."""

    service = MagicMock(spec=OOCToICTranslationService)
    service.config = _make_translation_config()
    if result is None:
        result = LabTranslateResult(
            ic_text="I must find another way out.",
            status="success",
            profile_summary="Character: Lab Subject\nDemeanor: timid (0.07)",
            rendered_prompt="<rendered system prompt>",
            prompt_template="<raw template>",
        )
    service.translate_with_axes.return_value = result
    return service


def _build_world_with_service(
    service: OOCToICTranslationService | None,
    *,
    world_id: str = TEST_WORLD_ID,
    world_name: str = "Test World",
    world_root: Path | None = None,
) -> World:
    """Build one lightweight ``World`` object without filesystem loading."""

    with patch.object(World, "_load_world", lambda self: None):
        world = World()

    world.world_name = world_name
    world.world_id = world_id
    world._translation_service = service
    world._world_root = world_root
    return world


def _build_lab_engine(
    world: World,
    *,
    world_id: str = TEST_WORLD_ID,
    world_name: str = "Test World",
) -> GameEngine:
    """Build one mock ``GameEngine`` registry exposing exactly one world."""

    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
        engine_any = cast(Any, engine)

    def _get_world(wid: str) -> World:
        if wid == world_id:
            return world
        raise ValueError(f"Unknown world: {wid!r}")

    engine_any.world_registry = SimpleNamespace(
        get_world=_get_world,
        list_worlds=lambda: [{"world_id": world_id, "name": world_name, "is_active": True}],
    )
    return engine


def _login(client: TestClient, username: str) -> str:
    """Log in with test credentials and return the authenticated session id."""

    response = client.post("/login", json={"username": username, "password": TEST_PASSWORD})
    assert response.status_code == 200, f"Login failed for {username}: {response.text}"
    return str(response.json()["session_id"])


def _upsert_and_activate(
    *,
    scope: policy_service.ActivationScope,
    policy_id: str,
    variant: str,
    content: dict[str, Any],
    updated_by: str = "test-seed",
    policy_version: int = 1,
) -> None:
    """Create/update one canonical policy variant and activate it for test scope."""

    policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant=variant,
        schema_version="1.0",
        policy_version=policy_version,
        status="active",
        content=content,
        updated_by=updated_by,
    )
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=policy_id,
        variant=variant,
        activated_by=updated_by,
    )


def _seed_image_policy_contract(world_id: str = TEST_WORLD_ID) -> None:
    """Seed one full DB-first image policy contract for compile/bundle tests."""

    scope = policy_service.ActivationScope(world_id=world_id, client_profile="")

    _upsert_and_activate(
        scope=scope,
        policy_id=f"manifest_bundle:world.manifests:{world_id}",
        variant="v1",
        content={
            "manifest": {
                "policy_schema": "pipeworks_policy_v1",
                "policy_bundle": {"id": "pipeworks_web_default", "version": 1},
                "axis": {"active_bundle": {"id": "axis_core_v1", "version": 1}},
                "image": {
                    "descriptor_layer": {
                        "id": "id_card_v1",
                        "version": 1,
                        "path": "policies/image/descriptor_layers/id_card_v1.txt",
                    },
                    "tone_profile": {
                        "id": "ledger_engraving_v1",
                        "version": 1,
                        "path": "policies/image/tone_profiles/ledger_engraving_v1.json",
                    },
                    "registries": {
                        "species": "policies/image/registries/species_registry.yaml",
                        "clothing": "policies/image/registries/clothing_registry.yaml",
                    },
                    "composition": {
                        "order": [
                            "species_canon_block",
                            "descriptor_layer_output",
                            "clothing_block",
                            "tone_profile_block",
                        ],
                        "required_runtime_inputs": [
                            "entity.identity.gender",
                            "entity.species",
                            "entity.axes",
                        ],
                    },
                },
            }
        },
    )

    _upsert_and_activate(
        scope=scope,
        policy_id="axis_bundle:axis.bundles:axis_core_v1",
        variant="v1",
        content={
            "axes": {"demeanor": {"ordering": {"values": ["timid", "proud"]}}},
            "thresholds": {
                "axes": {
                    "demeanor": {
                        "values": {
                            "timid": {"min": 0.0, "max": 0.49},
                            "proud": {"min": 0.5, "max": 1.0},
                        }
                    }
                }
            },
            "resolution": {"interactions": {"chat": {"axes": {}}}},
        },
    )

    _upsert_and_activate(
        scope=scope,
        policy_id="tone_profile:image.tone_profiles:ledger_engraving",
        variant="v1",
        content={"prompt_block": "Muted sepia with etched ledger-line textures."},
    )

    _upsert_and_activate(
        scope=scope,
        policy_id="species_block:image.blocks.species:goblin",
        variant="v1",
        content={"text": "Pipe-works goblin canonical species descriptor."},
    )
    _upsert_and_activate(
        scope=scope,
        policy_id="clothing_block:image.blocks.clothing.environment:coastal",
        variant="v1",
        content={"text": "Coastal garments suitable for wet weather."},
    )
    _upsert_and_activate(
        scope=scope,
        policy_id="clothing_block:image.blocks.clothing.activity:general_labour",
        variant="v1",
        content={"text": "Functional clothing for manual labour."},
    )
    _upsert_and_activate(
        scope=scope,
        policy_id="clothing_block:image.blocks.clothing.wealth:modest",
        variant="v1",
        content={"text": "Modest, durable, and well-maintained materials."},
    )
    _upsert_and_activate(
        scope=scope,
        policy_id="descriptor_layer:image.descriptors:id_card",
        variant="v1",
        content={
            "text": "engraved portrait descriptor layer",
            "references": [
                {
                    "policy_id": "species_block:image.blocks.species:goblin",
                    "variant": "v1",
                },
                {
                    "policy_id": "tone_profile:image.tone_profiles:ledger_engraving",
                    "variant": "v1",
                },
            ],
        },
    )

    _upsert_and_activate(
        scope=scope,
        policy_id="registry:image.registries:species_registry",
        variant="v1",
        content={
            "registry": {"id": "species_registry", "version": 1, "kind": "species"},
            "references": [
                {
                    "policy_id": "species_block:image.blocks.species:goblin",
                    "variant": "v1",
                }
            ],
            "entries": [
                {
                    "id": "goblin_pipeworks_v1",
                    "version": 1,
                    "block_type": "species",
                    "status": "active",
                    "render_priority": 100,
                    "compatible_species": ["goblin"],
                    "compatible_genders": ["male", "female"],
                    "selection_rules": {"when": {"species_any": ["goblin"]}},
                    "policy_ref": {
                        "policy_id": "species_block:image.blocks.species:goblin",
                        "variant": "v1",
                    },
                }
            ],
        },
    )
    _upsert_and_activate(
        scope=scope,
        policy_id="registry:image.registries:clothing_registry",
        variant="v1",
        content={
            "registry": {"id": "clothing_registry", "version": 1, "kind": "clothing"},
            "references": [
                {
                    "policy_id": "clothing_block:image.blocks.clothing.environment:coastal",
                    "variant": "v1",
                },
                {
                    "policy_id": "clothing_block:image.blocks.clothing.activity:general_labour",
                    "variant": "v1",
                },
                {
                    "policy_id": "clothing_block:image.blocks.clothing.wealth:modest",
                    "variant": "v1",
                },
            ],
            "composition_contract": {"slots": ["environment", "activity", "wealth"]},
            "defaults": {"profile_id": "clothing_default_v1"},
            "slots": {
                "environment": [
                    {
                        "id": "clothing_environment_coastal_v1",
                        "version": 1,
                        "block_type": "clothing_fragment",
                        "status": "active",
                        "render_priority": 90,
                        "compatible_genders": ["male", "female"],
                        "selection_rules": {"when": {"world_context_any": ["coastal"]}},
                        "policy_ref": {
                            "policy_id": "clothing_block:image.blocks.clothing.environment:coastal",
                            "variant": "v1",
                        },
                    }
                ],
                "activity": [
                    {
                        "id": "clothing_activity_general_labour_v1",
                        "version": 1,
                        "block_type": "clothing_fragment",
                        "status": "active",
                        "render_priority": 80,
                        "compatible_genders": ["male", "female"],
                        "selection_rules": {"when": {"occupation_signal_any": ["manual_labour"]}},
                        "policy_ref": {
                            "policy_id": "clothing_block:image.blocks.clothing.activity:general_labour",
                            "variant": "v1",
                        },
                    }
                ],
                "wealth": [
                    {
                        "id": "clothing_wealth_modest_v1",
                        "version": 1,
                        "block_type": "clothing_fragment",
                        "status": "active",
                        "render_priority": 70,
                        "compatible_genders": ["male", "female"],
                        "selection_rules": {"when": {"axis_labels": {"wealth_any": ["modest"]}}},
                        "policy_ref": {
                            "policy_id": "clothing_block:image.blocks.clothing.wealth:modest",
                            "variant": "v1",
                        },
                    }
                ],
            },
        },
    )


@pytest.fixture()
def lab_client(test_db, temp_db_path):
    """Return a lab client backed by a world with translation enabled."""

    world = _build_world_with_service(_make_mock_service(), world_root=None)
    engine = _build_lab_engine(world)

    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        yield client


@pytest.fixture()
def lab_client_no_translation(test_db, temp_db_path):
    """Return a lab client backed by a world with translation disabled."""

    world = _build_world_with_service(None, world_root=None)
    engine = _build_lab_engine(world)

    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        yield client


# ---------------------------------------------------------------------------
# Role and auth behavior
# ---------------------------------------------------------------------------


@pytest.mark.api
def test_worlds_forbidden_for_player(lab_client, db_with_users, temp_db_path):
    """Player role must be rejected for lab endpoint access."""

    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testplayer")
        response = lab_client.get(f"/api/lab/worlds?session_id={sid}")
    assert response.status_code == 403


@pytest.mark.api
def test_worlds_allowed_for_admin_and_superuser(lab_client, db_with_users, temp_db_path):
    """Admin and superuser roles must be accepted for lab endpoint access."""

    with use_test_database(temp_db_path):
        admin_sid = _login(lab_client, "testadmin")
        admin_response = lab_client.get(f"/api/lab/worlds?session_id={admin_sid}")
        super_sid = _login(lab_client, "testsuperuser")
        super_response = lab_client.get(f"/api/lab/worlds?session_id={super_sid}")

    assert admin_response.status_code == 200
    assert super_response.status_code == 200


@pytest.mark.api
def test_worlds_invalid_session_returns_401(lab_client, test_db, temp_db_path):
    """Unknown session identifiers must return HTTP 401."""

    with use_test_database(temp_db_path):
        response = lab_client.get("/api/lab/worlds?session_id=not-a-real-session")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Active endpoint behavior
# ---------------------------------------------------------------------------


@pytest.mark.api
def test_worlds_returns_list_with_translation_flag(lab_client, db_with_users, temp_db_path):
    """World list response includes translation availability metadata."""

    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        response = lab_client.get(f"/api/lab/worlds?session_id={sid}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["worlds"][0]["world_id"] == TEST_WORLD_ID
    assert payload["worlds"][0]["translation_enabled"] is True


@pytest.mark.api
def test_worlds_translation_disabled_flag(lab_client_no_translation, db_with_users, temp_db_path):
    """World list marks translation-disabled worlds when service is unavailable."""

    with use_test_database(temp_db_path):
        sid = _login(lab_client_no_translation, "testadmin")
        response = lab_client_no_translation.get(f"/api/lab/worlds?session_id={sid}")

    assert response.status_code == 200
    assert response.json()["worlds"][0]["translation_enabled"] is False


@pytest.mark.api
def test_world_config_returns_translation_config(lab_client, db_with_users, temp_db_path):
    """World config endpoint returns canonical translation service settings."""

    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        response = lab_client.get(f"/api/lab/world-config/{TEST_WORLD_ID}?session_id={sid}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["world_id"] == TEST_WORLD_ID
    assert payload["model"] == "gemma2:2b"
    assert payload["translation_enabled"] is True


@pytest.mark.api
def test_world_config_unknown_world_returns_404(lab_client, db_with_users, temp_db_path):
    """Unknown world ids must return HTTP 404 on world-config reads."""

    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        response = lab_client.get(f"/api/lab/world-config/no_such_world?session_id={sid}")

    assert response.status_code == 404


@pytest.mark.api
def test_translate_success(lab_client, db_with_users, temp_db_path):
    """Translate endpoint returns service payload and world config on success."""

    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        response = lab_client.post(
            "/api/lab/translate",
            json={
                "session_id": sid,
                "world_id": TEST_WORLD_ID,
                "axes": {
                    "demeanor": {"label": "timid", "score": 0.07},
                    "wealth": {"label": "modest", "score": 0.33},
                },
                "ooc_message": "Keep your voice down and follow me.",
                "channel": "say",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["model"] == "gemma2:2b"
    assert payload["world_config"]["world_id"] == TEST_WORLD_ID


@pytest.mark.api
def test_translate_disabled_returns_503(lab_client_no_translation, db_with_users, temp_db_path):
    """Translate endpoint returns HTTP 503 when translation layer is disabled."""

    with use_test_database(temp_db_path):
        sid = _login(lab_client_no_translation, "testadmin")
        response = lab_client_no_translation.post(
            "/api/lab/translate",
            json={
                "session_id": sid,
                "world_id": TEST_WORLD_ID,
                "axes": {"demeanor": {"label": "timid", "score": 0.07}},
                "ooc_message": "Hello",
            },
        )

    assert response.status_code == 503


@pytest.mark.api
def test_translate_seed_minus_one_passes_none_to_service(test_db, temp_db_path, db_with_users):
    """``seed=-1`` is normalized to ``None`` before service invocation."""

    mock_service = _make_mock_service()
    world = _build_world_with_service(mock_service, world_root=None)
    engine = _build_lab_engine(world)
    app = FastAPI()
    register_routes(app, engine)
    client = TestClient(app)

    with use_test_database(temp_db_path):
        sid = _login(client, "testadmin")
        response = client.post(
            "/api/lab/translate",
            json={
                "session_id": sid,
                "world_id": TEST_WORLD_ID,
                "axes": {"demeanor": {"label": "timid", "score": 0.07}},
                "ooc_message": "Hello",
                "seed": -1,
            },
        )

    assert response.status_code == 200
    call_kwargs = cast(Any, mock_service).translate_with_axes.call_args.kwargs
    assert call_kwargs["seed"] is None


@pytest.mark.api
def test_world_image_policy_bundle_db_only_works_without_world_root(
    lab_client, db_with_users, temp_db_path
):
    """Image policy bundle resolves from DB activation state even with no world root."""

    with use_test_database(temp_db_path):
        _seed_image_policy_contract()
        sid = _login(lab_client, "testadmin")
        response = lab_client.get(
            f"/api/lab/world-image-policy-bundle/{TEST_WORLD_ID}?session_id={sid}"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["world_id"] == TEST_WORLD_ID
    assert payload["policy_schema"] == "pipeworks_policy_v1"
    assert payload["policy_bundle_id"] == "pipeworks_web_default"
    assert payload["composition_order"] == [
        "species_canon_block",
        "descriptor_layer_output",
        "clothing_block",
        "tone_profile_block",
    ]
    assert payload["missing_components"] == []


@pytest.mark.api
def test_world_image_policy_bundle_hash_changes_when_active_content_changes(
    lab_client, db_with_users, temp_db_path
):
    """Bundle hash changes when an activated DB policy payload changes."""

    scope = policy_service.ActivationScope(world_id=TEST_WORLD_ID, client_profile="")
    with use_test_database(temp_db_path):
        _seed_image_policy_contract()
        sid = _login(lab_client, "testadmin")
        first = lab_client.get(
            f"/api/lab/world-image-policy-bundle/{TEST_WORLD_ID}?session_id={sid}"
        )
        assert first.status_code == 200

        # Update active tone profile variant in-place; activation pointer is unchanged.
        _upsert_and_activate(
            scope=scope,
            policy_id="tone_profile:image.tone_profiles:ledger_engraving",
            variant="v1",
            content={"prompt_block": "High-contrast etching with deep graphite shadows."},
            policy_version=2,
        )

        second = lab_client.get(
            f"/api/lab/world-image-policy-bundle/{TEST_WORLD_ID}?session_id={sid}"
        )

    assert second.status_code == 200
    assert first.json()["policy_hash"] != second.json()["policy_hash"]


@pytest.mark.api
def test_compile_image_prompt_db_only_works_without_world_root(
    lab_client, db_with_users, temp_db_path
):
    """Compile endpoint is DB-only and succeeds when world policy files are absent."""

    with use_test_database(temp_db_path):
        _seed_image_policy_contract()
        sid = _login(lab_client, "testadmin")
        response = lab_client.post(
            "/api/lab/compile-image-prompt",
            json={
                "session_id": sid,
                "world_id": TEST_WORLD_ID,
                "species": "goblin",
                "gender": "male",
                "axes": {
                    "demeanor": {"label": "timid", "score": 0.07},
                    "wealth": {"label": "modest", "score": 0.33},
                },
                "world_context": ["coastal"],
                "occupation_signals": ["manual_labour"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["world_id"] == TEST_WORLD_ID
    assert payload["selected_species_block_id"] == "goblin_pipeworks_v1"
    assert payload["selected_clothing_profile_id"] == "clothing_default_v1"
    assert payload["selected_clothing_slot_ids"]["environment"] == "clothing_environment_coastal_v1"
    assert "Pipe-works goblin canonical species descriptor." in payload["compiled_prompt"]


@pytest.mark.api
def test_compile_image_prompt_missing_required_inputs_returns_409(
    lab_client, db_with_users, temp_db_path
):
    """Compile returns HTTP 409 when manifest-required runtime inputs are missing."""

    with use_test_database(temp_db_path):
        _seed_image_policy_contract()
        sid = _login(lab_client, "testadmin")
        response = lab_client.post(
            "/api/lab/compile-image-prompt",
            json={
                "session_id": sid,
                "world_id": TEST_WORLD_ID,
                "species": "goblin",
                "gender": "male",
                "axes": {},
            },
        )

    assert response.status_code == 409
    assert "entity.axes" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Legacy route removals (explicit breaking change assertions)
# ---------------------------------------------------------------------------


@pytest.mark.api
def test_legacy_world_prompt_routes_are_removed(lab_client, db_with_users, temp_db_path):
    """Legacy world prompt draft routes are removed and return HTTP 404."""

    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        list_response = lab_client.get(f"/api/lab/world-prompts/{TEST_WORLD_ID}?session_id={sid}")
        drafts_response = lab_client.get(
            f"/api/lab/world-prompts/{TEST_WORLD_ID}/drafts?session_id={sid}"
        )

    assert list_response.status_code == 404
    assert drafts_response.status_code == 404


@pytest.mark.api
def test_legacy_world_policy_bundle_routes_are_removed(lab_client, db_with_users, temp_db_path):
    """Legacy world policy bundle draft routes are removed and return HTTP 404."""

    with use_test_database(temp_db_path):
        sid = _login(lab_client, "testadmin")
        bundle_response = lab_client.get(
            f"/api/lab/world-policy-bundle/{TEST_WORLD_ID}?session_id={sid}"
        )
        drafts_response = lab_client.get(
            f"/api/lab/world-policy-bundle/{TEST_WORLD_ID}/drafts?session_id={sid}"
        )

    assert bundle_response.status_code == 404
    assert drafts_response.status_code == 404
