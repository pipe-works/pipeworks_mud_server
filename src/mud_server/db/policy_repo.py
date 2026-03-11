"""SQLite repository functions for canonical policy authoring state.

This module is intentionally limited to storage concerns:
- inserting/updating policy identity rows
- inserting/updating policy variants
- recording validation, activation, and publish history
- reading normalized rows for API/service callers

Business rules (for example policy-type validation and world existence checks)
belong in :mod:`mud_server.services.policy_service`. Keeping that split makes
both layers easier to test and reason about.
"""

from __future__ import annotations

import json
from typing import Any, NoReturn

from mud_server.db.connection import connection_scope
from mud_server.db.errors import (
    DatabaseError,
    DatabaseOperationContext,
    DatabaseReadError,
    DatabaseWriteError,
)


def _raise_read_error(operation: str, exc: Exception, *, details: str | None = None) -> NoReturn:
    """Raise a typed repository read error while preserving chained cause.

    Args:
        operation: Stable operation identifier used in telemetry/logging.
        exc: Original low-level exception.
        details: Optional operation context that helps debugging.
    """
    if isinstance(exc, DatabaseError):
        raise exc
    raise DatabaseReadError(
        context=DatabaseOperationContext(operation=operation, details=details),
        cause=exc,
    ) from exc


def _raise_write_error(operation: str, exc: Exception, *, details: str | None = None) -> NoReturn:
    """Raise a typed repository write error while preserving chained cause.

    Args:
        operation: Stable operation identifier used in telemetry/logging.
        exc: Original low-level exception.
        details: Optional operation context that helps debugging.
    """
    if isinstance(exc, DatabaseError):
        raise exc
    raise DatabaseWriteError(
        context=DatabaseOperationContext(operation=operation, details=details),
        cause=exc,
    ) from exc


def upsert_policy_item(
    *,
    policy_id: str,
    policy_type: str,
    namespace: str,
    policy_key: str,
) -> None:
    """Insert one policy identity row when it does not already exist.

    ``policy_item`` is immutable identity metadata (type, namespace, key).
    Variant content and status live in ``policy_variant``.
    """
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO policy_item (
                    policy_id,
                    policy_type,
                    namespace,
                    policy_key
                ) VALUES (?, ?, ?, ?)
                """,
                (policy_id, policy_type, namespace, policy_key),
            )
    except Exception as exc:
        _raise_write_error(
            "policy.upsert_policy_item",
            exc,
            details=f"policy_id={policy_id!r}",
        )


def upsert_policy_variant(
    *,
    policy_id: str,
    variant: str,
    schema_version: str,
    policy_version: int,
    status: str,
    content: dict[str, Any],
    content_hash: str,
    updated_at: str,
    updated_by: str,
) -> dict[str, Any]:
    """Insert or update one policy variant and return the canonical row.

    The method intentionally performs a read-after-write to ensure callers
    receive the database-normalized representation (including JSON decoding and
    integer coercions) from a single code path.
    """
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO policy_variant (
                    policy_id,
                    variant,
                    schema_version,
                    policy_version,
                    status,
                    content_json,
                    content_hash,
                    updated_at,
                    updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_id, variant) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    policy_version = excluded.policy_version,
                    status = excluded.status,
                    content_json = excluded.content_json,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (
                    policy_id,
                    variant,
                    schema_version,
                    policy_version,
                    status,
                    json.dumps(content, ensure_ascii=False, sort_keys=True),
                    content_hash,
                    updated_at,
                    updated_by,
                ),
            )
    except Exception as exc:
        _raise_write_error(
            "policy.upsert_policy_variant",
            exc,
            details=f"policy_id={policy_id!r}, variant={variant!r}",
        )

    row = get_policy(policy_id=policy_id, variant=variant)
    if row is None:
        raise DatabaseWriteError(
            context=DatabaseOperationContext(
                operation="policy.upsert_policy_variant",
                details="variant write succeeded but row could not be reloaded",
            )
        )
    return row


def list_policies(
    *,
    policy_type: str | None = None,
    namespace: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List policy variants with optional filters.

    Args:
        policy_type: Optional exact filter for ``policy_item.policy_type``.
        namespace: Optional exact filter for ``policy_item.namespace``.
        status: Optional exact filter for ``policy_variant.status``.

    Returns:
        A list of normalized policy-object dictionaries sorted by stable
        identity keys and descending version within each policy.
    """
    query = """
        SELECT
            pi.policy_id,
            pi.policy_type,
            pi.namespace,
            pi.policy_key,
            pv.variant,
            pv.schema_version,
            pv.policy_version,
            pv.status,
            pv.content_json,
            pv.content_hash,
            pv.updated_at,
            pv.updated_by
        FROM policy_item pi
        JOIN policy_variant pv ON pv.policy_id = pi.policy_id
        WHERE 1=1
    """
    params: list[Any] = []
    if policy_type is not None:
        query += " AND pi.policy_type = ?"
        params.append(policy_type)
    if namespace is not None:
        query += " AND pi.namespace = ?"
        params.append(namespace)
    if status is not None:
        query += " AND pv.status = ?"
        params.append(status)
    query += " ORDER BY pi.policy_type, pi.namespace, pi.policy_key, pv.policy_version DESC"

    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [_deserialize_policy_variant_row(row) for row in rows]
    except Exception as exc:
        _raise_read_error("policy.list_policies", exc)


def get_policy(*, policy_id: str, variant: str | None = None) -> dict[str, Any] | None:
    """Get one policy variant by id and optional variant key.

    If ``variant`` is omitted, returns the highest ``policy_version`` variant.
    """
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            if variant is None:
                cursor.execute(
                    """
                    SELECT
                        pi.policy_id,
                        pi.policy_type,
                        pi.namespace,
                        pi.policy_key,
                        pv.variant,
                        pv.schema_version,
                        pv.policy_version,
                        pv.status,
                        pv.content_json,
                        pv.content_hash,
                        pv.updated_at,
                        pv.updated_by
                    FROM policy_item pi
                    JOIN policy_variant pv ON pv.policy_id = pi.policy_id
                    WHERE pi.policy_id = ?
                    ORDER BY pv.policy_version DESC, pv.updated_at DESC
                    LIMIT 1
                    """,
                    (policy_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        pi.policy_id,
                        pi.policy_type,
                        pi.namespace,
                        pi.policy_key,
                        pv.variant,
                        pv.schema_version,
                        pv.policy_version,
                        pv.status,
                        pv.content_json,
                        pv.content_hash,
                        pv.updated_at,
                        pv.updated_by
                    FROM policy_item pi
                    JOIN policy_variant pv ON pv.policy_id = pi.policy_id
                    WHERE pi.policy_id = ? AND pv.variant = ?
                    LIMIT 1
                    """,
                    (policy_id, variant),
                )
            row = cursor.fetchone()
            if row is None:
                return None
            return _deserialize_policy_variant_row(row)
    except Exception as exc:
        _raise_read_error(
            "policy.get_policy",
            exc,
            details=f"policy_id={policy_id!r}, variant={variant!r}",
        )


def insert_validation_run(
    *,
    policy_id: str,
    variant: str,
    is_valid: bool,
    errors: list[str],
    validated_at: str,
    validated_by: str,
) -> int:
    """Insert one validation-run row and return row id.

    Validation history is append-only. It allows audit replay even when a
    variant is later updated.
    """
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO policy_validation_run (
                    policy_id,
                    variant,
                    is_valid,
                    errors_json,
                    validated_at,
                    validated_by
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    policy_id,
                    variant,
                    1 if is_valid else 0,
                    json.dumps(errors, ensure_ascii=False),
                    validated_at,
                    validated_by,
                ),
            )
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("validation run insert missing lastrowid")
            return int(row_id)
    except Exception as exc:
        _raise_write_error(
            "policy.insert_validation_run",
            exc,
            details=f"policy_id={policy_id!r}, variant={variant!r}",
        )


def get_activation_event(event_id: int) -> dict[str, Any] | None:
    """Return one activation audit event row by id."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id,
                    world_id,
                    client_profile,
                    policy_id,
                    variant,
                    actor,
                    event_payload_json,
                    created_at
                FROM policy_audit_event
                WHERE id = ? AND event_type = 'activation'
                LIMIT 1
                """,
                (event_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "id": int(row[0]),
                "world_id": row[1],
                "client_profile": row[2],
                "policy_id": row[3],
                "variant": row[4],
                "actor": row[5],
                "event_payload": json.loads(row[6]),
                "created_at": row[7],
            }
    except Exception as exc:
        _raise_read_error("policy.get_activation_event", exc, details=f"event_id={event_id}")


def set_policy_activation(
    *,
    world_id: str,
    client_profile: str,
    policy_id: str,
    variant: str,
    activated_by: str,
    activated_at: str,
    rollback_of_activation_id: int | None,
) -> dict[str, Any]:
    """Atomically upsert the active pointer and emit an activation audit row.

    This method runs inside one write transaction so pointer state and audit
    history move together.
    """
    try:
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            # Guard activation updates against dangling pointers. The caller
            # must activate an existing policy variant.
            cursor.execute(
                """
                SELECT 1 FROM policy_variant
                WHERE policy_id = ? AND variant = ?
                LIMIT 1
                """,
                (policy_id, variant),
            )
            if cursor.fetchone() is None:
                raise ValueError(f"Unknown policy variant for activation: {policy_id}:{variant}")

            cursor.execute(
                """
                INSERT INTO policy_activation (
                    world_id,
                    client_profile,
                    policy_id,
                    variant,
                    activated_at,
                    activated_by,
                    rollback_of_activation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(world_id, client_profile, policy_id) DO UPDATE SET
                    variant = excluded.variant,
                    activated_at = excluded.activated_at,
                    activated_by = excluded.activated_by,
                    rollback_of_activation_id = excluded.rollback_of_activation_id
                """,
                (
                    world_id,
                    client_profile,
                    policy_id,
                    variant,
                    activated_at,
                    activated_by,
                    rollback_of_activation_id,
                ),
            )

            cursor.execute(
                """
                INSERT INTO policy_audit_event (
                    event_type,
                    world_id,
                    client_profile,
                    policy_id,
                    variant,
                    actor,
                    event_payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "activation",
                    world_id,
                    client_profile,
                    policy_id,
                    variant,
                    activated_by,
                    json.dumps(
                        {
                            "rollback_of_activation_id": rollback_of_activation_id,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    activated_at,
                ),
            )
            audit_event_id = cursor.lastrowid

            cursor.execute(
                """
                SELECT
                    world_id,
                    client_profile,
                    policy_id,
                    variant,
                    activated_at,
                    activated_by,
                    rollback_of_activation_id
                FROM policy_activation
                WHERE world_id = ? AND client_profile = ? AND policy_id = ?
                LIMIT 1
                """,
                (world_id, client_profile, policy_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError(
                    "Activation pointer write succeeded but row could not be reloaded"
                )
            return {
                "world_id": row[0],
                "client_profile": row[1],
                "policy_id": row[2],
                "variant": row[3],
                "activated_at": row[4],
                "activated_by": row[5],
                "rollback_of_activation_id": row[6],
                "audit_event_id": int(audit_event_id) if audit_event_id is not None else None,
            }
    except Exception as exc:
        _raise_write_error(
            "policy.set_policy_activation",
            exc,
            details=(
                f"world_id={world_id!r}, client_profile={client_profile!r}, "
                f"policy_id={policy_id!r}, variant={variant!r}"
            ),
        )


def list_policy_activations(*, world_id: str, client_profile: str) -> list[dict[str, Any]]:
    """List active policy pointers for one activation scope."""
    try:
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    world_id,
                    client_profile,
                    policy_id,
                    variant,
                    activated_at,
                    activated_by,
                    rollback_of_activation_id
                FROM policy_activation
                WHERE world_id = ? AND client_profile = ?
                ORDER BY policy_id
                """,
                (world_id, client_profile),
            )
            rows = cursor.fetchall()
            return [
                {
                    "world_id": row[0],
                    "client_profile": row[1],
                    "policy_id": row[2],
                    "variant": row[3],
                    "activated_at": row[4],
                    "activated_by": row[5],
                    "rollback_of_activation_id": row[6],
                }
                for row in rows
            ]
    except Exception as exc:
        _raise_read_error(
            "policy.list_policy_activations",
            exc,
            details=f"world_id={world_id!r}, client_profile={client_profile!r}",
        )


def insert_publish_run(
    *,
    world_id: str,
    client_profile: str,
    actor: str,
    manifest: dict[str, Any],
    created_at: str,
) -> int:
    """Insert one publish run plus audit event and return run id.

    The publish manifest is stored verbatim for later inspection and replay.
    """
    try:
        manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO policy_publish_run (
                    world_id,
                    client_profile,
                    actor,
                    manifest_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (world_id, client_profile, actor, manifest_json, created_at),
            )
            run_id = cursor.lastrowid
            if run_id is None:
                raise RuntimeError("Publish run insert missing lastrowid")

            cursor.execute(
                """
                INSERT INTO policy_audit_event (
                    event_type,
                    world_id,
                    client_profile,
                    policy_id,
                    variant,
                    actor,
                    event_payload_json,
                    created_at
                ) VALUES (?, ?, ?, NULL, NULL, ?, ?, ?)
                """,
                ("publish", world_id, client_profile, actor, manifest_json, created_at),
            )
            return int(run_id)
    except Exception as exc:
        _raise_write_error(
            "policy.insert_publish_run",
            exc,
            details=f"world_id={world_id!r}, client_profile={client_profile!r}",
        )


def _deserialize_policy_variant_row(row: tuple[Any, ...]) -> dict[str, Any]:
    """Normalize one joined ``policy_item`` + ``policy_variant`` row.

    Args:
        row: Tuple produced by the policy list/get SELECT statements.

    Returns:
        Dictionary matching the public policy-object API contract.
    """
    return {
        "policy_id": row[0],
        "policy_type": row[1],
        "namespace": row[2],
        "policy_key": row[3],
        "variant": row[4],
        "schema_version": row[5],
        "policy_version": int(row[6]),
        "status": row[7],
        "content": json.loads(row[8]),
        "content_hash": row[9],
        "updated_at": row[10],
        "updated_by": row[11],
    }
