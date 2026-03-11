"""Unit tests for ``mud_server.services.policy_service``.

These tests cover service-only behavior that is easier to validate without
round-tripping through HTTP:
- scope parsing edge cases
- policy-id parsing and validation errors
- rollback guardrails for policy/scope mismatch
"""

from __future__ import annotations

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
def test_publish_scope_rejects_activation_pointer_to_missing_variant(test_db, monkeypatch) -> None:
    """Publish should fail when activation points at a missing policy row."""
    monkeypatch.setattr(
        policy_service,
        "list_policy_activations",
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
        policy_id="prompt:image.prompts:scene",
        policy_type="prompt",
        namespace="image.prompts",
        policy_key="scene",
    )
    type_errors = policy_service._validate_policy_type_content(  # noqa: SLF001
        identity=unsupported_identity,
        content={"text": "x"},
    )
    assert type_errors == [
        "Phase 1 only supports writes/validation for policy_type='species_block'."
    ]
