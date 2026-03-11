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
            "'species_block', 'prompt', 'tone_profile', 'descriptor_layer', 'registry'."
        )
    ]
