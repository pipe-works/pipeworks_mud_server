"""Tests for policy export root path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from mud_server.services.policy.paths import resolve_policy_export_root


@pytest.mark.unit
def test_resolve_policy_export_root_prefers_active_repo_sibling(
    monkeypatch, tmp_path: Path
) -> None:
    """Resolver should prefer the sibling of the cwd repo over stale install paths."""
    active_repo_root = tmp_path / "active_repo"
    (active_repo_root / "src" / "mud_server").mkdir(parents=True, exist_ok=True)
    (active_repo_root / "pyproject.toml").write_text("[project]\nname='pipeworks_mud_server'\n")

    cwd_sibling_exports = tmp_path / "pipe-works-world-policies"
    cwd_sibling_exports.mkdir(parents=True, exist_ok=True)

    stale_project_root = tmp_path / "stale_install" / "pipeworks_mud_server"
    stale_project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("MUD_POLICY_EXPORTS_ROOT", raising=False)
    monkeypatch.setattr("mud_server.services.policy.paths.PROJECT_ROOT", stale_project_root)
    monkeypatch.chdir(active_repo_root)

    assert resolve_policy_export_root() == cwd_sibling_exports.resolve()
