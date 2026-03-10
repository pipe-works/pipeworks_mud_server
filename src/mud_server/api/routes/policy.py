"""Canonical policy hash snapshot endpoints."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Query
from pipeworks_ipc import compute_payload_hash

from mud_server.api.models_policy import PolicyHashDirectoryResponse, PolicyHashSnapshotResponse
from mud_server.core.engine import GameEngine

try:
    import pipeworks_ipc.hashing as ipc_hashing
except ImportError:  # pragma: no cover - import path is expected in normal runtime
    ipc_hashing = None

_HASH_VERSION = "policy_tree_hash_v1"
_DEFAULT_WORLD_ID = "pipeworks_web"
_SUPPORTED_SUFFIXES = {".txt", ".yaml", ".yml"}


@dataclass(frozen=True, slots=True)
class _PolicyEntry:
    """Minimal in-module entry used for deterministic tree hashing."""

    relative_path: str
    content_hash: str


def router(_engine: GameEngine) -> APIRouter:
    """Create policy router exposing canonical hash snapshot endpoints."""

    api = APIRouter(prefix="/api/policy", tags=["policy"])

    @api.get("/hash-snapshot", response_model=PolicyHashSnapshotResponse)
    async def hash_snapshot(
        world_id: str = Query(default=_DEFAULT_WORLD_ID, min_length=1),
    ) -> PolicyHashSnapshotResponse:
        """Return deterministic canonical policy tree hashes for one world."""

        policy_root = _canonical_policy_root(world_id)
        if not policy_root.exists() or not policy_root.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"Canonical policy root not found for world {world_id!r}: {policy_root}",
            )

        entries = _collect_policy_entries(policy_root)
        directories = _compute_directory_hashes(entries)
        generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        return PolicyHashSnapshotResponse(
            hash_version=_HASH_VERSION,
            canonical_root=str(policy_root),
            generated_at=generated_at,
            file_count=len(entries),
            root_hash=_compute_tree_hash(entries),
            directories=[
                PolicyHashDirectoryResponse(
                    path=directory.path,
                    file_count=directory.file_count,
                    hash=directory.hash,
                )
                for directory in directories
            ],
        )

    return api


def _canonical_policy_root(world_id: str) -> Path:
    """Resolve canonical policy root for one world id inside the mud-server repo."""

    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "data" / "worlds" / world_id / "policies"


def _collect_policy_entries(policy_root: Path) -> list[_PolicyEntry]:
    """Collect deterministic file hash entries for the canonical policy scope."""

    entries: list[_PolicyEntry] = []
    for path in sorted(policy_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue

        relative_path = path.relative_to(policy_root).as_posix()
        content_bytes = path.read_bytes()
        entries.append(
            _PolicyEntry(
                relative_path=relative_path,
                content_hash=_compute_file_hash(relative_path, content_bytes),
            )
        )

    return entries


def _compute_file_hash(relative_path: str, content_bytes: bytes) -> str:
    """Compute deterministic policy file hash using IPC helper when available."""

    helper = getattr(ipc_hashing, "compute_policy_file_hash", None) if ipc_hashing else None
    if callable(helper):
        return str(helper(relative_path, content_bytes))

    normalized_path = _normalize_relative_path(relative_path)
    return str(
        compute_payload_hash(
            {
                "hash_version": _HASH_VERSION,
                "relative_path": normalized_path,
                "content_bytes_hex": content_bytes.hex(),
            }
        )
    )


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
            "relative_path": _normalize_relative_path(entry.relative_path),
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
        current = PurePosixPath(_normalize_relative_path(entry.relative_path)).parent
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


def _normalize_relative_path(relative_path: str) -> str:
    """Normalize policy-relative paths into canonical POSIX shape."""

    normalized = PurePosixPath(relative_path.replace("\\", "/")).as_posix().lstrip("./")
    if normalized in {"", "."}:
        raise ValueError("Policy relative path must not be empty")
    if normalized.startswith("../") or "/../" in f"/{normalized}":
        raise ValueError(f"Policy relative path must not traverse upwards: {relative_path!r}")
    return normalized
