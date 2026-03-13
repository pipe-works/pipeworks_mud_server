"""API tests for canonical DB-backed policy hash snapshot endpoint."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mud_server.api.routes import policy as policy_routes
from mud_server.db import constants, database
from mud_server.services import policy_service


def _session_id_for(username: str) -> str:
    """Create and return a deterministic test session id for ``username``."""

    session_id = f"session-{username}"
    assert database.create_session(username, session_id) is True
    return session_id


def _seed_effective_policy(
    *,
    policy_id: str,
    variant: str,
    content: dict,
) -> None:
    """Upsert and activate one policy variant for default world scope."""

    scope = policy_service.ActivationScope(world_id=constants.DEFAULT_WORLD_ID, client_profile="")
    policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant=variant,
        schema_version="1.0",
        policy_version=1,
        status="active",
        content=content,
        updated_by="tester",
    )
    policy_service.set_policy_activation(
        scope=scope,
        policy_id=policy_id,
        variant=variant,
        activated_by="tester",
    )


@pytest.mark.api
@pytest.mark.db
def test_hash_snapshot_is_deterministic_and_db_scoped(test_client, db_with_users) -> None:
    """Snapshots should be deterministic for unchanged canonical DB state."""

    _seed_effective_policy(
        policy_id="species_block:image.blocks.species:goblin",
        variant="v1",
        content={"text": "goblin text"},
    )
    _seed_effective_policy(
        policy_id="prompt:translation.prompts.ic:default",
        variant="v1",
        content={"text": "prompt text"},
    )

    session_id = _session_id_for("testadmin")
    first = test_client.get("/api/policy/hash-snapshot", params={"session_id": session_id})
    second = test_client.get("/api/policy/hash-snapshot", params={"session_id": session_id})

    assert first.status_code == 200
    assert second.status_code == 200

    first_payload = first.json()
    second_payload = second.json()

    assert first_payload["hash_version"] == "policy_db_snapshot_hash_v2"
    assert first_payload["canonical_root"] == "canonical_db://pipeworks_web/effective-activations"
    assert first_payload["file_count"] == 2
    assert first_payload["root_hash"] == second_payload["root_hash"]

    directory_paths = {entry["path"] for entry in first_payload["directories"]}
    assert "species_block" in directory_paths
    assert "prompt" in directory_paths


@pytest.mark.api
@pytest.mark.db
def test_hash_snapshot_changes_after_policy_content_change(test_client, db_with_users) -> None:
    """Root hash should change when canonical policy content hash changes."""

    policy_id = "species_block:image.blocks.species:goblin"
    _seed_effective_policy(
        policy_id=policy_id,
        variant="v1",
        content={"text": "scene one"},
    )

    session_id = _session_id_for("testadmin")
    first_hash = test_client.get(
        "/api/policy/hash-snapshot", params={"session_id": session_id}
    ).json()["root_hash"]

    policy_service.upsert_policy_variant(
        policy_id=policy_id,
        variant="v1",
        schema_version="1.0",
        policy_version=2,
        status="active",
        content={"text": "scene one updated"},
        updated_by="tester",
    )

    second_hash = test_client.get(
        "/api/policy/hash-snapshot", params={"session_id": session_id}
    ).json()["root_hash"]

    assert first_hash != second_hash


@pytest.mark.api
@pytest.mark.db
def test_hash_snapshot_returns_404_when_world_is_missing(test_client, db_with_users) -> None:
    """Endpoint should return 404 for unknown worlds."""

    session_id = _session_id_for("testadmin")
    response = test_client.get(
        "/api/policy/hash-snapshot",
        params={"session_id": session_id, "world_id": "no_such_world"},
    )

    assert response.status_code == 404


@pytest.mark.api
@pytest.mark.db
@pytest.mark.parametrize("username", ["testplayer", "testbuilder"])
def test_hash_snapshot_rejects_non_admin_roles(
    test_client,
    db_with_users,
    username: str,
) -> None:
    """Hash snapshot route should reject player/worldbuilder sessions."""

    session_id = _session_id_for(username)
    response = test_client.get("/api/policy/hash-snapshot", params={"session_id": session_id})

    assert response.status_code == 403
    assert "admin or superuser" in response.json()["detail"]


@pytest.mark.api
@pytest.mark.db
def test_hash_snapshot_allows_superuser_role(test_client, db_with_users) -> None:
    """Hash snapshot route should allow superuser sessions."""

    _seed_effective_policy(
        policy_id="species_block:image.blocks.species:goblin",
        variant="v1",
        content={"text": "goblin text"},
    )

    session_id = _session_id_for("testsuperuser")
    response = test_client.get("/api/policy/hash-snapshot", params={"session_id": session_id})

    assert response.status_code == 200
    assert response.json()["file_count"] == 1


@pytest.mark.api
@pytest.mark.db
def test_hash_snapshot_requires_session_id_query_param(
    test_client,
    db_with_users,
) -> None:
    """Hash snapshot route should reject requests that omit ``session_id``."""

    response = test_client.get("/api/policy/hash-snapshot")
    assert response.status_code == 422


@pytest.mark.api
def test_policy_hash_helpers_use_ipc_branch_when_helpers_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directory/tree helpers should switch to IPC helpers when available."""

    class FakePolicyHashEntry:
        def __init__(self, *, relative_path: str, content_hash: str) -> None:
            self.relative_path = relative_path
            self.content_hash = content_hash

    fake_hashing = SimpleNamespace(
        PolicyHashEntry=FakePolicyHashEntry,
        compute_policy_tree_hash=lambda entries: f"tree::{len(entries)}",
        compute_policy_directory_hashes=lambda entries: [
            SimpleNamespace(path="species_block", file_count=len(entries), hash="dir::hash")
        ],
    )
    monkeypatch.setattr(policy_routes, "ipc_hashing", fake_hashing)

    entries = [
        policy_routes._PolicyEntry(
            relative_path="species_block/image/blocks/species/goblin/v1.json",
            content_hash="h1",
        ),
    ]
    assert policy_routes._compute_tree_hash(entries) == "tree::1"

    directories = policy_routes._compute_directory_hashes(entries)
    assert directories == [
        policy_routes.PolicyHashDirectoryResponse(
            path="species_block", file_count=1, hash="dir::hash"
        )
    ]


@pytest.mark.api
def test_entry_path_from_policy_row_is_deterministic() -> None:
    """Pseudo-path builder should produce a stable canonical DB snapshot path."""

    relative = policy_routes._entry_path_from_policy_row(
        {
            "policy_type": "species_block",
            "namespace": "image.blocks.species",
            "policy_key": "goblin",
            "variant": "v1",
        }
    )

    assert relative == "species_block/image/blocks/species/goblin/v1.json"
