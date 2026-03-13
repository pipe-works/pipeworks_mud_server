"""Shared utility helpers for policy services.

These helpers are intentionally storage-agnostic primitives used across
multiple policy modules. They hold common parsing and guard-rail behavior
that should remain consistent across validation, activation, and publish.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mud_server.db import facade as db_facade

from .errors import PolicyServiceError
from .types import ActivationScope


def now_iso() -> str:
    """Return canonical UTC ISO-8601 timestamp string with ``Z`` suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_world_exists(world_id: str) -> None:
    """Raise a typed 404 when the target world id does not exist."""
    if db_facade.get_world_by_id(world_id) is None:
        raise PolicyServiceError(
            status_code=404,
            code="POLICY_WORLD_NOT_FOUND",
            detail=f"World {world_id!r} not found.",
        )


def parse_scope(scope_text: str) -> ActivationScope:
    """Parse ``world_id[:client_profile]`` text into ``ActivationScope``.

    Empty ``client_profile`` always maps to world-level scope.
    """
    normalized = scope_text.strip()
    if not normalized:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_SCOPE_INVALID",
            detail="Activation scope must not be empty.",
        )
    if ":" in normalized:
        world_id, client_profile = normalized.split(":", 1)
    else:
        world_id, client_profile = normalized, ""

    world_id = world_id.strip()
    client_profile = client_profile.strip()
    if not world_id:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_SCOPE_INVALID",
            detail="Scope world_id must not be empty.",
        )
    return ActivationScope(world_id=world_id, client_profile=client_profile)


def resolve_positive_int_version(*, value: Any, default: int | None, context: str) -> int:
    """Resolve a positive integer value with strict type and range checks."""
    if value is None:
        if default is None:
            raise ValueError(f"{context} must be a positive integer.")
        return default

    if isinstance(value, bool):
        raise ValueError(f"{context} must not be a boolean.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise ValueError(f"{context} must be a positive integer; got {value!r}.")

    if parsed < 1:
        raise ValueError(f"{context} must be >= 1.")
    return parsed


def activation_map_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Return ``policy_id -> variant`` map from activation row payloads."""
    return {str(row["policy_id"]): str(row["variant"]) for row in rows}
