"""Pydantic response models for canonical policy hash snapshot APIs."""

from __future__ import annotations

from pydantic import BaseModel


class PolicyHashDirectoryResponse(BaseModel):
    """One deterministic directory hash summary under the canonical policy root."""

    path: str
    file_count: int
    hash: str


class PolicyHashSnapshotResponse(BaseModel):
    """Top-level canonical policy hash snapshot payload."""

    hash_version: str
    canonical_root: str
    generated_at: str
    file_count: int
    root_hash: str
    directories: list[PolicyHashDirectoryResponse]
