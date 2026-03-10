"""API tests for canonical policy hash snapshot endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest

from mud_server.api.routes import policy as policy_routes


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 text fixture data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.mark.api
def test_hash_snapshot_is_deterministic_and_filters_file_scope(
    test_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hash snapshots should be deterministic and include only canonical file suffixes."""

    policy_root = tmp_path / "data" / "worlds" / "pipeworks_web" / "policies"
    _write_text(policy_root / "image" / "prompts" / "scene.txt", "scene one")
    _write_text(policy_root / "image" / "blocks" / "species" / "goblin.yaml", "text: goblin")
    _write_text(policy_root / "translation" / "ic" / "prompt.yml", "text: prompt")
    _write_text(policy_root / "image" / ".DS_Store", "ignored")
    _write_text(policy_root / "image" / "notes.md", "ignored")

    monkeypatch.setattr(policy_routes, "_canonical_policy_root", lambda _world_id: policy_root)

    first = test_client.get("/api/policy/hash-snapshot")
    second = test_client.get("/api/policy/hash-snapshot")

    assert first.status_code == 200
    assert second.status_code == 200

    first_payload = first.json()
    second_payload = second.json()

    assert first_payload["hash_version"] == "policy_tree_hash_v1"
    assert first_payload["canonical_root"] == str(policy_root)
    assert first_payload["file_count"] == 3
    assert first_payload["root_hash"] == second_payload["root_hash"]

    directory_paths = [entry["path"] for entry in first_payload["directories"]]
    assert "image" in directory_paths
    assert "image/prompts" in directory_paths
    assert "translation" in directory_paths


@pytest.mark.api
def test_hash_snapshot_changes_after_policy_content_change(
    test_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Root hash should change when canonical policy content changes."""

    policy_root = tmp_path / "data" / "worlds" / "pipeworks_web" / "policies"
    target_file = policy_root / "image" / "prompts" / "scene.txt"
    _write_text(target_file, "scene one")

    monkeypatch.setattr(policy_routes, "_canonical_policy_root", lambda _world_id: policy_root)

    first_hash = test_client.get("/api/policy/hash-snapshot").json()["root_hash"]
    _write_text(target_file, "scene one updated")
    second_hash = test_client.get("/api/policy/hash-snapshot").json()["root_hash"]

    assert first_hash != second_hash


@pytest.mark.api
def test_hash_snapshot_returns_404_when_canonical_root_is_missing(
    test_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Endpoint should return 404 for worlds without canonical policy roots."""

    missing_root = tmp_path / "missing" / "policies"
    monkeypatch.setattr(policy_routes, "_canonical_policy_root", lambda _world_id: missing_root)

    response = test_client.get("/api/policy/hash-snapshot")

    assert response.status_code == 404
    assert "Canonical policy root not found" in response.json()["detail"]
