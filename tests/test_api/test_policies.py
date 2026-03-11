"""API tests for canonical policy-object endpoints."""

from __future__ import annotations

from urllib.parse import quote

import pytest

from mud_server.db import constants, database


def _session_id_for(username: str) -> str:
    """Create and return a deterministic test session id for ``username``."""
    session_id = f"session-{username}"
    assert database.create_session(username, session_id) is True
    return session_id


def _species_payload(
    *, text: str, policy_version: int = 1, status: str = "draft"
) -> dict[str, object]:
    """Build a canonical ``species_block`` request body."""
    return {
        "schema_version": "1.0",
        "policy_version": policy_version,
        "status": status,
        "content": {"text": text},
    }


@pytest.mark.api
def test_species_policy_validate_upsert_get_and_list(test_client, db_with_users) -> None:
    """Species pilot should support validate->upsert->read/list flow."""
    session_id = _session_id_for("testbuilder")
    policy_id = "species_block:image.blocks.species:goblin"
    encoded_id = quote(policy_id, safe="")

    validate_response = test_client.post(
        f"/api/policies/{encoded_id}/validate",
        params={"session_id": session_id, "variant": "v1"},
        json=_species_payload(text="A canonical goblin species description."),
    )
    assert validate_response.status_code == 200
    validation_payload = validate_response.json()
    assert validation_payload["is_valid"] is True
    assert validation_payload["errors"] == []
    assert validation_payload["content_hash"]

    upsert_response = test_client.put(
        f"/api/policies/{encoded_id}/variants/v1",
        params={"session_id": session_id},
        json=_species_payload(text="A canonical goblin species description."),
    )
    assert upsert_response.status_code == 200
    upsert_payload = upsert_response.json()
    assert upsert_payload["policy_id"] == policy_id
    assert upsert_payload["policy_type"] == "species_block"
    assert upsert_payload["namespace"] == "image.blocks.species"
    assert upsert_payload["policy_key"] == "goblin"
    assert upsert_payload["variant"] == "v1"

    get_response = test_client.get(
        f"/api/policies/{encoded_id}",
        params={"session_id": session_id, "variant": "v1"},
    )
    assert get_response.status_code == 200
    assert get_response.json()["content"]["text"] == "A canonical goblin species description."

    list_response = test_client.get(
        "/api/policies",
        params={
            "session_id": session_id,
            "policy_type": "species_block",
            "namespace": "image.blocks.species",
            "status": "draft",
        },
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload["items"]) == 1
    assert list_payload["items"][0]["policy_id"] == policy_id


@pytest.mark.api
def test_species_policy_validation_rejects_empty_text(test_client, db_with_users) -> None:
    """Species pilot validation should reject empty content.text."""
    session_id = _session_id_for("testbuilder")
    policy_id = "species_block:image.blocks.species:goblin"
    encoded_id = quote(policy_id, safe="")

    upsert_response = test_client.put(
        f"/api/policies/{encoded_id}/variants/v1",
        params={"session_id": session_id},
        json=_species_payload(text="   "),
    )
    assert upsert_response.status_code == 422
    payload = upsert_response.json()
    assert payload["code"] == "POLICY_VALIDATION_ERROR"
    assert "species_block content.text must be a non-empty string" in payload["detail"]


@pytest.mark.api
def test_policy_activation_and_rollback_flow(test_client, db_with_users) -> None:
    """Activation should be scope-based and rollback should restore prior variant."""
    session_id = _session_id_for("testbuilder")
    policy_id = "species_block:image.blocks.species:goblin"
    encoded_id = quote(policy_id, safe="")

    for policy_version, variant in ((1, "v1"), (2, "v2")):
        write_response = test_client.put(
            f"/api/policies/{encoded_id}/variants/{variant}",
            params={"session_id": session_id},
            json=_species_payload(
                text=f"Goblin policy {variant}",
                policy_version=policy_version,
                status="candidate",
            ),
        )
        assert write_response.status_code == 200

    activation_v1 = test_client.post(
        "/api/policy-activations",
        params={"session_id": session_id},
        json={
            "world_id": constants.DEFAULT_WORLD_ID,
            "policy_id": policy_id,
            "variant": "v1",
        },
    )
    assert activation_v1.status_code == 200
    activation_v1_payload = activation_v1.json()
    assert activation_v1_payload["variant"] == "v1"
    assert activation_v1_payload["audit_event_id"] is not None

    activation_v2 = test_client.post(
        "/api/policy-activations",
        params={"session_id": session_id},
        json={
            "world_id": constants.DEFAULT_WORLD_ID,
            "policy_id": policy_id,
            "variant": "v2",
        },
    )
    assert activation_v2.status_code == 200
    assert activation_v2.json()["variant"] == "v2"

    rollback_response = test_client.post(
        "/api/policy-activations",
        params={"session_id": session_id},
        json={
            "world_id": constants.DEFAULT_WORLD_ID,
            "policy_id": policy_id,
            "variant": "v2",
            "rollback_of_activation_id": activation_v1_payload["audit_event_id"],
        },
    )
    assert rollback_response.status_code == 200
    rollback_payload = rollback_response.json()
    assert rollback_payload["variant"] == "v1"
    assert rollback_payload["rollback_of_activation_id"] == activation_v1_payload["audit_event_id"]

    list_response = test_client.get(
        "/api/policy-activations",
        params={"session_id": session_id, "scope": constants.DEFAULT_WORLD_ID},
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["world_id"] == constants.DEFAULT_WORLD_ID
    assert list_payload["client_profile"] is None
    assert len(list_payload["items"]) == 1
    assert list_payload["items"][0]["variant"] == "v1"


@pytest.mark.api
def test_policy_publish_returns_deterministic_manifest(test_client, db_with_users) -> None:
    """Publish should emit manifest rows based on active scope pointers."""
    session_id = _session_id_for("testbuilder")
    policy_id = "species_block:image.blocks.species:goblin"
    encoded_id = quote(policy_id, safe="")

    write_response = test_client.put(
        f"/api/policies/{encoded_id}/variants/v1",
        params={"session_id": session_id},
        json=_species_payload(text="Active goblin variant", status="active"),
    )
    assert write_response.status_code == 200

    activation_response = test_client.post(
        "/api/policy-activations",
        params={"session_id": session_id},
        json={
            "world_id": constants.DEFAULT_WORLD_ID,
            "policy_id": policy_id,
            "variant": "v1",
        },
    )
    assert activation_response.status_code == 200

    publish_response = test_client.post(
        "/api/policy-publish",
        params={"session_id": session_id},
        json={"world_id": constants.DEFAULT_WORLD_ID},
    )
    assert publish_response.status_code == 200
    payload = publish_response.json()
    assert payload["publish_run_id"] > 0
    manifest = payload["manifest"]
    assert manifest["world_id"] == constants.DEFAULT_WORLD_ID
    assert manifest["item_count"] == 1
    assert manifest["manifest_hash"]
    assert manifest["items"][0]["policy_id"] == policy_id


@pytest.mark.api
def test_policy_upsert_rejects_invalid_policy_id_shape(test_client, db_with_users) -> None:
    """Route should return contract error when ``policy_id`` format is invalid."""
    session_id = _session_id_for("testbuilder")
    invalid_policy_id = quote("species_block:image.blocks.species", safe="")

    response = test_client.put(
        f"/api/policies/{invalid_policy_id}/variants/v1",
        params={"session_id": session_id},
        json=_species_payload(text="invalid id shape"),
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "POLICY_ID_INVALID"


@pytest.mark.api
def test_policy_upsert_rejects_unsupported_policy_type(test_client, db_with_users) -> None:
    """Route should reject unknown policy types before write."""
    session_id = _session_id_for("testbuilder")
    policy_id = quote("unknown_type:image.blocks.species:goblin", safe="")

    response = test_client.put(
        f"/api/policies/{policy_id}/variants/v1",
        params={"session_id": session_id},
        json=_species_payload(text="invalid type"),
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "POLICY_TYPE_UNSUPPORTED"


@pytest.mark.api
def test_policy_get_without_variant_returns_latest_policy_version(
    test_client, db_with_users
) -> None:
    """GET without variant should return the newest policy_version row."""
    session_id = _session_id_for("testbuilder")
    policy_id = "species_block:image.blocks.species:kobold"
    encoded_id = quote(policy_id, safe="")

    first_write = test_client.put(
        f"/api/policies/{encoded_id}/variants/v1",
        params={"session_id": session_id},
        json=_species_payload(text="v1", policy_version=1),
    )
    assert first_write.status_code == 200

    second_write = test_client.put(
        f"/api/policies/{encoded_id}/variants/v2",
        params={"session_id": session_id},
        json=_species_payload(text="v2", policy_version=2, status="candidate"),
    )
    assert second_write.status_code == 200

    get_latest = test_client.get(f"/api/policies/{encoded_id}", params={"session_id": session_id})
    assert get_latest.status_code == 200
    payload = get_latest.json()
    assert payload["variant"] == "v2"
    assert payload["policy_version"] == 2


@pytest.mark.api
def test_policy_activation_rejects_unknown_world_scope(test_client, db_with_users) -> None:
    """Activation should return a world-not-found error for unknown world scope."""
    session_id = _session_id_for("testbuilder")
    policy_id = "species_block:image.blocks.species:goblin"
    encoded_id = quote(policy_id, safe="")

    write_response = test_client.put(
        f"/api/policies/{encoded_id}/variants/v1",
        params={"session_id": session_id},
        json=_species_payload(text="scope test"),
    )
    assert write_response.status_code == 200

    activation_response = test_client.post(
        "/api/policy-activations",
        params={"session_id": session_id},
        json={
            "world_id": "unknown_world",
            "policy_id": policy_id,
            "variant": "v1",
        },
    )
    assert activation_response.status_code == 404
    payload = activation_response.json()
    assert payload["code"] == "POLICY_WORLD_NOT_FOUND"
