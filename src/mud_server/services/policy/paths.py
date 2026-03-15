"""Filesystem path resolution helpers for policy publish/import workflows."""

from __future__ import annotations

import os
from pathlib import Path

from mud_server.config import PROJECT_ROOT

from .constants import _POLICY_EXPORT_REPO_NAME, _POLICY_EXPORT_ROOT_ENV


def resolve_policy_export_root(*, cwd: Path | None = None) -> Path:
    """Resolve the policy export repository root.

    Resolution order:
    1. ``MUD_POLICY_EXPORTS_ROOT`` environment variable
    2. sibling repo next to the active CLI repo root (derived from ``cwd``)
    3. sibling repo next to ``PROJECT_ROOT`` (historical default)
    """
    configured_root = os.getenv(_POLICY_EXPORT_ROOT_ENV, "").strip()
    if configured_root:
        root = Path(configured_root)
        if not root.is_absolute():
            root = (PROJECT_ROOT / root).resolve()
        return root

    active_cwd = (cwd or Path.cwd()).resolve()
    cwd_repo_root = _resolve_repo_root_from_cwd(active_cwd)

    candidates: list[Path] = []
    if cwd_repo_root is not None:
        candidates.append((cwd_repo_root.parent / _POLICY_EXPORT_REPO_NAME).resolve())
    candidates.append((PROJECT_ROOT.parent / _POLICY_EXPORT_REPO_NAME).resolve())

    deduped: list[Path] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)

    for candidate in deduped:
        if candidate.exists():
            return candidate
    return deduped[0]


def _resolve_repo_root_from_cwd(start: Path) -> Path | None:
    """Locate repository root by walking up from ``start``."""
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src" / "mud_server").is_dir():
            return candidate
    return None
