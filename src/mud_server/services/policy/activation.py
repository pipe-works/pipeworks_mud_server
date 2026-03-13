"""Layer 3 activation service logic.

This module owns activation pointer mutation, replay consistency checks, and
scope overlay resolution used by runtime callers.
"""

from __future__ import annotations

from typing import Any

from mud_server.db import policy_repo

from .errors import PolicyServiceError
from .types import ActivationScope
from .utils import activation_map_from_rows, ensure_world_exists, now_iso
from .validation import parse_policy_id


def set_policy_activation(
    *,
    scope: ActivationScope,
    policy_id: str,
    variant: str,
    activated_by: str,
    rollback_of_activation_id: int | None = None,
) -> dict[str, Any]:
    """Set one activation pointer for a scope and record audit history.

    When ``rollback_of_activation_id`` is provided, the target variant is read
    from that event after strict scope and policy-id checks.
    """
    ensure_world_exists(scope.world_id)
    parse_policy_id(policy_id)

    resolved_variant = variant
    if rollback_of_activation_id is not None:
        rollback_event = policy_repo.get_activation_event(rollback_of_activation_id)
        if rollback_event is None:
            raise PolicyServiceError(
                status_code=404,
                code="POLICY_ROLLBACK_EVENT_NOT_FOUND",
                detail=f"Rollback activation event not found: {rollback_of_activation_id}",
            )
        if rollback_event["policy_id"] != policy_id:
            raise PolicyServiceError(
                status_code=409,
                code="POLICY_ROLLBACK_POLICY_MISMATCH",
                detail="Rollback activation event does not match requested policy_id.",
            )
        if rollback_event["world_id"] != scope.world_id or rollback_event["client_profile"] != (
            scope.client_profile
        ):
            raise PolicyServiceError(
                status_code=409,
                code="POLICY_ROLLBACK_SCOPE_MISMATCH",
                detail="Rollback activation event belongs to a different activation scope.",
            )
        resolved_variant = str(rollback_event["variant"])

    try:
        activation_row = policy_repo.set_policy_activation(
            world_id=scope.world_id,
            client_profile=scope.client_profile,
            policy_id=policy_id,
            variant=resolved_variant,
            activated_by=activated_by,
            activated_at=now_iso(),
            rollback_of_activation_id=rollback_of_activation_id,
        )
    except Exception as exc:
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_ACTIVATION_ERROR",
            detail=str(exc),
        ) from exc

    assert_activation_replay_consistency(scope=scope)
    return activation_row


def list_policy_activations(*, scope: ActivationScope) -> list[dict[str, Any]]:
    """List active pointers for exactly one activation scope."""
    ensure_world_exists(scope.world_id)
    return policy_repo.list_policy_activations(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
    )


def resolve_effective_policy_activations(*, scope: ActivationScope) -> list[dict[str, Any]]:
    """Resolve effective scope activations with client-over-world overlay semantics."""
    ensure_world_exists(scope.world_id)
    world_rows = policy_repo.list_policy_activations(world_id=scope.world_id, client_profile="")
    if not scope.client_profile:
        return world_rows

    client_rows = policy_repo.list_policy_activations(
        world_id=scope.world_id,
        client_profile=scope.client_profile,
    )
    merged_by_policy_id: dict[str, dict[str, Any]] = {
        str(row["policy_id"]): row for row in world_rows
    }
    for row in client_rows:
        merged_by_policy_id[str(row["policy_id"])] = row
    return [merged_by_policy_id[policy_id] for policy_id in sorted(merged_by_policy_id)]


def get_effective_policy_variant(
    *, scope: ActivationScope, policy_id: str
) -> dict[str, Any] | None:
    """Return effective active policy variant for one scope + policy id."""
    parse_policy_id(policy_id)
    effective_rows = resolve_effective_policy_activations(scope=scope)
    by_policy_id = {str(row["policy_id"]): row for row in effective_rows}
    activation = by_policy_id.get(policy_id)
    if activation is None:
        return None

    variant = str(activation["variant"])
    row = policy_repo.get_policy(policy_id=policy_id, variant=variant)
    if row is None:
        raise PolicyServiceError(
            status_code=409,
            code="POLICY_EFFECTIVE_REFERENCE_MISSING",
            detail=f"Effective activation points to missing policy variant: {policy_id}:{variant}",
        )
    return row


def assert_activation_replay_consistency(*, scope: ActivationScope) -> None:
    """Assert pointer table equals replayed activation-event history.

    This protects the core auditability invariant of Layer 3.
    """
    try:
        active_rows = policy_repo.list_policy_activations(
            world_id=scope.world_id,
            client_profile=scope.client_profile,
        )
        activation_events = policy_repo.list_activation_events(
            world_id=scope.world_id,
            client_profile=scope.client_profile,
        )
    except Exception as exc:
        raise PolicyServiceError(
            status_code=500,
            code="POLICY_AUDIT_REPLAY_READ_ERROR",
            detail=str(exc),
        ) from exc

    pointer_state = activation_map_from_rows(active_rows)
    replay_state: dict[str, str] = {}
    for event in activation_events:
        replay_state[str(event["policy_id"])] = str(event["variant"])

    if replay_state != pointer_state:
        raise PolicyServiceError(
            status_code=500,
            code="POLICY_ACTIVATION_REPLAY_MISMATCH",
            detail=(
                "Activation pointer state does not match replayed activation events "
                f"for scope {scope.world_id}:{scope.client_profile}."
            ),
        )
