"""Unit tests for ``mud_server.services.policy_service``.

These tests cover service-only behavior that is easier to validate without
round-tripping through HTTP:
- scope parsing edge cases
- policy-id parsing and validation errors
- rollback guardrails for policy/scope mismatch
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from mud_server.db import constants, database
from mud_server.services import policy_service
from mud_server.services.policy_service import ActivationScope, PolicyServiceError


def _seed_species_variant(*, policy_key: str, variant: str, policy_version: int) -> str:
    """Create one species variant row through the service and return policy_id."""
    policy_id = f"species_block:image.blocks.species:{policy_key}"
    policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant=variant,
        schema_version="1.0",
        policy_version=policy_version,
        status="candidate",
        content={"text": f"{policy_key}-{variant}"},
        updated_by="tester",
    )
    return policy_id


def _seed_prompt_variant(
    *,
    namespace: str,
    policy_key: str,
    variant: str,
    policy_version: int,
    text: str,
) -> str:
    """Create one prompt variant row through the service and return policy_id."""
    policy_id = f"prompt:{namespace}:{policy_key}"
    policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant=variant,
        schema_version="1.0",
        policy_version=policy_version,
        status="candidate",
        content={"text": text},
        updated_by="tester",
    )
    return policy_id


def _seed_descriptor_layer_variant(
    *,
    policy_key: str,
    variant: str,
    policy_version: int,
    references: list[dict[str, str]],
) -> str:
    """Create one descriptor-layer variant with Layer 1 references."""
    policy_id = f"descriptor_layer:image.descriptors:{policy_key}"
    policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant=variant,
        schema_version="1.0",
        policy_version=policy_version,
        status="candidate",
        content={"references": references},
        updated_by="tester",
    )
    return policy_id


def _seed_effective_axis_bundle(
    *,
    world_id: str = constants.DEFAULT_WORLD_ID,
    bundle_id: str = "axis_core_v1",
    bundle_version: int = 1,
) -> tuple[str, str]:
    """Seed manifest+axis canonical objects and activate them for world scope."""
    manifest_policy_id = f"manifest_bundle:world.manifests:{world_id}"
    axis_policy_id = f"axis_bundle:axis.bundles:{bundle_id}"
    variant = f"v{bundle_version}"

    policy_service.upsert_policy_variant(
        policy_id=manifest_policy_id,
        variant=variant,
        schema_version="1.0",
        policy_version=bundle_version,
        status="active",
        content={
            "manifest": {
                "axis": {
                    "active_bundle": {
                        "id": bundle_id,
                        "version": bundle_version,
                    }
                },
                "image": {
                    "composition": {
                        "required_runtime_inputs": [
                            "entity.identity.gender",
                            "entity.species",
                            "entity.axes",
                        ]
                    }
                },
            }
        },
        updated_by="tester",
    )
    policy_service.upsert_policy_variant(
        policy_id=axis_policy_id,
        variant=variant,
        schema_version="1.0",
        policy_version=bundle_version,
        status="active",
        content={
            "axes": {
                "version": "1",
                "axes": {"demeanor": {"ordering": {"values": ["timid", "bold"]}}},
            },
            "thresholds": {
                "version": "1",
                "axes": {
                    "demeanor": {
                        "values": {
                            "timid": {"min": 0.0, "max": 0.49},
                            "bold": {"min": 0.5, "max": 1.0},
                        }
                    }
                },
            },
            "resolution": {
                "version": "1.0",
                "interactions": {
                    "chat": {
                        "channel_multipliers": {"say": 1.0, "yell": 1.5, "whisper": 0.5},
                        "min_gap_threshold": 0.05,
                        "axes": {
                            "demeanor": {"resolver": "dominance_shift", "base_magnitude": 0.03}
                        },
                    }
                },
            },
        },
        updated_by="tester",
    )
    scope = ActivationScope(world_id=world_id, client_profile="")
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=manifest_policy_id,
        variant=variant,
        activated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=axis_policy_id,
        variant=variant,
        activated_by="tester",
    )
    return manifest_policy_id, axis_policy_id


def _set_temp_worlds_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect policy export writes to a temporary world root."""
    monkeypatch.setattr(policy_service.config.worlds, "worlds_root", str(tmp_path))


def _write_species_yaml(
    *,
    worlds_root: Path,
    world_id: str,
    filename: str,
    text: str,
    version: int,
) -> None:
    """Write one legacy species YAML fixture file under the canonical path."""
    species_root = worlds_root / world_id / "policies" / "image" / "blocks" / "species"
    species_root.mkdir(parents=True, exist_ok=True)
    species_path = species_root / filename
    species_path.write_text(
        (
            f"id: {filename.removesuffix('.yaml')}\n"
            f"version: {version}\n"
            "text: |\n"
            f"  {text}\n"
        ),
        encoding="utf-8",
    )


def _write_registry_yaml(
    *,
    worlds_root: Path,
    world_id: str,
    filename: str,
    payload: dict[str, object],
) -> None:
    """Write one legacy registry YAML fixture file under the canonical path."""
    registry_root = worlds_root / world_id / "policies" / "image" / "registries"
    registry_root.mkdir(parents=True, exist_ok=True)
    registry_path = registry_root / filename
    registry_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def _write_descriptor_file(
    *,
    worlds_root: Path,
    world_id: str,
    filename: str,
    text: str,
) -> None:
    """Write one legacy descriptor-layer fixture file under the canonical path."""
    descriptor_root = worlds_root / world_id / "policies" / "image" / "descriptor_layers"
    descriptor_root.mkdir(parents=True, exist_ok=True)
    descriptor_path = descriptor_root / filename
    descriptor_path.write_text(text, encoding="utf-8")


def _write_tone_profile_json(
    *,
    worlds_root: Path,
    world_id: str,
    filename: str,
    payload: dict[str, object],
) -> None:
    """Write one legacy tone-profile JSON fixture under the canonical path."""
    tone_root = worlds_root / world_id / "policies" / "image" / "tone_profiles"
    tone_root.mkdir(parents=True, exist_ok=True)
    tone_path = tone_root / filename
    tone_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_prompt_file(
    *,
    worlds_root: Path,
    world_id: str,
    namespace_path: str,
    filename: str,
    text: str,
) -> None:
    """Write one legacy prompt fixture under translation/image prompt trees."""
    prompt_root = worlds_root / world_id / "policies" / Path(namespace_path)
    prompt_root.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_root / filename
    prompt_path.write_text(text, encoding="utf-8")


def _write_clothing_block_file(
    *,
    worlds_root: Path,
    world_id: str,
    category: str,
    filename: str,
    text: str,
) -> None:
    """Write one legacy clothing block text fixture under the canonical path."""
    clothing_root = worlds_root / world_id / "policies" / "image" / "blocks" / "clothing" / category
    clothing_root.mkdir(parents=True, exist_ok=True)
    clothing_path = clothing_root / filename
    clothing_path.write_text(text, encoding="utf-8")


def _write_manifest_and_axis_bundle(
    *,
    worlds_root: Path,
    world_id: str,
    bundle_id: str = "axis_core_v1",
    bundle_version: int = 1,
) -> None:
    """Write one manifest + axis bundle fixture set under canonical world policy paths."""
    policies_root = worlds_root / world_id / "policies"
    axis_root = policies_root / "axis"
    axis_root.mkdir(parents=True, exist_ok=True)

    (axis_root / "axes.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "axes": {
                    "demeanor": {
                        "ordering": {
                            "values": ["timid", "neutral", "bold"],
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (axis_root / "thresholds.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "axes": {
                    "demeanor": {
                        "values": {
                            "timid": {"min": 0.0, "max": 0.33},
                            "neutral": {"min": 0.34, "max": 0.66},
                            "bold": {"min": 0.67, "max": 1.0},
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (axis_root / "resolution.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "interactions": {
                    "chat": {
                        "channel_multipliers": {"say": 1.0, "yell": 1.5, "whisper": 0.5},
                        "min_gap_threshold": 0.1,
                        "axes": {
                            "demeanor": {"resolver": "dominance_shift", "base_magnitude": 0.03}
                        },
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (policies_root / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "policy_schema": "pipeworks_policy_v1",
                "policy_bundle": {"id": "pipeworks_web_default", "version": 1},
                "axis": {
                    "active_bundle": {
                        "id": bundle_id,
                        "version": bundle_version,
                        "files": {
                            "axes": "policies/axis/axes.yaml",
                            "thresholds": "policies/axis/thresholds.yaml",
                            "resolution": "policies/axis/resolution.yaml",
                        },
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


@pytest.mark.unit
def test_parse_scope_supports_world_only_and_world_plus_client() -> None:
    """Scope parser should normalize world-only and world+client forms."""
    world_only = policy_service.parse_scope(constants.DEFAULT_WORLD_ID)
    assert world_only.world_id == constants.DEFAULT_WORLD_ID
    assert world_only.client_profile == ""

    with_client = policy_service.parse_scope(f"{constants.DEFAULT_WORLD_ID}:mobile")
    assert with_client.world_id == constants.DEFAULT_WORLD_ID
    assert with_client.client_profile == "mobile"


@pytest.mark.unit
def test_parse_scope_rejects_empty_or_missing_world() -> None:
    """Scope parser should reject empty strings and empty world segments."""
    with pytest.raises(PolicyServiceError) as empty_error:
        policy_service.parse_scope("  ")
    assert empty_error.value.code == "POLICY_SCOPE_INVALID"

    with pytest.raises(PolicyServiceError) as missing_world_error:
        policy_service.parse_scope(":mobile")
    assert missing_world_error.value.code == "POLICY_SCOPE_INVALID"


@pytest.mark.unit
def test_validate_policy_variant_rejects_non_pilot_namespace(test_db) -> None:
    """Service validation should reject ``species_block`` outside pilot namespace."""
    result = policy_service.validate_policy_variant(
        policy_id="species_block:wrong.namespace:goblin",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="draft",
        content={"text": "example"},
        validated_by="tester",
    )
    assert result.is_valid is False
    assert any("species_block namespace must be exactly" in error for error in result.errors)


@pytest.mark.unit
def test_set_policy_activation_rollback_rejects_policy_id_mismatch(test_db) -> None:
    """Rollback should fail when referenced event belongs to a different policy."""
    goblin_policy_id = _seed_species_variant(policy_key="goblin", variant="v1", policy_version=1)
    orc_policy_id = _seed_species_variant(policy_key="orc", variant="v1", policy_version=1)

    activation = policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=goblin_policy_id,
        variant="v1",
        activated_by="tester",
    )
    event_id = activation["audit_event_id"]
    assert isinstance(event_id, int)

    with pytest.raises(PolicyServiceError) as error:
        policy_service.set_policy_activation(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
            policy_id=orc_policy_id,
            variant="v1",
            activated_by="tester",
            rollback_of_activation_id=event_id,
        )
    assert error.value.code == "POLICY_ROLLBACK_POLICY_MISMATCH"


@pytest.mark.unit
def test_set_policy_activation_rollback_rejects_scope_mismatch(test_db) -> None:
    """Rollback should fail when referenced event belongs to a different scope."""
    policy_id = _seed_species_variant(policy_key="gnoll", variant="v1", policy_version=1)

    activation = policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="mobile"),
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
    )
    event_id = activation["audit_event_id"]
    assert isinstance(event_id, int)

    with pytest.raises(PolicyServiceError) as error:
        policy_service.set_policy_activation(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="desktop"),
            policy_id=policy_id,
            variant="v1",
            activated_by="tester",
            rollback_of_activation_id=event_id,
        )
    assert error.value.code == "POLICY_ROLLBACK_SCOPE_MISMATCH"


@pytest.mark.unit
def test_publish_scope_rejects_unknown_world(test_db) -> None:
    """Publish should return a world-not-found error before querying activations."""
    # Ensure default world exists in fixture DB, then assert unknown world fails.
    assert database.get_world_by_id(constants.DEFAULT_WORLD_ID) is not None
    with pytest.raises(PolicyServiceError) as error:
        policy_service.publish_scope(
            scope=ActivationScope(world_id="unknown_world", client_profile=""),
            actor="tester",
        )
    assert error.value.code == "POLICY_WORLD_NOT_FOUND"


@pytest.mark.unit
def test_get_policy_raises_not_found_for_missing_variant(test_db) -> None:
    """Service get should return POLICY_NOT_FOUND when no row matches."""
    with pytest.raises(PolicyServiceError) as error:
        policy_service.get_policy(
            policy_id="species_block:image.blocks.species:missing",
            variant="v1",
        )
    assert error.value.code == "POLICY_NOT_FOUND"


@pytest.mark.unit
def test_get_publish_run_raises_not_found_for_missing_row(test_db) -> None:
    """Publish-run lookup should return stable not-found service error."""
    with pytest.raises(PolicyServiceError) as error:
        policy_service.get_publish_run(publish_run_id=999999)
    assert error.value.code == "POLICY_PUBLISH_RUN_NOT_FOUND"


@pytest.mark.unit
def test_set_policy_activation_rollback_rejects_unknown_event(test_db) -> None:
    """Rollback should fail with 404 when event id does not exist."""
    policy_id = _seed_species_variant(policy_key="troll", variant="v1", policy_version=1)
    with pytest.raises(PolicyServiceError) as error:
        policy_service.set_policy_activation(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
            policy_id=policy_id,
            variant="v1",
            activated_by="tester",
            rollback_of_activation_id=999999,
        )
    assert error.value.code == "POLICY_ROLLBACK_EVENT_NOT_FOUND"


@pytest.mark.unit
def test_set_policy_activation_wraps_repo_errors(test_db, monkeypatch) -> None:
    """Repository exceptions should map to POLICY_ACTIVATION_ERROR."""
    policy_id = _seed_species_variant(policy_key="ratfolk", variant="v1", policy_version=1)
    monkeypatch.setattr(
        policy_service.policy_repo,
        "set_policy_activation",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("activation broken")),
    )
    with pytest.raises(PolicyServiceError) as error:
        policy_service.set_policy_activation(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
            policy_id=policy_id,
            variant="v1",
            activated_by="tester",
        )
    assert error.value.code == "POLICY_ACTIVATION_ERROR"


@pytest.mark.unit
def test_set_policy_activation_detects_audit_replay_mismatch(test_db, monkeypatch) -> None:
    """Service should fail when replay state diverges from activation pointer rows."""
    policy_id = _seed_species_variant(policy_key="lizardfolk", variant="v1", policy_version=1)
    _seed_species_variant(policy_key="lizardfolk", variant="v2", policy_version=2)
    original_list_events = policy_service.policy_repo.list_activation_events

    def _list_activation_events_without_latest(**kwargs):
        events = original_list_events(**kwargs)
        return events[:-1] if len(events) > 1 else []

    policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
    )
    monkeypatch.setattr(
        policy_service.policy_repo,
        "list_activation_events",
        _list_activation_events_without_latest,
    )
    with pytest.raises(PolicyServiceError) as error:
        policy_service.set_policy_activation(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
            policy_id=policy_id,
            variant="v2",
            activated_by="tester",
        )
    assert error.value.code == "POLICY_ACTIVATION_REPLAY_MISMATCH"


@pytest.mark.unit
def test_resolve_effective_policy_activations_overlays_client_scope(test_db) -> None:
    """Client scope should inherit world defaults and override by policy_id."""
    goblin = _seed_species_variant(policy_key="goblin", variant="v1", policy_version=1)
    kobold = _seed_species_variant(policy_key="kobold", variant="v1", policy_version=1)
    _seed_species_variant(policy_key="kobold", variant="v2", policy_version=2)

    policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=goblin,
        variant="v1",
        activated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=kobold,
        variant="v1",
        activated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="mobile"),
        policy_id=kobold,
        variant="v2",
        activated_by="tester",
    )

    effective_rows = policy_service.resolve_effective_policy_activations(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="mobile"),
    )
    assert len(effective_rows) == 2
    by_policy_id = {row["policy_id"]: row for row in effective_rows}
    assert by_policy_id[goblin]["variant"] == "v1"
    assert by_policy_id[goblin]["client_profile"] == ""
    assert by_policy_id[kobold]["variant"] == "v2"
    assert by_policy_id[kobold]["client_profile"] == "mobile"


@pytest.mark.unit
def test_get_effective_policy_variant_resolves_layer3_pointer_to_variant_row(test_db) -> None:
    """Effective policy helper should return activated variant content for the scope."""
    policy_id = _seed_species_variant(policy_key="sprite", variant="v1", policy_version=1)
    policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
    )
    row = policy_service.get_effective_policy_variant(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=policy_id,
    )
    assert row is not None
    assert row["policy_id"] == policy_id
    assert row["variant"] == "v1"
    assert row["content"]["text"] == "sprite-v1"


@pytest.mark.unit
def test_validate_policy_variant_accepts_descriptor_layer_references(test_db) -> None:
    """Layer 2 validation should pass when all Layer 1 references exist."""
    referenced_policy_id = _seed_species_variant(policy_key="orc", variant="v1", policy_version=1)
    descriptor_policy_id = "descriptor_layer:image.descriptors:combat_style"

    result = policy_service.validate_policy_variant(
        policy_id=descriptor_policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={
            "references": [
                {
                    "policy_id": referenced_policy_id,
                    "variant": "v1",
                }
            ]
        },
        validated_by="tester",
    )
    assert result.is_valid is True
    assert result.errors == []


@pytest.mark.unit
def test_validate_policy_variant_accepts_prompt_layer1_content(test_db) -> None:
    """Prompt Layer 1 objects should accept non-empty ``content.text`` payloads."""
    result = policy_service.validate_policy_variant(
        policy_id="prompt:image.prompts:ic_default",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={"text": "Respond in-character with concise output."},
        validated_by="tester",
    )
    assert result.is_valid is True
    assert result.errors == []


@pytest.mark.unit
def test_validate_policy_variant_rejects_prompt_layer1_empty_text(test_db) -> None:
    """Prompt Layer 1 objects should reject empty ``content.text`` payloads."""
    result = policy_service.validate_policy_variant(
        policy_id="prompt:image.prompts:ic_default",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={"text": "   "},
        validated_by="tester",
    )
    assert result.is_valid is False
    assert result.errors == ["prompt content.text must be a non-empty string"]


@pytest.mark.unit
def test_import_species_blocks_from_legacy_yaml_backfills_and_activates(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should create canonical variants and seed world-scope activations."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_species_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="goblin_v1.yaml",
        text="Goblin source text",
        version=1,
    )
    _write_species_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="human_v1.yaml",
        text="Human source text",
        version=1,
    )

    summary = policy_service.import_species_blocks_from_legacy_yaml(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )

    assert summary.scanned_files == 2
    assert summary.imported_count == 2
    assert summary.updated_count == 0
    assert summary.skipped_count == 0
    assert summary.error_count == 0
    assert summary.activated_count == 2
    assert summary.activation_skipped_count == 0

    policies = policy_service.list_policies(
        policy_type="species_block",
        namespace="image.blocks.species",
        status="active",
    )
    assert len(policies) == 2
    by_policy_id = {policy["policy_id"]: policy for policy in policies}
    assert by_policy_id["species_block:image.blocks.species:goblin"]["content"] == {
        "text": "Goblin source text"
    }
    assert by_policy_id["species_block:image.blocks.species:human"]["content"] == {
        "text": "Human source text"
    }

    effective_rows = policy_service.resolve_effective_policy_activations(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
    )
    by_activation_policy_id = {row["policy_id"]: row for row in effective_rows}
    assert by_activation_policy_id["species_block:image.blocks.species:goblin"]["variant"] == "v1"
    assert by_activation_policy_id["species_block:image.blocks.species:human"]["variant"] == "v1"


@pytest.mark.unit
def test_import_species_blocks_from_legacy_yaml_is_idempotent_for_unchanged_content(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A second import pass should skip unchanged variants and activations."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_species_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="goblin_v1.yaml",
        text="Goblin source text",
        version=1,
    )

    first = policy_service.import_species_blocks_from_legacy_yaml(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    second = policy_service.import_species_blocks_from_legacy_yaml(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )

    assert first.imported_count == 1
    assert second.imported_count == 0
    assert second.updated_count == 0
    assert second.skipped_count == 1
    assert second.error_count == 0
    assert second.activated_count == 0
    assert second.activation_skipped_count == 1


@pytest.mark.unit
def test_import_species_blocks_from_legacy_yaml_continues_after_invalid_file(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should report invalid files and continue processing valid ones."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_species_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="goblin_v1.yaml",
        text="Goblin source text",
        version=1,
    )
    _write_species_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="broken_name.yaml",
        text="Broken source text",
        version=1,
    )

    summary = policy_service.import_species_blocks_from_legacy_yaml(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=False,
        status="candidate",
    )

    assert summary.scanned_files == 2
    assert summary.imported_count == 1
    assert summary.error_count == 1
    error_rows = [entry for entry in summary.entries if entry.action == "error"]
    assert len(error_rows) == 1
    assert "filename must match '<policy_key>_v<version>.yaml'" in error_rows[0].detail


@pytest.mark.unit
def test_import_species_blocks_from_legacy_yaml_rejects_invalid_status(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should reject unsupported status values before file scanning."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    with pytest.raises(PolicyServiceError) as error:
        policy_service.import_species_blocks_from_legacy_yaml(
            world_id=constants.DEFAULT_WORLD_ID,
            actor="importer",
            activate=False,
            status="invalid-status",
        )
    assert error.value.code == "POLICY_IMPORT_STATUS_INVALID"


@pytest.mark.unit
def test_import_species_blocks_from_legacy_yaml_rejects_missing_species_root(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should fail with a stable error when species source root is absent."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    (tmp_path / constants.DEFAULT_WORLD_ID).mkdir(parents=True, exist_ok=True)

    with pytest.raises(PolicyServiceError) as error:
        policy_service.import_species_blocks_from_legacy_yaml(
            world_id=constants.DEFAULT_WORLD_ID,
            actor="importer",
            activate=False,
            status="candidate",
        )
    assert error.value.code == "POLICY_SPECIES_SOURCE_NOT_FOUND"


@pytest.mark.unit
def test_import_species_blocks_from_legacy_yaml_updates_changed_variant(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should mark existing rows as updated when payload content changes."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_species_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="goblin_v1.yaml",
        text="Original source text",
        version=1,
    )
    first = policy_service.import_species_blocks_from_legacy_yaml(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=False,
        status="candidate",
    )
    assert first.imported_count == 1

    _write_species_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="goblin_v1.yaml",
        text="Updated source text",
        version=1,
    )
    second = policy_service.import_species_blocks_from_legacy_yaml(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=False,
        status="candidate",
    )
    assert second.imported_count == 0
    assert second.updated_count == 1
    assert second.error_count == 0
    updated_entries = [entry for entry in second.entries if entry.action == "updated"]
    assert len(updated_entries) == 1

    row = policy_service.get_policy(
        policy_id="species_block:image.blocks.species:goblin",
        variant="v1",
    )
    assert row["content"] == {"text": "Updated source text"}


@pytest.mark.unit
def test_import_species_blocks_from_legacy_yaml_reports_activation_failure(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should record activation errors without discarding import success."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_species_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="goblin_v1.yaml",
        text="Goblin source text",
        version=1,
    )

    def _raise_activation_error(**_kwargs):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_ACTIVATION_INVALID",
            detail="simulated activation failure",
        )

    monkeypatch.setattr(policy_service, "set_policy_activation", _raise_activation_error)

    summary = policy_service.import_species_blocks_from_legacy_yaml(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    assert summary.imported_count == 1
    assert summary.activated_count == 0
    assert summary.error_count == 1
    activation_errors = [
        entry
        for entry in summary.entries
        if entry.action == "error" and entry.source_path == "<activation>"
    ]
    assert len(activation_errors) == 1
    assert "activation failed: simulated activation failure" in activation_errors[0].detail


@pytest.mark.unit
def test_read_species_yaml_payload_rejects_non_mapping_payload(tmp_path: Path) -> None:
    """Reader should reject YAML payloads that are not dictionary objects."""
    species_file = tmp_path / "goblin_v1.yaml"
    species_file.write_text("- not-a-mapping\n", encoding="utf-8")

    with pytest.raises(ValueError) as error:
        policy_service._read_species_yaml_payload(species_file)
    assert "must contain a YAML object" in str(error.value)


@pytest.mark.unit
def test_read_species_yaml_payload_wraps_io_and_yaml_failures(tmp_path: Path) -> None:
    """Reader should wrap OS and YAML parser errors into stable service-facing errors."""
    missing_file = tmp_path / "missing.yaml"
    with pytest.raises(OSError) as io_error:
        policy_service._read_species_yaml_payload(missing_file)
    assert "Unable to read species source file" in str(io_error.value)

    invalid_yaml_file = tmp_path / "invalid.yaml"
    invalid_yaml_file.write_text("text: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError) as yaml_error:
        policy_service._read_species_yaml_payload(invalid_yaml_file)
    assert "Invalid YAML in species source file" in str(yaml_error.value)


@pytest.mark.unit
def test_resolve_species_policy_version_handles_string_and_invalid_values(tmp_path: Path) -> None:
    """Version resolver should parse numeric strings and reject invalid forms."""
    species_file = tmp_path / "goblin_v1.yaml"

    assert (
        policy_service._resolve_species_policy_version(
            payload={},
            file_policy_version=1,
            species_path=species_file,
        )
        == 1
    )

    assert (
        policy_service._resolve_species_policy_version(
            payload={"version": "1"},
            file_policy_version=1,
            species_path=species_file,
        )
        == 1
    )

    with pytest.raises(ValueError) as bool_error:
        policy_service._resolve_species_policy_version(
            payload={"version": True},
            file_policy_version=1,
            species_path=species_file,
        )
    assert "invalid boolean version value" in str(bool_error.value)

    with pytest.raises(ValueError) as non_positive_error:
        policy_service._resolve_species_policy_version(
            payload={"version": 0},
            file_policy_version=1,
            species_path=species_file,
        )
    assert "must be >= 1" in str(non_positive_error.value)

    with pytest.raises(ValueError) as mismatch_error:
        policy_service._resolve_species_policy_version(
            payload={"version": 2},
            file_policy_version=1,
            species_path=species_file,
        )
    assert "must match filename v1" in str(mismatch_error.value)

    with pytest.raises(ValueError) as non_numeric_error:
        policy_service._resolve_species_policy_version(
            payload={"version": "v2"},
            file_policy_version=1,
            species_path=species_file,
        )
    assert "must be a positive integer" in str(non_numeric_error.value)


@pytest.mark.unit
def test_extract_species_text_content_requires_non_empty_text(tmp_path: Path) -> None:
    """Text extractor should reject missing/empty text content in legacy payloads."""
    species_file = tmp_path / "goblin_v1.yaml"
    with pytest.raises(ValueError) as error:
        policy_service._extract_species_text_content(
            payload={"text": "   "},
            species_path=species_file,
        )
    assert "must define non-empty text content" in str(error.value)


@pytest.mark.unit
def test_import_layer2_policies_from_legacy_files_backfills_and_activates(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Layer 2 importer should create registry/descriptor rows and seed activations."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _seed_species_variant(policy_key="goblin", variant="v1", policy_version=1)
    _seed_species_variant(policy_key="human", variant="v1", policy_version=1)

    _write_registry_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="species_registry.yaml",
        payload={
            "registry": {"id": "species_registry", "version": 1},
            "entries": [
                {"block_path": "policies/image/blocks/species/goblin_v1.yaml"},
                {"block_path": "policies/image/blocks/species/human_v1.yaml"},
            ],
        },
    )
    _write_descriptor_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="id_card_v1.txt",
        text="Descriptor text payload.",
    )

    summary = policy_service.import_layer2_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )

    assert summary.scanned_descriptor_files == 1
    assert summary.scanned_registry_files == 1
    assert summary.imported_count == 2
    assert summary.updated_count == 0
    assert summary.skipped_count == 0
    assert summary.error_count == 0
    assert summary.activated_count == 2
    assert summary.activation_skipped_count == 0

    species_refs = [
        {"policy_id": "species_block:image.blocks.species:goblin", "variant": "v1"},
        {"policy_id": "species_block:image.blocks.species:human", "variant": "v1"},
    ]
    registry_row = policy_service.get_policy(
        policy_id="registry:image.registries:species_registry",
        variant="v1",
    )
    descriptor_row = policy_service.get_policy(
        policy_id="descriptor_layer:image.descriptors:id_card",
        variant="v1",
    )
    assert registry_row["content"] == {"references": species_refs}
    assert descriptor_row["content"] == {"references": species_refs}

    effective_rows = policy_service.resolve_effective_policy_activations(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
    )
    by_policy_id = {row["policy_id"]: row for row in effective_rows}
    assert by_policy_id["registry:image.registries:species_registry"]["variant"] == "v1"
    assert by_policy_id["descriptor_layer:image.descriptors:id_card"]["variant"] == "v1"


@pytest.mark.unit
def test_import_layer2_policies_from_legacy_files_is_idempotent(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A second Layer 2 import pass should skip unchanged variants/activations."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _seed_species_variant(policy_key="goblin", variant="v1", policy_version=1)
    _write_registry_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="species_registry.yaml",
        payload={
            "registry": {"id": "species_registry", "version": 1},
            "entries": [{"block_path": "policies/image/blocks/species/goblin_v1.yaml"}],
        },
    )
    _write_descriptor_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="id_card_v1.txt",
        text="Descriptor text payload.",
    )

    first = policy_service.import_layer2_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    second = policy_service.import_layer2_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    assert first.imported_count == 2
    assert second.imported_count == 0
    assert second.updated_count == 0
    assert second.skipped_count == 2
    assert second.error_count == 0
    assert second.activated_count == 0
    assert second.activation_skipped_count == 2


@pytest.mark.unit
def test_import_layer2_policies_from_legacy_files_reports_unmappable_registry(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Layer 2 importer should report unmappable registry files and continue."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _seed_species_variant(policy_key="goblin", variant="v1", policy_version=1)

    _write_registry_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="species_registry.yaml",
        payload={
            "registry": {"id": "species_registry", "version": 1},
            "entries": [{"block_path": "policies/image/blocks/species/goblin_v1.yaml"}],
        },
    )
    _write_registry_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="clothing_registry.yaml",
        payload={
            "registry": {"id": "clothing_registry", "version": 1},
            "slots": {
                "environment": [
                    {
                        "fragment_path": (
                            "policies/image/blocks/clothing/environment/maritime_v2.txt"
                        )
                    }
                ]
            },
        },
    )
    _write_descriptor_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="id_card_v1.txt",
        text="Descriptor text payload.",
    )

    summary = policy_service.import_layer2_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=False,
        status="candidate",
    )

    assert summary.scanned_registry_files == 2
    assert summary.scanned_descriptor_files == 1
    assert summary.imported_count == 2
    assert summary.error_count == 1
    error_rows = [entry for entry in summary.entries if entry.action == "error"]
    assert len(error_rows) == 1
    assert "references missing Layer 1 variant" in error_rows[0].detail


@pytest.mark.unit
def test_import_layer2_policies_from_legacy_files_rejects_missing_source_roots(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Layer 2 importer should fail when both source roots are absent."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    (tmp_path / constants.DEFAULT_WORLD_ID).mkdir(parents=True, exist_ok=True)

    with pytest.raises(PolicyServiceError) as error:
        policy_service.import_layer2_policies_from_legacy_files(
            world_id=constants.DEFAULT_WORLD_ID,
            actor="importer",
            activate=False,
            status="active",
        )
    assert error.value.code == "POLICY_LAYER2_SOURCE_NOT_FOUND"


@pytest.mark.unit
def test_import_layer2_policies_from_legacy_files_rejects_invalid_status(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Layer 2 importer should reject unsupported status values before scanning."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_descriptor_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="id_card_v1.txt",
        text="Descriptor text payload.",
    )
    with pytest.raises(PolicyServiceError) as error:
        policy_service.import_layer2_policies_from_legacy_files(
            world_id=constants.DEFAULT_WORLD_ID,
            actor="importer",
            activate=False,
            status="invalid-status",
        )
    assert error.value.code == "POLICY_IMPORT_STATUS_INVALID"


@pytest.mark.unit
def test_import_layer2_policies_from_legacy_files_updates_changed_variants(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Layer 2 importer should mark both registry and descriptor rows as updated."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _seed_species_variant(policy_key="goblin", variant="v1", policy_version=1)
    _seed_species_variant(policy_key="human", variant="v1", policy_version=1)

    _write_registry_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="species_registry.yaml",
        payload={
            "registry": {"id": "species_registry", "version": 1},
            "entries": [{"block_path": "policies/image/blocks/species/goblin_v1.yaml"}],
        },
    )
    _write_descriptor_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="id_card_v1.txt",
        text="Descriptor text payload.",
    )
    first = policy_service.import_layer2_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=False,
        status="candidate",
    )
    assert first.imported_count == 2

    _write_registry_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="species_registry.yaml",
        payload={
            "registry": {"id": "species_registry", "version": 1},
            "entries": [
                {"block_path": "policies/image/blocks/species/goblin_v1.yaml"},
                {"block_path": "policies/image/blocks/species/human_v1.yaml"},
            ],
        },
    )
    second = policy_service.import_layer2_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=False,
        status="candidate",
    )
    assert second.imported_count == 0
    assert second.updated_count == 2
    assert second.error_count == 0
    updated_entries = [entry for entry in second.entries if entry.action == "updated"]
    assert len(updated_entries) == 2


@pytest.mark.unit
def test_import_layer2_policies_from_legacy_files_errors_when_descriptor_refs_unavailable(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Descriptor rows should error when no valid Layer 1 references can be inferred."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_descriptor_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="id_card_v1.txt",
        text="Descriptor text payload.",
    )
    summary = policy_service.import_layer2_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=False,
        status="active",
    )
    assert summary.imported_count == 0
    assert summary.error_count == 1
    assert "could not infer Layer 1 references" in summary.entries[0].detail


@pytest.mark.unit
def test_import_layer2_policies_from_legacy_files_reports_activation_failure(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Layer 2 importer should record activation errors without discarding import success."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _seed_species_variant(policy_key="goblin", variant="v1", policy_version=1)
    _write_registry_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="species_registry.yaml",
        payload={
            "registry": {"id": "species_registry", "version": 1},
            "entries": [{"block_path": "policies/image/blocks/species/goblin_v1.yaml"}],
        },
    )
    _write_descriptor_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="id_card_v1.txt",
        text="Descriptor text payload.",
    )

    def _raise_activation_error(**_kwargs):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_ACTIVATION_INVALID",
            detail="simulated activation failure",
        )

    monkeypatch.setattr(policy_service, "set_policy_activation", _raise_activation_error)

    summary = policy_service.import_layer2_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    assert summary.imported_count == 2
    assert summary.activated_count == 0
    assert summary.error_count == 2
    activation_errors = [
        entry
        for entry in summary.entries
        if entry.action == "error" and entry.source_path == "<activation>"
    ]
    assert len(activation_errors) == 2


@pytest.mark.unit
def test_import_tone_prompt_policies_from_legacy_files_backfills_and_activates(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should backfill tone-profile/prompt files and seed activations."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_tone_profile_json(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="ledger_engraving_v1.json",
        payload={
            "name": "ledger_engraving_v1",
            "prompt_block": "Muted engraving style on archival texture.",
        },
    )
    _write_prompt_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        namespace_path="translation/prompts/ic",
        filename="default_v1.txt",
        text="Translation prompt text.\n",
    )
    _write_prompt_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        namespace_path="image/prompts/species",
        filename="goblin_v1.txt",
        text="Image prompt text.\n",
    )

    summary = policy_service.import_tone_prompt_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )

    assert summary.scanned_tone_profile_files == 1
    assert summary.scanned_prompt_files == 2
    assert summary.imported_count == 3
    assert summary.updated_count == 0
    assert summary.skipped_count == 0
    assert summary.error_count == 0
    assert summary.activated_count == 3
    assert summary.activation_skipped_count == 0

    tone_row = policy_service.get_policy(
        policy_id="tone_profile:image.tone_profiles:ledger_engraving",
        variant="v1",
    )
    translation_prompt_row = policy_service.get_policy(
        policy_id="prompt:translation.prompts.ic:default",
        variant="v1",
    )
    image_prompt_row = policy_service.get_policy(
        policy_id="prompt:image.prompts.species:goblin",
        variant="v1",
    )
    assert tone_row["content"]["prompt_block"] == "Muted engraving style on archival texture."
    assert translation_prompt_row["content"] == {"text": "Translation prompt text."}
    assert image_prompt_row["content"] == {"text": "Image prompt text."}

    effective_rows = policy_service.resolve_effective_policy_activations(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
    )
    by_policy_id = {row["policy_id"]: row for row in effective_rows}
    assert by_policy_id["tone_profile:image.tone_profiles:ledger_engraving"]["variant"] == "v1"
    assert by_policy_id["prompt:translation.prompts.ic:default"]["variant"] == "v1"
    assert by_policy_id["prompt:image.prompts.species:goblin"]["variant"] == "v1"


@pytest.mark.unit
def test_import_tone_prompt_policies_from_legacy_files_is_idempotent(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Second import pass should skip unchanged tone-profile/prompt variants."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_tone_profile_json(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="ledger_engraving_v1.json",
        payload={"prompt_block": "Muted engraving style on archival texture."},
    )
    _write_prompt_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        namespace_path="translation/prompts/ic",
        filename="default_v1.txt",
        text="Translation prompt text.",
    )

    first = policy_service.import_tone_prompt_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    second = policy_service.import_tone_prompt_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    assert first.imported_count == 2
    assert second.imported_count == 0
    assert second.updated_count == 0
    assert second.skipped_count == 2
    assert second.error_count == 0
    assert second.activated_count == 0
    assert second.activation_skipped_count == 2


@pytest.mark.unit
def test_import_tone_prompt_policies_from_legacy_files_continues_after_invalid_file(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should report invalid files and continue importing valid files."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_tone_profile_json(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="ledger_engraving_v1.json",
        payload={"prompt_block": "Muted engraving style on archival texture."},
    )
    _write_prompt_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        namespace_path="translation/prompts/ic",
        filename="broken_prompt.txt",
        text="Broken filename prompt.",
    )

    summary = policy_service.import_tone_prompt_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=False,
        status="candidate",
    )
    assert summary.scanned_tone_profile_files == 1
    assert summary.scanned_prompt_files == 1
    assert summary.imported_count == 1
    assert summary.error_count == 1
    error_rows = [entry for entry in summary.entries if entry.action == "error"]
    assert len(error_rows) == 1
    assert "Prompt filename must match '<policy_key>_v<version>.txt'" in error_rows[0].detail


@pytest.mark.unit
def test_import_tone_prompt_policies_from_legacy_files_rejects_missing_source_roots(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should fail when no tone-profile/prompt roots exist."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    (tmp_path / constants.DEFAULT_WORLD_ID).mkdir(parents=True, exist_ok=True)

    with pytest.raises(PolicyServiceError) as error:
        policy_service.import_tone_prompt_policies_from_legacy_files(
            world_id=constants.DEFAULT_WORLD_ID,
            actor="importer",
            activate=False,
            status="active",
        )
    assert error.value.code == "POLICY_TONE_PROMPT_SOURCE_NOT_FOUND"


@pytest.mark.unit
def test_import_tone_prompt_policies_from_legacy_files_rejects_invalid_status(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should reject unsupported status values before scanning."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_tone_profile_json(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="ledger_engraving_v1.json",
        payload={"prompt_block": "Muted engraving style on archival texture."},
    )
    with pytest.raises(PolicyServiceError) as error:
        policy_service.import_tone_prompt_policies_from_legacy_files(
            world_id=constants.DEFAULT_WORLD_ID,
            actor="importer",
            activate=False,
            status="invalid-status",
        )
    assert error.value.code == "POLICY_IMPORT_STATUS_INVALID"


@pytest.mark.unit
def test_import_tone_prompt_policies_from_legacy_files_reports_activation_failure(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Importer should record activation failures while preserving import success."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_tone_profile_json(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="ledger_engraving_v1.json",
        payload={"prompt_block": "Muted engraving style on archival texture."},
    )
    _write_prompt_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        namespace_path="translation/prompts/ic",
        filename="default_v1.txt",
        text="Translation prompt text.",
    )

    def _raise_activation_error(**_kwargs):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_ACTIVATION_INVALID",
            detail="simulated activation failure",
        )

    monkeypatch.setattr(policy_service, "set_policy_activation", _raise_activation_error)
    summary = policy_service.import_tone_prompt_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    assert summary.imported_count == 2
    assert summary.activated_count == 0
    assert summary.error_count == 2
    activation_errors = [
        entry
        for entry in summary.entries
        if entry.action == "error" and entry.source_path == "<activation>"
    ]
    assert len(activation_errors) == 2


@pytest.mark.unit
def test_import_clothing_block_policies_from_legacy_files_backfills_and_activates(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Clothing importer should create Layer 1 rows and seed world activations."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_clothing_block_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        category="environment",
        filename="coastal_v1.txt",
        text="Salt-worn boots and weathered waxed coat.",
    )

    summary = policy_service.import_clothing_block_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="candidate",
    )
    assert summary.scanned_clothing_files == 1
    assert summary.imported_count == 1
    assert summary.updated_count == 0
    assert summary.error_count == 0
    assert summary.activated_count == 1

    row = policy_service.get_policy(
        policy_id="clothing_block:image.blocks.clothing.environment:coastal",
        variant="v1",
    )
    assert row["content"]["text"] == "Salt-worn boots and weathered waxed coat."
    assert row["status"] == "candidate"


@pytest.mark.unit
def test_import_axis_manifest_policies_from_legacy_files_backfills_and_activates(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Axis/manifest importer should create canonical bundle objects and activate them."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_manifest_and_axis_bundle(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        bundle_id="axis_core_v1",
        bundle_version=1,
    )

    summary = policy_service.import_axis_manifest_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    assert summary.scanned_files == 4
    assert summary.imported_count == 2
    assert summary.updated_count == 0
    assert summary.error_count == 0
    assert summary.activated_count == 2

    manifest_row = policy_service.get_policy(
        policy_id=f"manifest_bundle:world.manifests:{constants.DEFAULT_WORLD_ID}",
        variant="v1",
    )
    axis_row = policy_service.get_policy(
        policy_id="axis_bundle:axis.bundles:axis_core_v1",
        variant="v1",
    )
    assert isinstance(manifest_row["content"]["manifest"], dict)
    assert isinstance(axis_row["content"]["axes"], dict)
    assert isinstance(axis_row["content"]["thresholds"], dict)
    assert isinstance(axis_row["content"]["resolution"], dict)


@pytest.mark.unit
def test_import_world_policies_from_legacy_files_runs_all_domains(
    test_db,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Import-all should aggregate all domain import counts in dependency order."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    _write_species_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="goblin_v1.yaml",
        text="Wire-thin goblin silhouette.",
        version=1,
    )
    _write_tone_profile_json(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="ledger_engraving_v1.json",
        payload={"prompt_block": "Muted engraving style on archival texture."},
    )
    _write_prompt_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        namespace_path="translation/prompts/ic",
        filename="default_v1.txt",
        text="Translate into terse in-character dialogue.\n",
    )
    _write_clothing_block_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        category="environment",
        filename="coastal_v1.txt",
        text="Salt-worn boots and weathered waxed coat.",
    )
    _write_registry_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="species_registry.yaml",
        payload={
            "registry": {"id": "species_registry", "version": 1},
            "entries": [{"block_path": "policies/image/blocks/species/goblin_v1.yaml"}],
        },
    )
    _write_registry_yaml(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="clothing_registry.yaml",
        payload={
            "registry": {"id": "clothing_registry", "version": 1},
            "entries": [
                {"fragment_path": ("policies/image/blocks/clothing/environment/coastal_v1.txt")}
            ],
        },
    )
    _write_descriptor_file(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        filename="id_card_v1.txt",
        text="Descriptor text payload.",
    )
    _write_manifest_and_axis_bundle(
        worlds_root=tmp_path,
        world_id=constants.DEFAULT_WORLD_ID,
        bundle_id="axis_core_v1",
        bundle_version=1,
    )

    summary = policy_service.import_world_policies_from_legacy_files(
        world_id=constants.DEFAULT_WORLD_ID,
        actor="importer",
        activate=True,
        status="active",
    )
    assert summary.imported_count == 9
    assert summary.updated_count == 0
    assert summary.error_count == 0
    assert summary.activated_count == 9
    assert len(summary.entries) == 5
    assert any("species: imported=1" in entry for entry in summary.entries)
    assert any("tone_prompt: imported=2" in entry for entry in summary.entries)
    assert any("clothing: imported=1" in entry for entry in summary.entries)
    assert any("layer2: imported=3" in entry for entry in summary.entries)
    assert any("axis_manifest: imported=2" in entry for entry in summary.entries)


@pytest.mark.unit
def test_parse_descriptor_filename_rejects_invalid_names(tmp_path: Path) -> None:
    """Descriptor filename parser should enforce versioned naming contract."""
    with pytest.raises(ValueError) as error:
        policy_service._parse_descriptor_filename(tmp_path / "id_card.txt")
    assert "Descriptor filename must match" in str(error.value)


@pytest.mark.unit
def test_parse_tone_profile_filename_rejects_invalid_names(tmp_path: Path) -> None:
    """Tone-profile filename parser should enforce versioned naming contract."""
    with pytest.raises(ValueError) as error:
        policy_service._parse_tone_profile_filename(tmp_path / "ledger_engraving.json")
    assert "Tone profile filename must match" in str(error.value)


@pytest.mark.unit
def test_read_tone_profile_json_content_wraps_io_json_and_shape_errors(tmp_path: Path) -> None:
    """Tone-profile reader should wrap IO/JSON errors and reject non-object payloads."""
    missing_file = tmp_path / "missing.json"
    with pytest.raises(OSError) as io_error:
        policy_service._read_tone_profile_json_content(missing_file)
    assert "Unable to read tone profile source file" in str(io_error.value)

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{bad json}", encoding="utf-8")
    with pytest.raises(ValueError) as json_error:
        policy_service._read_tone_profile_json_content(invalid_json)
    assert "Invalid JSON in tone profile source file" in str(json_error.value)

    list_payload = tmp_path / "list.json"
    list_payload.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(ValueError) as shape_error:
        policy_service._read_tone_profile_json_content(list_payload)
    assert "must contain a JSON object" in str(shape_error.value)


@pytest.mark.unit
def test_parse_prompt_file_identity_validates_filename_and_namespace(tmp_path: Path) -> None:
    """Prompt identity parser should enforce filename and allowed prompt roots."""
    world_root = tmp_path / "world"
    prompt_file = world_root / "policies" / "translation" / "prompts" / "ic" / "default_v2.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text("prompt text", encoding="utf-8")
    namespace, policy_key, variant, policy_version = policy_service._parse_prompt_file_identity(
        prompt_path=prompt_file,
        world_root=world_root,
    )
    assert namespace == "translation.prompts.ic"
    assert policy_key == "default"
    assert variant == "v2"
    assert policy_version == 2

    with pytest.raises(ValueError) as filename_error:
        policy_service._parse_prompt_file_identity(
            prompt_path=world_root / "policies" / "translation" / "prompts" / "ic" / "default.txt",
            world_root=world_root,
        )
    assert "Prompt filename must match" in str(filename_error.value)

    invalid_namespace_file = world_root / "policies" / "translation" / "templates" / "ic_v1.txt"
    invalid_namespace_file.parent.mkdir(parents=True, exist_ok=True)
    invalid_namespace_file.write_text("prompt text", encoding="utf-8")
    with pytest.raises(ValueError) as namespace_error:
        policy_service._parse_prompt_file_identity(
            prompt_path=invalid_namespace_file,
            world_root=world_root,
        )
    assert "must be under 'policies/image/prompts' or 'policies/translation/prompts'" in str(
        namespace_error.value
    )

    outside_file = tmp_path / "outside" / "default_v1.txt"
    outside_file.parent.mkdir(parents=True, exist_ok=True)
    outside_file.write_text("prompt text", encoding="utf-8")
    with pytest.raises(ValueError) as outside_error:
        policy_service._parse_prompt_file_identity(
            prompt_path=outside_file,
            world_root=world_root,
        )
    assert "must be located under" in str(outside_error.value)


@pytest.mark.unit
def test_parse_clothing_block_file_identity_validates_filename_and_root(tmp_path: Path) -> None:
    """Clothing identity parser should enforce versioned filename and source root."""
    world_root = tmp_path / "world"
    block_file = (
        world_root / "policies" / "image" / "blocks" / "clothing" / "environment" / "coastal_v2.txt"
    )
    block_file.parent.mkdir(parents=True, exist_ok=True)
    block_file.write_text("coastal block", encoding="utf-8")
    namespace, policy_key, variant, policy_version = (
        policy_service._parse_clothing_block_file_identity(
            clothing_path=block_file,
            world_root=world_root,
        )
    )
    assert namespace == "image.blocks.clothing.environment"
    assert policy_key == "coastal"
    assert variant == "v2"
    assert policy_version == 2

    with pytest.raises(ValueError) as filename_error:
        policy_service._parse_clothing_block_file_identity(
            clothing_path=block_file.with_name("coastal.txt"),
            world_root=world_root,
        )
    assert "Clothing block filename must match" in str(filename_error.value)

    outside_file = tmp_path / "outside" / "coastal_v1.txt"
    outside_file.parent.mkdir(parents=True, exist_ok=True)
    outside_file.write_text("coastal block", encoding="utf-8")
    with pytest.raises(ValueError) as outside_error:
        policy_service._parse_clothing_block_file_identity(
            clothing_path=outside_file,
            world_root=world_root,
        )
    assert "must be located under" in str(outside_error.value)


@pytest.mark.unit
def test_read_prompt_text_content_requires_non_empty_and_wraps_io(tmp_path: Path) -> None:
    """Prompt reader should reject empty content and normalize trailing newlines."""
    missing_file = tmp_path / "missing.txt"
    with pytest.raises(OSError) as io_error:
        policy_service._read_prompt_text_content(missing_file)
    assert "Unable to read prompt source file" in str(io_error.value)

    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError) as empty_error:
        policy_service._read_prompt_text_content(empty_file)
    assert "must define non-empty text content" in str(empty_error.value)

    content_file = tmp_path / "default_v1.txt"
    content_file.write_text("Prompt body.\n\n", encoding="utf-8")
    assert policy_service._read_prompt_text_content(content_file) == "Prompt body."


@pytest.mark.unit
def test_manifest_helper_read_and_resolve_functions_validate_shape_and_paths(
    tmp_path: Path,
) -> None:
    """Manifest helper functions should read YAML and reject invalid path traversal."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("policy_bundle:\n  version: 1\n", encoding="utf-8")
    manifest = policy_service._read_manifest_yaml_payload(manifest_file)
    assert manifest["policy_bundle"]["version"] == 1

    with pytest.raises(ValueError) as missing_file_error:
        policy_service._require_manifest_relative_file_path(
            axis_files={},
            key="axes",
            context="manifest test",
        )
    assert "axis.active_bundle.files.axes must be a non-empty string" in str(
        missing_file_error.value
    )

    world_root = tmp_path / "world"
    world_root.mkdir(parents=True, exist_ok=True)
    resolved = policy_service._resolve_world_relative_path(
        world_root=world_root,
        relative_path="policies/axis/axes.yaml",
    )
    assert resolved == world_root / "policies" / "axis" / "axes.yaml"

    with pytest.raises(ValueError) as traversal_error:
        policy_service._resolve_world_relative_path(
            world_root=world_root,
            relative_path="../outside.yaml",
        )
    assert "escapes world root" in str(traversal_error.value)

    axes_file = world_root / "policies" / "axis" / "axes.yaml"
    axes_file.parent.mkdir(parents=True, exist_ok=True)
    axes_file.write_text("axes:\n  demeanor: {}\n", encoding="utf-8")
    payload = policy_service._read_yaml_payload_file(axes_file, context="Axis bundle file")
    assert payload == {"axes": {"demeanor": {}}}


@pytest.mark.unit
def test_read_registry_yaml_payload_wraps_io_yaml_and_shape_errors(tmp_path: Path) -> None:
    """Registry reader should wrap IO/YAML errors and reject non-object payloads."""
    missing_file = tmp_path / "missing.yaml"
    with pytest.raises(OSError) as io_error:
        policy_service._read_registry_yaml_payload(missing_file)
    assert "Unable to read registry source file" in str(io_error.value)

    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("registry: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError) as yaml_error:
        policy_service._read_registry_yaml_payload(invalid_yaml)
    assert "Invalid YAML in registry source file" in str(yaml_error.value)

    list_payload = tmp_path / "list.yaml"
    list_payload.write_text("- bad\n", encoding="utf-8")
    with pytest.raises(ValueError) as shape_error:
        policy_service._read_registry_yaml_payload(list_payload)
    assert "must contain a YAML object" in str(shape_error.value)


@pytest.mark.unit
def test_resolve_registry_identity_validates_meta_and_versions(tmp_path: Path) -> None:
    """Registry identity resolver should enforce id/version consistency rules."""
    with pytest.raises(ValueError) as meta_error:
        policy_service._resolve_registry_identity(
            registry_path=tmp_path / "species_registry.yaml",
            payload={"registry": []},
        )
    assert "field 'registry' must be an object" in str(meta_error.value)

    with pytest.raises(ValueError) as version_missing_error:
        policy_service._resolve_registry_identity(
            registry_path=tmp_path / "species_registry.yaml",
            payload={"registry": {"id": "species_registry"}},
        )
    assert "registry.version must be a positive integer" in str(version_missing_error.value)

    with pytest.raises(ValueError) as mismatch_error:
        policy_service._resolve_registry_identity(
            registry_path=tmp_path / "species_registry_v1.yaml",
            payload={"registry": {"id": "species_registry", "version": 2}},
        )
    assert "must match filename v1" in str(mismatch_error.value)

    with pytest.raises(ValueError) as key_mismatch_error:
        policy_service._resolve_registry_identity(
            registry_path=tmp_path / "species_registry_v1.yaml",
            payload={"registry": {"id": "other_registry", "version": 1}},
        )
    assert "must match filename policy_key" in str(key_mismatch_error.value)


@pytest.mark.unit
def test_resolve_registry_identity_versioned_success_uses_filename_version(tmp_path: Path) -> None:
    """Versioned registry filenames should resolve canonical key/variant from filename."""
    policy_key, variant, policy_version = policy_service._resolve_registry_identity(
        registry_path=tmp_path / "species_registry_v2.yaml",
        payload={"registry": {"id": "species_registry"}},
    )
    assert policy_key == "species_registry"
    assert variant == "v2"
    assert policy_version == 2


@pytest.mark.unit
def test_resolve_positive_int_version_parses_and_rejects_invalid_values() -> None:
    """Positive-int resolver should parse valid values and reject invalid ones."""
    assert (
        policy_service._resolve_positive_int_version(value=None, default=4, context="test context")
        == 4
    )
    assert (
        policy_service._resolve_positive_int_version(
            value="7", default=None, context="test context"
        )
        == 7
    )
    with pytest.raises(ValueError) as bool_error:
        policy_service._resolve_positive_int_version(
            value=True, default=None, context="test context"
        )
    assert "must not be a boolean" in str(bool_error.value)

    with pytest.raises(ValueError) as non_numeric_error:
        policy_service._resolve_positive_int_version(
            value="v1", default=None, context="test context"
        )
    assert "must be a positive integer" in str(non_numeric_error.value)

    with pytest.raises(ValueError) as low_error:
        policy_service._resolve_positive_int_version(value=0, default=None, context="test context")
    assert "must be >= 1" in str(low_error.value)


@pytest.mark.unit
def test_extract_registry_references_accepts_explicit_and_rejects_invalid(tmp_path: Path) -> None:
    """Registry reference extraction should handle explicit references and invalid shapes."""
    path = tmp_path / "species_registry.yaml"
    explicit = policy_service._extract_registry_references(
        payload={
            "references": [
                {"policy_id": "species_block:image.blocks.species:goblin", "variant": "v1"}
            ]
        },
        registry_path=path,
    )
    assert explicit == [{"policy_id": "species_block:image.blocks.species:goblin", "variant": "v1"}]

    with pytest.raises(ValueError) as error:
        policy_service._extract_registry_references(
            payload={"references": []},
            registry_path=path,
        )
    assert "content.references must be a non-empty list" in str(error.value)


@pytest.mark.unit
def test_extract_registry_references_deduplicates_legacy_paths(tmp_path: Path) -> None:
    """Registry extraction should dedupe repeated legacy path entries."""
    path = tmp_path / "species_registry.yaml"
    references = policy_service._extract_registry_references(
        payload={
            "entries": [
                {"block_path": "policies/image/blocks/species/goblin_v1.yaml"},
                {"block_path": "policies/image/blocks/species/goblin_v1.yaml"},
            ]
        },
        registry_path=path,
    )
    assert references == [
        {"policy_id": "species_block:image.blocks.species:goblin", "variant": "v1"}
    ]


@pytest.mark.unit
def test_normalize_reference_entries_rejects_invalid_shapes() -> None:
    """Reference normalizer should reject malformed list entries and missing fields."""
    with pytest.raises(ValueError) as non_object_error:
        policy_service._normalize_reference_entries(
            references=["bad-item"],
            policy_type="registry",
        )
    assert "must be an object with 'policy_id' and 'variant'" in str(non_object_error.value)

    with pytest.raises(ValueError) as missing_policy_error:
        policy_service._normalize_reference_entries(
            references=[{"variant": "v1"}],
            policy_type="registry",
        )
    assert ".policy_id is required" in str(missing_policy_error.value)

    with pytest.raises(ValueError) as missing_variant_error:
        policy_service._normalize_reference_entries(
            references=[{"policy_id": "species_block:image.blocks.species:goblin"}],
            policy_type="registry",
        )
    assert ".variant is required" in str(missing_variant_error.value)


@pytest.mark.unit
def test_collect_legacy_path_fields_skips_non_objects() -> None:
    """Legacy path collector should ignore non-dictionary entry rows."""
    values = policy_service._collect_legacy_path_fields_from_entries(
        entries=[None, "bad", {"block_path": "policies/image/blocks/species/goblin_v1.yaml"}]
    )
    assert values == ["policies/image/blocks/species/goblin_v1.yaml"]


@pytest.mark.unit
def test_policy_reference_from_legacy_path_maps_prompt_tone_and_clothing_paths() -> None:
    """Legacy path mapper should resolve prompt/tone/clothing policy references."""
    prompt_reference = policy_service._policy_reference_from_legacy_path(
        "policies/translation/prompts/ic/default_v1.txt"
    )
    assert prompt_reference == {
        "policy_id": "prompt:translation.prompts.ic:default",
        "variant": "v1",
    }

    tone_reference = policy_service._policy_reference_from_legacy_path(
        "policies/image/tone_profiles/ledger_engraving_v1.json"
    )
    assert tone_reference == {
        "policy_id": "tone_profile:image.tone_profiles:ledger_engraving",
        "variant": "v1",
    }

    clothing_reference = policy_service._policy_reference_from_legacy_path(
        "policies/image/blocks/clothing/environment/coastal_v1.txt"
    )
    assert clothing_reference == {
        "policy_id": "clothing_block:image.blocks.clothing.environment:coastal",
        "variant": "v1",
    }


@pytest.mark.unit
def test_validate_policy_variant_accepts_tone_profile_layer1_content(test_db) -> None:
    """Tone profile Layer 1 objects should accept non-empty ``prompt_block`` text."""
    result = policy_service.validate_policy_variant(
        policy_id="tone_profile:image.tone_profiles:ledger_engraving",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={"prompt_block": "Muted engraving style on archival texture."},
        validated_by="tester",
    )
    assert result.is_valid is True
    assert result.errors == []


@pytest.mark.unit
def test_validate_policy_variant_rejects_tone_profile_missing_prompt_block(test_db) -> None:
    """Tone profile Layer 1 objects should reject missing/empty ``prompt_block`` text."""
    result = policy_service.validate_policy_variant(
        policy_id="tone_profile:image.tone_profiles:ledger_engraving",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={"prompt_block": ""},
        validated_by="tester",
    )
    assert result.is_valid is False
    assert result.errors == ["tone_profile content.prompt_block must be a non-empty string"]


@pytest.mark.unit
def test_validate_policy_variant_accepts_clothing_block_layer1_content(test_db) -> None:
    """Clothing block Layer 1 objects should accept non-empty ``content.text`` payloads."""
    result = policy_service.validate_policy_variant(
        policy_id="clothing_block:image.blocks.clothing.environment:coastal",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={"text": "Salt-worn boots and weathered waxed coat."},
        validated_by="tester",
    )
    assert result.is_valid is True
    assert result.errors == []


@pytest.mark.unit
def test_validate_policy_variant_rejects_axis_bundle_missing_required_objects(test_db) -> None:
    """Axis bundle validation should require non-empty axes/thresholds/resolution objects."""
    result = policy_service.validate_policy_variant(
        policy_id="axis_bundle:axis.bundles:axis_core_v1",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={},
        validated_by="tester",
    )
    assert result.is_valid is False
    assert "axis_bundle content.axes must be a non-empty object" in result.errors
    assert "axis_bundle content.thresholds must be a non-empty object" in result.errors
    assert "axis_bundle content.resolution must be a non-empty object" in result.errors


@pytest.mark.unit
def test_validate_policy_variant_rejects_manifest_bundle_missing_manifest_object(test_db) -> None:
    """Manifest bundle validation should require non-empty manifest object payload."""
    result = policy_service.validate_policy_variant(
        policy_id=f"manifest_bundle:world.manifests:{constants.DEFAULT_WORLD_ID}",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={"manifest": ""},
        validated_by="tester",
    )
    assert result.is_valid is False
    assert result.errors == ["manifest_bundle content.manifest must be a non-empty object"]


@pytest.mark.unit
def test_validate_policy_variant_rejects_invalid_descriptor_layer_references(test_db) -> None:
    """Layer 2 validation should fail for missing/non-Layer-1 references."""
    _seed_descriptor_layer_variant(
        policy_key="existing_layer2",
        variant="v1",
        policy_version=1,
        references=[
            {
                "policy_id": _seed_species_variant(
                    policy_key="gnome", variant="v1", policy_version=1
                ),
                "variant": "v1",
            }
        ],
    )
    result = policy_service.validate_policy_variant(
        policy_id="descriptor_layer:image.descriptors:broken",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={
            "references": [
                {
                    "policy_id": "descriptor_layer:image.descriptors:existing_layer2",
                    "variant": "v1",
                },
                {
                    "policy_id": "species_block:image.blocks.species:missing",
                    "variant": "v404",
                },
            ]
        },
        validated_by="tester",
    )
    assert result.is_valid is False
    assert any("must reference a Layer 1 policy type" in error for error in result.errors)
    assert any("references missing Layer 1 variant" in error for error in result.errors)


@pytest.mark.unit
def test_validate_policy_variant_rejects_empty_descriptor_layer_references(test_db) -> None:
    """Layer 2 validation should require a non-empty references list."""
    result = policy_service.validate_policy_variant(
        policy_id="descriptor_layer:image.descriptors:empty_refs",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={},
        validated_by="tester",
    )
    assert result.is_valid is False
    assert result.errors == ["Layer 2 content.references must be a non-empty list."]


@pytest.mark.unit
def test_validate_policy_variant_rejects_malformed_descriptor_layer_reference_entries(
    test_db,
) -> None:
    """Layer 2 validation should reject malformed reference entry fields."""
    result = policy_service.validate_policy_variant(
        policy_id="descriptor_layer:image.descriptors:shape_errors",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={
            "references": [
                42,
                {"policy_id": "", "variant": "v1"},
                {"policy_id": "species_block:image.blocks.species:goblin", "variant": ""},
                {"policy_id": "not:a:valid:policy_id", "variant": "v1"},
            ]
        },
        validated_by="tester",
    )
    assert result.is_valid is False
    assert any("must be an object with policy_id and variant" in error for error in result.errors)
    assert any(".policy_id must be a non-empty string." in error for error in result.errors)
    assert any(".variant must be a non-empty string." in error for error in result.errors)
    assert any(".policy_id is invalid:" in error for error in result.errors)


@pytest.mark.unit
def test_set_policy_activation_wraps_audit_replay_read_errors(test_db, monkeypatch) -> None:
    """Replay consistency should map repository read failures to a stable service error."""
    policy_id = _seed_species_variant(policy_key="harpy", variant="v1", policy_version=1)
    monkeypatch.setattr(
        policy_service.policy_repo,
        "list_policy_activations",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("replay read failed")),
    )
    with pytest.raises(PolicyServiceError) as error:
        policy_service.set_policy_activation(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
            policy_id=policy_id,
            variant="v1",
            activated_by="tester",
        )
    assert error.value.code == "POLICY_AUDIT_REPLAY_READ_ERROR"


@pytest.mark.unit
def test_publish_scope_rejects_activation_pointer_to_missing_variant(test_db, monkeypatch) -> None:
    """Publish should fail when activation points at a missing policy row."""
    monkeypatch.setattr(
        policy_service,
        "resolve_effective_policy_activations",
        lambda scope: [
            {
                "policy_id": "species_block:image.blocks.species:goblin",
                "variant": "v404",
            }
        ],
    )
    monkeypatch.setattr(policy_service.policy_repo, "get_policy", lambda **kwargs: None)

    with pytest.raises(PolicyServiceError) as error:
        policy_service.publish_scope(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
            actor="tester",
        )
    assert error.value.code == "POLICY_PUBLISH_REFERENCE_MISSING"


@pytest.mark.unit
def test_publish_scope_is_deterministic_and_writes_artifact(test_db, monkeypatch, tmp_path) -> None:
    """Repeated publishes for equal activation state should keep stable hashes."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    policy_id = _seed_species_variant(policy_key="satyr", variant="v1", policy_version=1)
    policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
    )

    first = policy_service.publish_scope(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        actor="tester",
    )
    second = policy_service.publish_scope(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        actor="tester",
    )
    assert first["manifest"]["items_hash"] == second["manifest"]["items_hash"]
    assert first["manifest"]["manifest_hash"] == second["manifest"]["manifest_hash"]
    assert first["artifact"]["artifact_hash"] == second["artifact"]["artifact_hash"]
    assert first["artifact"]["artifact_path"] == second["artifact"]["artifact_path"]
    assert Path(first["artifact"]["artifact_path"]).exists()


@pytest.mark.unit
def test_get_publish_run_materializes_artifact_for_legacy_manifest(
    test_db, monkeypatch, tmp_path
) -> None:
    """Read path should normalize legacy manifests and write export artifact."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    run_id = policy_service.policy_repo.insert_publish_run(
        world_id=constants.DEFAULT_WORLD_ID,
        client_profile="",
        actor="tester",
        manifest={
            "world_id": constants.DEFAULT_WORLD_ID,
            "client_profile": None,
            "generated_at": "2026-03-11T12:00:00Z",
            "item_count": 1,
            "items": [
                {
                    "policy_id": "species_block:image.blocks.species:goblin",
                    "policy_type": "species_block",
                    "namespace": "image.blocks.species",
                    "policy_key": "goblin",
                    "variant": "v1",
                    "schema_version": "1.0",
                    "policy_version": 1,
                    "status": "candidate",
                    "content_hash": "hash-goblin-v1",
                    "updated_at": "2026-03-11T12:00:00Z",
                }
            ],
        },
        created_at="2026-03-11T12:00:00Z",
    )
    result = policy_service.get_publish_run(publish_run_id=run_id)
    assert result["publish_run_id"] == run_id
    assert result["manifest"]["items_hash"]
    assert result["manifest"]["manifest_hash"]
    artifact_path = Path(result["artifact"]["artifact_path"])
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["mirror_mode"] == "non_authoritative"
    assert payload["manifest_hash"] == result["manifest"]["manifest_hash"]


@pytest.mark.unit
def test_get_publish_run_normalizes_non_list_manifest_items(test_db, monkeypatch, tmp_path) -> None:
    """Legacy manifests with invalid items shape should normalize safely."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    run_id = policy_service.policy_repo.insert_publish_run(
        world_id=constants.DEFAULT_WORLD_ID,
        client_profile="",
        actor="tester",
        manifest={
            "world_id": constants.DEFAULT_WORLD_ID,
            "client_profile": None,
            "generated_at": "2026-03-11T12:00:00Z",
            "item_count": 99,
            "items": {"unexpected": True},
        },
        created_at="2026-03-11T12:00:00Z",
    )
    result = policy_service.get_publish_run(publish_run_id=run_id)
    assert result["manifest"]["item_count"] == 99
    assert result["manifest"]["items"] == []
    assert result["manifest"]["items_hash"]
    assert result["manifest"]["manifest_hash"]


@pytest.mark.unit
def test_publish_scope_is_not_affected_by_mirror_artifact_drift(
    test_db, monkeypatch, tmp_path
) -> None:
    """Tampering with export artifact must not affect runtime publish result."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    policy_id = _seed_species_variant(policy_key="nymph", variant="v1", policy_version=1)
    policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
    )
    first = policy_service.publish_scope(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        actor="tester",
    )
    artifact_path = Path(first["artifact"]["artifact_path"])
    artifact_path.write_text(
        json.dumps({"tampered": True}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    second = policy_service.publish_scope(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        actor="tester",
    )
    assert second["manifest"]["manifest_hash"] == first["manifest"]["manifest_hash"]
    restored_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert restored_payload["mirror_mode"] == "non_authoritative"
    assert restored_payload["manifest_hash"] == second["manifest"]["manifest_hash"]


@pytest.mark.unit
def test_publish_scope_surfaces_artifact_write_failures(test_db, monkeypatch, tmp_path) -> None:
    """Artifact write failures should raise a stable service error."""
    _set_temp_worlds_root(monkeypatch, tmp_path)
    policy_id = _seed_species_variant(policy_key="dryad", variant="v1", policy_version=1)
    policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
    )
    monkeypatch.setattr(
        Path,
        "write_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(PolicyServiceError) as error:
        policy_service.publish_scope(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
            actor="tester",
        )
    assert error.value.code == "POLICY_PUBLISH_ARTIFACT_WRITE_ERROR"


@pytest.mark.unit
def test_resolve_effective_prompt_template_prefers_configured_template_path(test_db) -> None:
    """Prompt resolution should follow configured template path when available."""
    default_prompt_id = _seed_prompt_variant(
        namespace="translation.prompts.ic",
        policy_key="default",
        variant="v1",
        policy_version=1,
        text="Default prompt template",
    )
    fallback_prompt_id = _seed_prompt_variant(
        namespace="translation.prompts.ic",
        policy_key="alt",
        variant="v1",
        policy_version=1,
        text="Alternate prompt template",
    )
    scope = ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="")
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=default_prompt_id,
        variant="v1",
        activated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=fallback_prompt_id,
        variant="v1",
        activated_by="tester",
    )

    result = policy_service.resolve_effective_prompt_template(
        scope=scope,
        preferred_template_path="policies/translation/prompts/ic/default_v1.txt",
    )
    assert result["policy_id"] == default_prompt_id
    assert result["variant"] == "v1"
    assert result["content_text"] == "Default prompt template"


@pytest.mark.unit
def test_resolve_effective_prompt_template_rejects_ambiguous_prompt_set(test_db) -> None:
    """Prompt resolution should fail when multiple effective prompts exist and no selector is set."""
    first_prompt_id = _seed_prompt_variant(
        namespace="translation.prompts.ic",
        policy_key="default",
        variant="v1",
        policy_version=1,
        text="Default prompt template",
    )
    second_prompt_id = _seed_prompt_variant(
        namespace="translation.prompts.ic",
        policy_key="alt",
        variant="v1",
        policy_version=1,
        text="Alternate prompt template",
    )
    scope = ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="")
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=first_prompt_id,
        variant="v1",
        activated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=second_prompt_id,
        variant="v1",
        activated_by="tester",
    )

    with pytest.raises(PolicyServiceError) as error:
        policy_service.resolve_effective_prompt_template(
            scope=scope,
            preferred_template_path=None,
        )

    assert error.value.code == "POLICY_EFFECTIVE_PROMPT_AMBIGUOUS"


@pytest.mark.unit
def test_resolve_effective_prompt_template_prefers_policy_id_selector(test_db) -> None:
    """Canonical policy_id selector should take precedence over template-path mapping."""
    default_prompt_id = _seed_prompt_variant(
        namespace="translation.prompts.ic",
        policy_key="default",
        variant="v1",
        policy_version=1,
        text="Default prompt template",
    )
    alternate_prompt_id = _seed_prompt_variant(
        namespace="translation.prompts.ic",
        policy_key="alt",
        variant="v1",
        policy_version=1,
        text="Alternate prompt template",
    )
    scope = ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="")
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=default_prompt_id,
        variant="v1",
        activated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=alternate_prompt_id,
        variant="v1",
        activated_by="tester",
    )

    result = policy_service.resolve_effective_prompt_template(
        scope=scope,
        preferred_policy_id=alternate_prompt_id,
        preferred_template_path="policies/translation/prompts/ic/default_v1.txt",
    )
    assert result["policy_id"] == alternate_prompt_id
    assert result["content_text"] == "Alternate prompt template"


@pytest.mark.unit
def test_resolve_effective_prompt_template_rejects_non_prompt_policy_selector(test_db) -> None:
    """Prompt resolver should reject selectors that are not prompt policy ids."""
    _seed_species_variant(policy_key="goblin", variant="v1", policy_version=1)
    scope = ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="")

    with pytest.raises(PolicyServiceError) as error:
        policy_service.resolve_effective_prompt_template(
            scope=scope,
            preferred_policy_id="species_block:image.blocks.species:goblin",
            preferred_template_path=None,
        )

    assert error.value.code == "POLICY_PROMPT_SELECTOR_INVALID"


@pytest.mark.unit
def test_resolve_effective_axis_bundle_happy_path(test_db) -> None:
    """Axis-bundle helper should resolve manifest and axis payloads via activation."""
    manifest_policy_id, axis_policy_id = _seed_effective_axis_bundle()

    resolved = policy_service.resolve_effective_axis_bundle(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="")
    )

    assert resolved.manifest_policy_id == manifest_policy_id
    assert resolved.axis_policy_id == axis_policy_id
    assert resolved.bundle_id == "axis_core_v1"
    assert resolved.bundle_version == "1"
    assert resolved.axis_variant == "v1"
    assert "entity.identity.gender" in resolved.required_runtime_inputs
    assert "entity.species" in resolved.required_runtime_inputs
    assert "entity.axes" in resolved.required_runtime_inputs
    assert resolved.axes_payload["axes"]["demeanor"]["ordering"]["values"] == ["timid", "bold"]
    assert isinstance(resolved.policy_hash, str) and resolved.policy_hash


@pytest.mark.unit
def test_resolve_effective_axis_bundle_requires_manifest_activation(test_db) -> None:
    """Missing manifest activation should raise a stable not-found contract error."""
    with pytest.raises(PolicyServiceError) as error:
        policy_service.resolve_effective_axis_bundle(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="")
        )
    assert error.value.code == "POLICY_EFFECTIVE_MANIFEST_NOT_FOUND"


@pytest.mark.unit
def test_resolve_effective_axis_bundle_detects_manifest_axis_version_mismatch(test_db) -> None:
    """Manifest-selected axis version must match activated axis variant."""
    _seed_effective_axis_bundle(bundle_version=1)
    _seed_effective_axis_bundle(bundle_version=2)
    # Force axis activation to a conflicting variant to assert mismatch behavior.
    axis_policy_id = "axis_bundle:axis.bundles:axis_core_v1"
    policy_service.set_policy_activation(
        scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile=""),
        policy_id=axis_policy_id,
        variant="v1",
        activated_by="tester",
    )

    with pytest.raises(PolicyServiceError) as error:
        policy_service.resolve_effective_axis_bundle(
            scope=ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="")
        )
    assert error.value.code == "POLICY_EFFECTIVE_AXIS_BUNDLE_VERSION_MISMATCH"


@pytest.mark.unit
def test_scope_segment_and_relative_world_root_helpers(monkeypatch) -> None:
    """Private helper branches should normalize scope and relative world roots."""
    relative_root = "tmp/worlds_relative_for_policy_tests"
    monkeypatch.setattr(policy_service.config.worlds, "worlds_root", relative_root)
    resolved = policy_service._resolve_world_root_path("alpha")  # noqa: SLF001
    assert resolved == policy_service.PROJECT_ROOT / relative_root / "alpha"  # noqa: SLF001
    assert policy_service._scope_segment("!!!") == "client_client"  # noqa: SLF001


@pytest.mark.unit
def test_validate_common_fields_and_policy_type_content_private_helpers() -> None:
    """Private helper branches should produce expected validation errors."""
    identity = policy_service.PolicyIdentity(
        policy_id="species_block::",
        policy_type="species_block",
        namespace="",
        policy_key="",
    )
    errors = policy_service._validate_common_fields(  # noqa: SLF001
        identity=identity,
        variant="",
        schema_version="",
        policy_version=0,
        status="bad-status",
        content={"text": "x"},
    )
    assert "namespace must not be empty" in errors
    assert "policy_key must not be empty" in errors
    assert "variant must not be empty" in errors
    assert "schema_version must not be empty" in errors
    assert "policy_version must be >= 1" in errors
    assert "status must be one of: draft, candidate, active, archived" in errors

    unsupported_identity = policy_service.PolicyIdentity(
        policy_id="image_block:image.blocks:scene",
        policy_type="image_block",
        namespace="image.blocks",
        policy_key="scene",
    )
    type_errors = policy_service._validate_policy_type_content(  # noqa: SLF001
        identity=unsupported_identity,
        content={"text": "x"},
    )
    assert type_errors == [
        (
            "Validation/writes currently support policy_type values: "
            "'species_block', 'clothing_block', 'prompt', 'tone_profile', "
            "'axis_bundle', 'manifest_bundle', 'descriptor_layer', 'registry'."
        )
    ]
