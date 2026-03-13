"""Core tests for canonical policy service facade and modules.

These tests cover the post-refactor DB-first policy service surface and assert
that removed legacy file-import APIs are no longer exposed.
"""

from __future__ import annotations

import pytest

from mud_server.db import constants
from mud_server.services import policy_service


@pytest.mark.unit
@pytest.mark.db
def test_validate_upsert_and_get_policy_roundtrip(test_db) -> None:
    """Canonical validation + upsert flow should persist retrievable variants."""
    policy_id = "species_block:image.blocks.species:goblin"

    validation = policy_service.validate_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="draft",
        content={"text": "Goblin canonical text."},
        validated_by="tester",
    )
    assert validation.is_valid is True

    saved = policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="draft",
        content={"text": "Goblin canonical text."},
        updated_by="tester",
    )
    assert saved["policy_id"] == policy_id

    fetched = policy_service.get_policy(policy_id=policy_id, variant="v1")
    assert fetched["content"]["text"] == "Goblin canonical text."


@pytest.mark.unit
@pytest.mark.db
def test_image_block_validate_upsert_and_get_policy_roundtrip(test_db) -> None:
    """Image blocks should validate, persist, and resolve through canonical APIs."""
    policy_id = "image_block:image.blocks.pose:standing_front"

    validation = policy_service.validate_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="draft",
        content={"text": "Subject is front-facing with neutral stance."},
        validated_by="tester",
    )
    assert validation.is_valid is True

    saved = policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="draft",
        content={"text": "Subject is front-facing with neutral stance."},
        updated_by="tester",
    )
    assert saved["policy_id"] == policy_id
    assert saved["policy_type"] == "image_block"

    fetched = policy_service.get_policy(policy_id=policy_id, variant="v1")
    assert fetched["content"]["text"] == "Subject is front-facing with neutral stance."


@pytest.mark.unit
@pytest.mark.db
def test_image_block_validation_rejects_empty_text(test_db) -> None:
    """Image block schema should require non-empty ``content.text`` strings."""
    invalid = policy_service.validate_policy_variant(
        policy_id="image_block:image.blocks.pose:standing_front",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="draft",
        content={"text": "   "},
        validated_by="tester",
    )
    assert invalid.is_valid is False
    assert "image_block content.text must be a non-empty string" in invalid.errors


@pytest.mark.unit
@pytest.mark.db
def test_layer2_reference_validation_rejects_non_layer1_reference(test_db) -> None:
    """Layer 2 payloads should reject references to non-Layer-1 policy types."""
    invalid = policy_service.validate_policy_variant(
        policy_id="descriptor_layer:image.descriptors:combat",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={
            "text": "Descriptor text.",
            "references": [
                {"policy_id": "descriptor_layer:image.descriptors:other", "variant": "v1"}
            ],
        },
        validated_by="tester",
    )
    assert invalid.is_valid is False
    assert any("must reference a Layer 1 policy type" in err for err in invalid.errors)


@pytest.mark.unit
@pytest.mark.db
def test_layer2_reference_validation_accepts_image_block_reference(test_db) -> None:
    """Layer 2 references should accept canonical ``image_block`` Layer 1 ids."""
    image_policy_id = "image_block:image.blocks.pose:standing_front"
    policy_service.upsert_policy_variant(
        policy_id=image_policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="active",
        content={"text": "Front-facing stance."},
        updated_by="tester",
    )

    valid = policy_service.validate_policy_variant(
        policy_id="descriptor_layer:image.descriptors:id_card",
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="candidate",
        content={
            "text": "Descriptor text.",
            "references": [
                {"policy_id": image_policy_id, "variant": "v1"},
            ],
        },
        validated_by="tester",
    )
    assert valid.is_valid is True
    assert valid.errors == []


@pytest.mark.unit
@pytest.mark.db
def test_activation_overlay_and_effective_variant_resolution(test_db) -> None:
    """Client-profile scope should overlay world scope by policy_id."""
    policy_id = "species_block:image.blocks.species:goblin"
    policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="active",
        content={"text": "World default goblin."},
        updated_by="tester",
    )
    policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant="v2",
        schema_version="1.0",
        policy_version=2,
        status="active",
        content={"text": "Mobile override goblin."},
        updated_by="tester",
    )

    world_scope = policy_service.ActivationScope(
        world_id=constants.DEFAULT_WORLD_ID, client_profile=""
    )
    mobile_scope = policy_service.ActivationScope(
        world_id=constants.DEFAULT_WORLD_ID,
        client_profile="mobile",
    )

    policy_service.set_policy_activation(
        scope=world_scope,
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=mobile_scope,
        policy_id=policy_id,
        variant="v2",
        activated_by="tester",
    )

    effective_mobile = policy_service.get_effective_policy_variant(
        scope=mobile_scope, policy_id=policy_id
    )
    assert effective_mobile is not None
    assert effective_mobile["variant"] == "v2"


@pytest.mark.unit
@pytest.mark.db
def test_resolve_effective_prompt_template_requires_policy_selector_when_ambiguous(test_db) -> None:
    """Multiple prompt activations should require explicit prompt policy id selection."""
    p1 = "prompt:translation.prompts.ic:default"
    p2 = "prompt:translation.prompts.ic:merchant"
    for idx, pid in enumerate((p1, p2), start=1):
        policy_service.upsert_policy_variant(
            policy_id=pid,
            variant="v1",
            schema_version="1.0",
            policy_version=idx,
            status="active",
            content={"text": f"Prompt {idx}"},
            updated_by="tester",
        )
        policy_service.set_policy_activation(
            scope=policy_service.ActivationScope(
                world_id=constants.DEFAULT_WORLD_ID, client_profile=""
            ),
            policy_id=pid,
            variant="v1",
            activated_by="tester",
        )

    with pytest.raises(policy_service.PolicyServiceError) as error:
        policy_service.resolve_effective_prompt_template(
            scope=policy_service.ActivationScope(
                world_id=constants.DEFAULT_WORLD_ID, client_profile=""
            ),
            preferred_policy_id=None,
        )
    assert error.value.code == "POLICY_EFFECTIVE_PROMPT_AMBIGUOUS"

    resolved = policy_service.resolve_effective_prompt_template(
        scope=policy_service.ActivationScope(
            world_id=constants.DEFAULT_WORLD_ID, client_profile=""
        ),
        preferred_policy_id=p1,
    )
    assert resolved["policy_id"] == p1


@pytest.mark.unit
@pytest.mark.db
def test_resolve_effective_axis_bundle_happy_path(test_db) -> None:
    """Axis bundle resolver should return manifest-selected active axis bundle payload."""
    world_id = constants.DEFAULT_WORLD_ID
    axis_policy_id = "axis_bundle:axis.bundles:default"
    manifest_policy_id = f"manifest_bundle:world.manifests:{world_id}"

    policy_service.upsert_policy_variant(
        policy_id=axis_policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="active",
        content={
            "axes": {"wealth": ["poor", "modest"]},
            "thresholds": {"wealth": {"poor": 0.4, "modest": 0.6}},
            "resolution": {"version": 1, "rules": []},
        },
        updated_by="tester",
    )
    policy_service.upsert_policy_variant(
        policy_id=manifest_policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="active",
        content={
            "manifest": {
                "axis": {"active_bundle": {"id": "default", "version": 1}},
                "image": {"composition": {"required_runtime_inputs": ["wealth"]}},
            }
        },
        updated_by="tester",
    )

    scope = policy_service.ActivationScope(world_id=world_id, client_profile="")
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=axis_policy_id,
        variant="v1",
        activated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=manifest_policy_id,
        variant="v1",
        activated_by="tester",
    )

    resolved = policy_service.resolve_effective_axis_bundle(scope=scope)
    assert resolved.axis_policy_id == axis_policy_id
    assert resolved.bundle_id == "default"
    assert "wealth" in resolved.required_runtime_inputs


@pytest.mark.unit
@pytest.mark.db
def test_publish_and_artifact_import_roundtrip(test_db, monkeypatch, tmp_path) -> None:
    """Publish artifact should roundtrip through import into canonical state."""
    monkeypatch.setenv("MUD_POLICY_EXPORTS_ROOT", str(tmp_path / "exports"))

    world_id = constants.DEFAULT_WORLD_ID
    scope = policy_service.ActivationScope(world_id=world_id, client_profile="")
    policy_id = "species_block:image.blocks.species:goblin"

    policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="active",
        content={"text": "Publish goblin."},
        updated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
    )

    published = policy_service.publish_scope(scope=scope, actor="tester")
    artifact_path = published["artifact"]["artifact_path"]
    with open(artifact_path, encoding="utf-8") as handle:
        artifact_payload = __import__("json").load(handle)

    imported = policy_service.import_published_artifact(
        artifact=artifact_payload,
        actor="importer",
        activate=True,
    )
    assert imported.error_count == 0
    assert imported.item_count >= 1


@pytest.mark.unit
@pytest.mark.db
def test_artifact_import_orders_layer1_before_layer2_reference_validation(test_db) -> None:
    """Artifact import should succeed even when Layer 2 rows appear first.

    This protects bootstrap/import workflows from false negatives caused by
    artifact row ordering when Layer 2 content references Layer 1 rows.
    """
    world_id = constants.DEFAULT_WORLD_ID
    species_policy_id = "species_block:image.blocks.species:goblin"
    image_policy_id = "image_block:image.blocks.pose:standing_front"
    descriptor_policy_id = "descriptor_layer:image.descriptors:id_card"

    artifact_payload = {
        "world_id": world_id,
        "client_profile": None,
        # Intentionally place Layer 2 before Layer 1 to assert importer ordering.
        "variants": [
            {
                "policy_id": descriptor_policy_id,
                "policy_type": "descriptor_layer",
                "namespace": "image.descriptors",
                "policy_key": "id_card",
                "variant": "v1",
                "schema_version": "1.0",
                "policy_version": 1,
                "status": "active",
                "content": {
                    "text": "Descriptor text.",
                    "references": [
                        {"policy_id": species_policy_id, "variant": "v1"},
                        {"policy_id": image_policy_id, "variant": "v1"},
                    ],
                },
            },
            {
                "policy_id": image_policy_id,
                "policy_type": "image_block",
                "namespace": "image.blocks.pose",
                "policy_key": "standing_front",
                "variant": "v1",
                "schema_version": "1.0",
                "policy_version": 1,
                "status": "active",
                "content": {"text": "Image block text."},
            },
            {
                "policy_id": species_policy_id,
                "policy_type": "species_block",
                "namespace": "image.blocks.species",
                "policy_key": "goblin",
                "variant": "v1",
                "schema_version": "1.0",
                "policy_version": 1,
                "status": "active",
                "content": {"text": "Goblin block text."},
            },
        ],
    }

    imported = policy_service.import_published_artifact(
        artifact=artifact_payload,
        actor="importer",
        activate=True,
    )

    assert imported.error_count == 0
    assert imported.imported_count == 3

    descriptor_row = policy_service.get_policy(policy_id=descriptor_policy_id, variant="v1")
    assert descriptor_row["content"]["references"][0]["policy_id"] == species_policy_id
    assert descriptor_row["content"]["references"][1]["policy_id"] == image_policy_id


@pytest.mark.unit
def test_parse_scope_supports_world_and_client_profile() -> None:
    """Scope parser should handle world-only and world+client forms."""
    world_only = policy_service.parse_scope(constants.DEFAULT_WORLD_ID)
    assert world_only.world_id == constants.DEFAULT_WORLD_ID
    assert world_only.client_profile == ""

    with_client = policy_service.parse_scope(f"{constants.DEFAULT_WORLD_ID}:mobile")
    assert with_client.world_id == constants.DEFAULT_WORLD_ID
    assert with_client.client_profile == "mobile"


@pytest.mark.unit
def test_legacy_policy_service_apis_are_removed() -> None:
    """Refactor should remove legacy file-import APIs from facade surface."""
    assert not hasattr(policy_service, "import_species_blocks_from_legacy_yaml")
    assert not hasattr(policy_service, "import_layer2_policies_from_legacy_files")
    assert not hasattr(policy_service, "import_tone_prompt_policies_from_legacy_files")
    assert not hasattr(policy_service, "import_clothing_block_policies_from_legacy_files")
    assert not hasattr(policy_service, "import_axis_manifest_policies_from_legacy_files")
    assert not hasattr(policy_service, "import_world_policies_from_legacy_files")
    assert not hasattr(policy_service, "policy_reference_from_legacy_path")
