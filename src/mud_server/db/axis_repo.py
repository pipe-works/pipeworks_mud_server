"""Axis registry and character state snapshot repository operations."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from secrets import randbelow
from typing import TYPE_CHECKING, Any, cast

from mud_server.db.constants import DEFAULT_AXIS_SCORE

if TYPE_CHECKING:
    from mud_server.db.database import AxisRegistrySeedStats


def _get_connection() -> sqlite3.Connection:
    """Return a DB connection via the compatibility facade."""
    from mud_server.db import database

    return database.get_connection()


def _generate_state_seed() -> int:
    """Return a non-zero random seed for character state snapshots."""
    return randbelow(2_147_483_647) + 1


def _extract_axis_ordering_values(axis_data: dict[str, Any]) -> list[str]:
    """Extract ordering values from axis policy payloads."""
    ordering = (axis_data or {}).get("ordering")
    if not isinstance(ordering, dict):
        return []

    values = ordering.get("values")
    if not isinstance(values, list):
        return []

    return [str(value) for value in values]


def seed_axis_registry(
    *,
    world_id: str,
    axes_payload: dict[str, Any],
    thresholds_payload: dict[str, Any],
) -> AxisRegistrySeedStats:
    """Insert or update axis and axis-value rows from policy payloads."""
    from mud_server.db import database

    axes_definitions = axes_payload.get("axes") or {}
    thresholds_definitions = thresholds_payload.get("axes") or {}

    axes_upserted = 0
    axis_values_inserted = 0
    axes_missing_thresholds = 0
    axis_values_skipped = 0

    conn = _get_connection()
    cursor = conn.cursor()

    for axis_name, axis_data in axes_definitions.items():
        axis_data = axis_data or {}
        ordering = axis_data.get("ordering")
        ordering_json = json.dumps(ordering, sort_keys=True) if ordering else None

        cursor.execute(
            """
            INSERT INTO axis (world_id, name, description, ordering_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(world_id, name) DO UPDATE SET
                description = excluded.description,
                ordering_json = excluded.ordering_json
            """,
            (
                world_id,
                axis_name,
                axis_data.get("description"),
                ordering_json,
            ),
        )
        axes_upserted += 1

        cursor.execute(
            "SELECT id FROM axis WHERE world_id = ? AND name = ? LIMIT 1",
            (world_id, axis_name),
        )
        axis_row = cursor.fetchone()
        if not axis_row:
            axis_values_skipped += 1
            continue
        axis_id = int(axis_row[0])

        thresholds = thresholds_definitions.get(axis_name)
        if not isinstance(thresholds, dict):
            axes_missing_thresholds += 1
            continue

        values = thresholds.get("values") or {}
        if not isinstance(values, dict):
            axis_values_skipped += 1
            continue

        ordering_values = _extract_axis_ordering_values(axis_data)
        ordinal_map = {value: index for index, value in enumerate(ordering_values)}

        cursor.execute("DELETE FROM axis_value WHERE axis_id = ?", (axis_id,))
        for value_name, value_bounds in values.items():
            value_bounds = value_bounds or {}
            min_score = value_bounds.get("min")
            max_score = value_bounds.get("max")
            min_score = float(min_score) if min_score is not None else None
            max_score = float(max_score) if max_score is not None else None

            cursor.execute(
                """
                INSERT INTO axis_value (axis_id, value, min_score, max_score, ordinal)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    axis_id,
                    str(value_name),
                    min_score,
                    max_score,
                    ordinal_map.get(str(value_name)),
                ),
            )
            axis_values_inserted += 1

    conn.commit()
    conn.close()

    return database.AxisRegistrySeedStats(
        axes_upserted=axes_upserted,
        axis_values_inserted=axis_values_inserted,
        axes_missing_thresholds=axes_missing_thresholds,
        axis_values_skipped=axis_values_skipped,
    )


def _get_axis_policy_hash(world_id: str) -> str | None:
    """Return the axis policy hash for a world."""
    from pathlib import Path

    from mud_server.config import config
    from mud_server.policies import AxisPolicyLoader

    loader = AxisPolicyLoader(worlds_root=Path(config.worlds.worlds_root))
    _payload, report = loader.load(world_id)
    return report.policy_hash


def _resolve_axis_label_for_score(cursor: sqlite3.Cursor, axis_id: int, score: float) -> str | None:
    """Resolve axis score to a label using axis_value thresholds."""
    cursor.execute(
        """
        SELECT value
        FROM axis_value
        WHERE axis_id = ?
          AND (? >= min_score OR min_score IS NULL)
          AND (? <= max_score OR max_score IS NULL)
        ORDER BY
          CASE WHEN ordinal IS NULL THEN 1 ELSE 0 END,
          ordinal,
          min_score
        LIMIT 1
        """,
        (axis_id, score, score),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def _resolve_axis_score_for_label(
    cursor: sqlite3.Cursor,
    *,
    world_id: str,
    axis_name: str,
    axis_label: str,
) -> float | None:
    """Resolve axis label to a representative numeric score."""
    cursor.execute(
        """
        SELECT av.min_score, av.max_score
        FROM axis_value av
        JOIN axis a ON a.id = av.axis_id
        WHERE a.world_id = ? AND a.name = ? AND av.value = ?
        LIMIT 1
        """,
        (world_id, axis_name, axis_label),
    )
    row = cursor.fetchone()
    if not row:
        return None

    min_score = float(row[0]) if row[0] is not None else None
    max_score = float(row[1]) if row[1] is not None else None
    if min_score is not None and max_score is not None:
        return (min_score + max_score) / 2.0
    if min_score is not None:
        return min_score
    if max_score is not None:
        return max_score
    return DEFAULT_AXIS_SCORE


def _flatten_entity_axis_labels(entity_state: dict[str, Any]) -> dict[str, str]:
    """Flatten entity payload labels into ``axis_name -> label`` mapping."""
    labels: dict[str, str] = {}

    for group in ("character", "occupation"):
        group_payload = entity_state.get(group)
        if isinstance(group_payload, dict):
            for axis_name, axis_value in group_payload.items():
                if isinstance(axis_value, str) and axis_value.strip():
                    labels[str(axis_name)] = axis_value.strip()

    axes_payload = entity_state.get("axes")
    if isinstance(axes_payload, dict):
        for axis_name, axis_value in axes_payload.items():
            if isinstance(axis_value, dict):
                label = axis_value.get("label")
                if isinstance(label, str) and label.strip():
                    labels[str(axis_name)] = label.strip()
            elif isinstance(axis_value, str) and axis_value.strip():
                labels[str(axis_name)] = axis_value.strip()

    return labels


def apply_entity_state_to_character(
    *,
    character_id: int,
    world_id: str,
    entity_state: dict[str, Any],
    seed: int | None = None,
    event_type_name: str = "entity_profile_seeded",
) -> int | None:
    """Apply entity-state labels as score deltas through the event ledger."""
    from mud_server.db import database

    axis_labels = _flatten_entity_axis_labels(entity_state)
    if not axis_labels:
        return None

    conn = _get_connection()
    cursor = conn.cursor()
    try:
        current_scores = {
            row["axis_name"]: float(row["axis_score"])
            for row in _fetch_character_axis_scores(cursor, character_id, world_id)
        }
        deltas: dict[str, float] = {}
        for axis_name, axis_label in axis_labels.items():
            target_score = _resolve_axis_score_for_label(
                cursor,
                world_id=world_id,
                axis_name=axis_name,
                axis_label=axis_label,
            )
            if target_score is None:
                continue
            old_score = current_scores.get(axis_name, DEFAULT_AXIS_SCORE)
            delta = target_score - old_score
            if abs(delta) < 1e-9:
                continue
            deltas[axis_name] = delta
    finally:
        conn.close()

    if not deltas:
        return None

    metadata: dict[str, str] = {
        "source": "entity_state_api",
        "axis_count": str(len(deltas)),
    }
    if seed is not None:
        metadata["seed"] = str(seed)

    return database.apply_axis_event(
        world_id=world_id,
        character_id=character_id,
        event_type_name=event_type_name,
        event_type_description=(
            "Initial axis profile generated from external entity-state integration."
        ),
        deltas=deltas,
        metadata=metadata,
    )


def _fetch_character_axis_scores(
    cursor: sqlite3.Cursor,
    character_id: int,
    world_id: str,
) -> list[dict[str, Any]]:
    """Return character axis score rows joined with axis metadata."""
    cursor.execute(
        """
        SELECT a.id, a.name, s.axis_score
        FROM character_axis_score s
        JOIN axis a ON a.id = s.axis_id
        WHERE s.character_id = ? AND s.world_id = ?
        ORDER BY a.name
        """,
        (character_id, world_id),
    )
    return [
        {
            "axis_id": int(row[0]),
            "axis_name": row[1],
            "axis_score": float(row[2]),
        }
        for row in cursor.fetchall()
    ]


def _seed_character_axis_scores(
    cursor: sqlite3.Cursor,
    *,
    character_id: int,
    world_id: str,
    default_score: float = DEFAULT_AXIS_SCORE,
) -> None:
    """Seed missing axis score rows for a character."""
    cursor.execute(
        """
        SELECT id, name
        FROM axis
        WHERE world_id = ?
        ORDER BY name
        """,
        (world_id,),
    )
    for axis_id, _axis_name in cursor.fetchall():
        cursor.execute(
            """
            INSERT OR IGNORE INTO character_axis_score
                (character_id, world_id, axis_id, axis_score)
            VALUES (?, ?, ?, ?)
            """,
            (character_id, world_id, int(axis_id), float(default_score)),
        )


def _build_character_state_snapshot(
    cursor: sqlite3.Cursor,
    *,
    character_id: int,
    world_id: str,
    seed: int,
    policy_hash: str | None,
) -> dict[str, Any]:
    """Build a canonical snapshot payload from current character axis scores."""
    axes_payload: dict[str, Any] = {}
    for axis_row in _fetch_character_axis_scores(cursor, character_id, world_id):
        label = _resolve_axis_label_for_score(cursor, axis_row["axis_id"], axis_row["axis_score"])
        axes_payload[axis_row["axis_name"]] = {
            "score": axis_row["axis_score"],
            "label": label,
        }

    return {
        "world_id": world_id,
        "seed": seed,
        "policy_hash": policy_hash,
        "axes": axes_payload,
    }


def _seed_character_state_snapshot(
    cursor: sqlite3.Cursor,
    *,
    character_id: int,
    world_id: str,
    seed: int | None = None,
) -> None:
    """Seed base/current state snapshots for a newly created character."""
    from mud_server.db import database

    cursor.execute("SELECT state_seed FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    existing_seed = int(row[0]) if row and row[0] is not None else 0
    if existing_seed > 0:
        effective_seed = existing_seed
    elif seed is not None:
        effective_seed = seed
    else:
        effective_seed = database._generate_state_seed()

    policy_hash = database._get_axis_policy_hash(world_id)
    snapshot = _build_character_state_snapshot(
        cursor,
        character_id=character_id,
        world_id=world_id,
        seed=effective_seed,
        policy_hash=policy_hash,
    )
    snapshot_json = json.dumps(snapshot, sort_keys=True)
    state_updated_at = datetime.now(UTC).isoformat()

    cursor.execute(
        """
        UPDATE characters
        SET base_state_json = COALESCE(base_state_json, ?),
            current_state_json = ?,
            state_seed = CASE
                WHEN state_seed IS NULL OR state_seed = 0 THEN ?
                ELSE state_seed
            END,
            state_version = ?,
            state_updated_at = ?
        WHERE id = ?
        """,
        (
            snapshot_json,
            snapshot_json,
            effective_seed,
            policy_hash,
            state_updated_at,
            character_id,
        ),
    )


def _refresh_character_current_snapshot(
    cursor: sqlite3.Cursor,
    *,
    character_id: int,
    world_id: str,
    seed_increment: int = 1,
) -> None:
    """Refresh current snapshot payload after axis score mutations."""
    from mud_server.db import database

    cursor.execute("SELECT state_seed FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    current_seed = int(row[0]) if row and row[0] is not None else 0
    new_seed = current_seed + seed_increment

    policy_hash = database._get_axis_policy_hash(world_id)
    snapshot = _build_character_state_snapshot(
        cursor,
        character_id=character_id,
        world_id=world_id,
        seed=new_seed,
        policy_hash=policy_hash,
    )
    snapshot_json = json.dumps(snapshot, sort_keys=True)
    state_updated_at = datetime.now(UTC).isoformat()

    cursor.execute(
        """
        UPDATE characters
        SET current_state_json = ?,
            state_seed = ?,
            state_version = ?,
            state_updated_at = ?
        WHERE id = ?
        """,
        (
            snapshot_json,
            new_seed,
            policy_hash,
            state_updated_at,
            character_id,
        ),
    )


def get_character_axis_state(character_id: int) -> dict[str, Any] | None:
    """Return axis score + snapshot payload for one character."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id,
               world_id,
               base_state_json,
               current_state_json,
               state_seed,
               state_version,
               state_updated_at
        FROM characters
        WHERE id = ?
        """,
        (character_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    world_id = row[1]
    base_state_json = row[2]
    current_state_json = row[3]
    state_seed = row[4]
    state_version = row[5]
    state_updated_at = row[6]

    def _safe_load(payload: str | None) -> dict[str, Any] | None:
        if not payload:
            return None
        try:
            return cast(dict[str, Any], json.loads(payload))
        except json.JSONDecodeError:
            return None

    axes = []
    for axis_row in _fetch_character_axis_scores(cursor, character_id, world_id):
        label = _resolve_axis_label_for_score(cursor, axis_row["axis_id"], axis_row["axis_score"])
        axes.append(
            {
                "axis_id": axis_row["axis_id"],
                "axis_name": axis_row["axis_name"],
                "axis_score": axis_row["axis_score"],
                "axis_label": label,
            }
        )

    conn.close()
    return {
        "character_id": int(row[0]),
        "world_id": world_id,
        "state_seed": state_seed,
        "state_version": state_version,
        "state_updated_at": state_updated_at,
        "base_state": _safe_load(base_state_json),
        "current_state": _safe_load(current_state_json),
        "axes": axes,
    }
