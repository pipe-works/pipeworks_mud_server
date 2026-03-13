"""Deterministic hashing helpers for policy service payloads."""

from __future__ import annotations

from typing import Any

from pipeworks_ipc import compute_payload_hash


def compute_content_hash(*, policy_id: str, variant: str, content: dict[str, Any]) -> str:
    """Return deterministic hash for one canonical policy variant payload.

    Identity and variant are included in the hash envelope so two policies with
    identical content still hash differently at contract level.
    """
    return str(
        compute_payload_hash(
            {
                "policy_id": policy_id,
                "variant": variant,
                "content": content,
            }
        )
    )


def compute_artifact_hash(*, artifact: dict[str, Any]) -> str:
    """Compute deterministic artifact hash excluding self-referential hash key."""
    payload_without_hash = {k: v for k, v in artifact.items() if k != "artifact_hash"}
    return str(compute_payload_hash(payload_without_hash))
