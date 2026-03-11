"""Unit tests for ``mud_server.db.policy_repo``.

These tests intentionally focus on repository invariants:
- unique identity behavior for ``policy_id + variant``
- activation pointer uniqueness per scope
- audit/publish persistence behavior
"""

from __future__ import annotations

import pytest

from mud_server.db import policy_repo
from mud_server.db.errors import DatabaseWriteError


def _seed_species_policy_item(policy_key: str = "goblin") -> str:
    """Create a standard species policy identity and return its policy_id."""
    policy_id = f"species_block:image.blocks.species:{policy_key}"
    policy_repo.upsert_policy_item(
        policy_id=policy_id,
        policy_type="species_block",
        namespace="image.blocks.species",
        policy_key=policy_key,
    )
    return policy_id


@pytest.mark.db
def test_policy_variant_identity_is_unique_per_policy_and_variant(test_db) -> None:
    """Upsert should preserve unique identity for policy_id+variant."""
    policy_id = _seed_species_policy_item()

    first = policy_repo.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="draft",
        content={"text": "version one"},
        content_hash="hash-one",
        updated_at="2026-03-11T12:00:00Z",
        updated_by="tester",
    )
    assert first["policy_version"] == 1

    second = policy_repo.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=2,
        status="candidate",
        content={"text": "version two"},
        content_hash="hash-two",
        updated_at="2026-03-11T12:01:00Z",
        updated_by="tester",
    )
    assert second["policy_version"] == 2
    assert second["status"] == "candidate"

    rows = policy_repo.list_policies(
        policy_type="species_block",
        namespace="image.blocks.species",
        status=None,
    )
    assert len(rows) == 1
    assert rows[0]["policy_id"] == policy_id
    assert rows[0]["variant"] == "v1"
    assert rows[0]["policy_version"] == 2


@pytest.mark.db
def test_policy_activation_scope_overwrites_pointer_for_same_scope(test_db) -> None:
    """Activation pointer row should be unique per world/client/policy scope."""
    policy_id = _seed_species_policy_item()
    policy_repo.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="draft",
        content={"text": "v1"},
        content_hash="h1",
        updated_at="2026-03-11T12:00:00Z",
        updated_by="tester",
    )
    policy_repo.upsert_policy_variant(
        policy_id=policy_id,
        variant="v2",
        schema_version="1.0",
        policy_version=2,
        status="candidate",
        content={"text": "v2"},
        content_hash="h2",
        updated_at="2026-03-11T12:01:00Z",
        updated_by="tester",
    )

    first = policy_repo.set_policy_activation(
        world_id="pipeworks_web",
        client_profile="",
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
        activated_at="2026-03-11T12:02:00Z",
        rollback_of_activation_id=None,
    )
    assert first["variant"] == "v1"

    second = policy_repo.set_policy_activation(
        world_id="pipeworks_web",
        client_profile="",
        policy_id=policy_id,
        variant="v2",
        activated_by="tester",
        activated_at="2026-03-11T12:03:00Z",
        rollback_of_activation_id=None,
    )
    assert second["variant"] == "v2"

    active = policy_repo.list_policy_activations(world_id="pipeworks_web", client_profile="")
    assert len(active) == 1
    assert active[0]["policy_id"] == policy_id
    assert active[0]["variant"] == "v2"


@pytest.mark.db
def test_get_policy_without_variant_returns_latest_policy_version(test_db) -> None:
    """Read without variant should return highest policy_version row."""
    policy_id = _seed_species_policy_item("kobold")
    policy_repo.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="draft",
        content={"text": "v1"},
        content_hash="h1",
        updated_at="2026-03-11T12:00:00Z",
        updated_by="tester",
    )
    policy_repo.upsert_policy_variant(
        policy_id=policy_id,
        variant="v2",
        schema_version="1.0",
        policy_version=2,
        status="candidate",
        content={"text": "v2"},
        content_hash="h2",
        updated_at="2026-03-11T12:01:00Z",
        updated_by="tester",
    )

    latest = policy_repo.get_policy(policy_id=policy_id, variant=None)
    assert latest is not None
    assert latest["variant"] == "v2"
    assert latest["policy_version"] == 2


@pytest.mark.db
def test_set_policy_activation_rejects_missing_variant_reference(test_db) -> None:
    """Activation should fail when the referenced policy variant does not exist."""
    policy_id = _seed_species_policy_item("orc")

    with pytest.raises(DatabaseWriteError):
        policy_repo.set_policy_activation(
            world_id="pipeworks_web",
            client_profile="",
            policy_id=policy_id,
            variant="v999",
            activated_by="tester",
            activated_at="2026-03-11T12:02:00Z",
            rollback_of_activation_id=None,
        )


@pytest.mark.db
def test_activation_and_publish_runs_write_audit_rows(test_db) -> None:
    """Activation and publish operations should create retrievable history rows."""
    policy_id = _seed_species_policy_item("elf")
    policy_repo.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=1,
        status="active",
        content={"text": "elf"},
        content_hash="h1",
        updated_at="2026-03-11T12:00:00Z",
        updated_by="tester",
    )

    activation = policy_repo.set_policy_activation(
        world_id="pipeworks_web",
        client_profile="mobile",
        policy_id=policy_id,
        variant="v1",
        activated_by="tester",
        activated_at="2026-03-11T12:01:00Z",
        rollback_of_activation_id=None,
    )
    audit_event_id = activation["audit_event_id"]
    assert isinstance(audit_event_id, int)

    audit_event = policy_repo.get_activation_event(audit_event_id)
    assert audit_event is not None
    assert audit_event["policy_id"] == policy_id
    assert audit_event["variant"] == "v1"
    assert audit_event["client_profile"] == "mobile"

    run_id = policy_repo.insert_publish_run(
        world_id="pipeworks_web",
        client_profile="mobile",
        actor="tester",
        manifest={
            "world_id": "pipeworks_web",
            "client_profile": "mobile",
            "generated_at": "2026-03-11T12:02:00Z",
            "item_count": 1,
            "items": [{"policy_id": policy_id, "variant": "v1"}],
            "manifest_hash": "mh1",
        },
        created_at="2026-03-11T12:02:00Z",
    )
    assert run_id > 0
