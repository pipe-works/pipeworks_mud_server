"""Canonical policy hash snapshot endpoints.

This route now snapshots canonical DB policy state (effective Layer 3
activations + selected policy variants) rather than filesystem trees.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Query
from pipeworks_ipc import compute_payload_hash

from mud_server.api.auth import validate_session
from mud_server.api.models_policy import PolicyHashDirectoryResponse, PolicyHashSnapshotResponse
from mud_server.core.engine import GameEngine
from mud_server.services import policy_service

try:
    import pipeworks_ipc.hashing as ipc_hashing
except ImportError:  # pragma: no cover - import path is expected in normal runtime
    ipc_hashing = None

_HASH_VERSION = "policy_db_snapshot_hash_v2"
_DEFAULT_WORLD_ID = "pipeworks_web"
_ADMIN_OR_SUPERUSER_ROLES = {"admin", "superuser"}


@dataclass(frozen=True, slots=True)
class _PolicyEntry:
    """Minimal in-module entry used for deterministic snapshot hashing."""

    relative_path: str
    content_hash: str


def router(_engine: GameEngine) -> APIRouter:
    """Create policy router exposing canonical hash snapshot endpoints."""

    api = APIRouter(prefix="/api/policy", tags=["policy"])

    @api.get("/hash-snapshot", response_model=PolicyHashSnapshotResponse)
    async def hash_snapshot(
        session_id: str = Query(min_length=1),
        world_id: str = Query(default=_DEFAULT_WORLD_ID, min_length=1),
    ) -> PolicyHashSnapshotResponse:
        """Return deterministic canonical DB policy hashes for one world scope."""
        _require_policy_hash_snapshot_role(session_id)

        entries = _collect_policy_entries(world_id=world_id)
        directories = _compute_directory_hashes(entries)
        generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        return PolicyHashSnapshotResponse(
            hash_version=_HASH_VERSION,
            canonical_root=f"canonical_db://{world_id}/effective-activations",
            generated_at=generated_at,
            file_count=len(entries),
            root_hash=_compute_tree_hash(entries),
            directories=directories,
        )

    return api


def _require_policy_hash_snapshot_role(session_id: str) -> str:
    """Validate session and enforce admin/superuser role for hash snapshots."""

    _user_id, _username, role = validate_session(session_id)
    if role not in _ADMIN_OR_SUPERUSER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Policy hash snapshot endpoint requires admin or superuser role.",
        )
    return role


def _collect_policy_entries(*, world_id: str) -> list[_PolicyEntry]:
    """Collect deterministic effective-policy entries for one world scope.

    The snapshot intentionally hashes effective active variants for the world
    default scope (``client_profile=''``). This matches runtime default lookup
    semantics and keeps drift checks focused on canonical activation state.
    """

    scope = policy_service.ActivationScope(world_id=world_id, client_profile="")
    try:
        effective_rows = policy_service.resolve_effective_policy_activations(scope=scope)
    except policy_service.PolicyServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    entries: list[_PolicyEntry] = []
    for activation in effective_rows:
        policy_id = str(activation.get("policy_id") or "").strip()
        variant = str(activation.get("variant") or "").strip()
        if not policy_id or not variant:
            continue

        row = policy_service.get_policy(policy_id=policy_id, variant=variant)
        relative_path = _entry_path_from_policy_row(row)
        entries.append(
            _PolicyEntry(
                relative_path=relative_path,
                content_hash=str(row.get("content_hash") or ""),
            )
        )

    entries.sort(key=lambda entry: entry.relative_path)
    return entries


def _entry_path_from_policy_row(row: dict[str, object]) -> str:
    """Build a deterministic pseudo-path for one canonical policy variant row."""

    policy_type = str(row.get("policy_type") or "unknown")
    namespace = str(row.get("namespace") or "unknown").replace(".", "/")
    policy_key = str(row.get("policy_key") or "unknown")
    variant = str(row.get("variant") or "unknown")
    return f"{policy_type}/{namespace}/{policy_key}/{variant}.json"


def _compute_tree_hash(entries: list[_PolicyEntry]) -> str:
    """Compute deterministic tree hash using IPC helper when available."""

    helper = getattr(ipc_hashing, "compute_policy_tree_hash", None) if ipc_hashing else None
    entry_cls = getattr(ipc_hashing, "PolicyHashEntry", None) if ipc_hashing else None
    if callable(helper) and entry_cls is not None:
        typed_entries = [
            entry_cls(relative_path=entry.relative_path, content_hash=entry.content_hash)
            for entry in entries
        ]
        return str(helper(typed_entries))

    payload_entries = [
        {
            "relative_path": entry.relative_path,
            "content_hash": entry.content_hash,
        }
        for entry in entries
    ]
    payload_entries.sort(key=lambda item: str(item["relative_path"]))
    return str(
        compute_payload_hash(
            {
                "hash_version": _HASH_VERSION,
                "entries": payload_entries,
            }
        )
    )


def _compute_directory_hashes(entries: list[_PolicyEntry]) -> list[PolicyHashDirectoryResponse]:
    """Compute deterministic directory subtree hashes using IPC helper when available."""

    helper = getattr(ipc_hashing, "compute_policy_directory_hashes", None) if ipc_hashing else None
    entry_cls = getattr(ipc_hashing, "PolicyHashEntry", None) if ipc_hashing else None
    if callable(helper) and entry_cls is not None:
        typed_entries = [
            entry_cls(relative_path=entry.relative_path, content_hash=entry.content_hash)
            for entry in entries
        ]
        directory_entries = helper(typed_entries)
        return [
            PolicyHashDirectoryResponse(
                path=str(entry.path),
                file_count=int(entry.file_count),
                hash=str(entry.hash),
            )
            for entry in directory_entries
        ]

    grouped: dict[str, list[_PolicyEntry]] = defaultdict(list)
    for entry in entries:
        current = PurePosixPath(entry.relative_path).parent
        while True:
            directory = current.as_posix()
            grouped[directory].append(entry)
            if directory == ".":
                break
            current = current.parent

    results: list[PolicyHashDirectoryResponse] = []
    for directory, directory_entries in grouped.items():
        if directory == ".":
            continue
        results.append(
            PolicyHashDirectoryResponse(
                path=directory,
                file_count=len(directory_entries),
                hash=_compute_tree_hash(directory_entries),
            )
        )

    return sorted(results, key=lambda entry: entry.path)
