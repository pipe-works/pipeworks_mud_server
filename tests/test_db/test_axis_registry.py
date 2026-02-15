"""
Tests for axis registry seeding (mud_server/db/database.py).

These tests verify:
- Axis rows are inserted/updated from policy payloads.
- Axis value rows are created from thresholds with correct ordinals.
- Missing thresholds do not overwrite axis_value rows.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mud_server.config import use_test_database
from mud_server.db import database


@pytest.mark.unit
@pytest.mark.db
def test_seed_axis_registry_inserts_axis_and_values(temp_db_path) -> None:
    """Axis policy payloads should seed both axis and axis_value tables."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        axes_payload: dict[str, Any] = {
            "axes": {
                "wealth": {
                    "description": "Economic status",
                    "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
                }
            }
        }
        thresholds_payload: dict[str, Any] = {
            "axes": {
                "wealth": {
                    "values": {
                        "poor": {"min": 0.0, "max": 0.5},
                        "wealthy": {"min": 0.5, "max": 1.0},
                    }
                }
            }
        }

        stats = database.seed_axis_registry(
            world_id="test_world",
            axes_payload=axes_payload,
            thresholds_payload=thresholds_payload,
        )

        assert stats.axes_upserted == 1
        assert stats.axis_values_inserted == 2
        assert stats.axes_missing_thresholds == 0

        conn = database.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name, description, ordering_json FROM axis WHERE world_id = ?",
            ("test_world",),
        )
        axis_row = cursor.fetchone()
        assert axis_row is not None
        assert axis_row[0] == "wealth"
        assert axis_row[1] == "Economic status"
        assert json.loads(axis_row[2]) == {"type": "ordinal", "values": ["poor", "wealthy"]}

        cursor.execute(
            """
            SELECT value, min_score, max_score, ordinal
            FROM axis_value
            JOIN axis ON axis.id = axis_value.axis_id
            WHERE axis.world_id = ?
            ORDER BY ordinal
            """,
            ("test_world",),
        )
        rows = cursor.fetchall()
        conn.close()

        assert rows == [
            ("poor", 0.0, 0.5, 0),
            ("wealthy", 0.5, 1.0, 1),
        ]


@pytest.mark.unit
@pytest.mark.db
def test_seed_axis_registry_skips_missing_thresholds(temp_db_path) -> None:
    """Missing thresholds should skip axis_value creation for that axis."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        axes_payload: dict[str, Any] = {
            "axes": {
                "demeanor": {
                    "description": "Disposition",
                    "ordering": {"type": "ordinal", "values": ["calm", "angry"]},
                }
            }
        }
        thresholds_payload: dict[str, Any] = {"axes": {}}

        stats = database.seed_axis_registry(
            world_id="test_world",
            axes_payload=axes_payload,
            thresholds_payload=thresholds_payload,
        )

        assert stats.axes_upserted == 1
        assert stats.axis_values_inserted == 0
        assert stats.axes_missing_thresholds == 1

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM axis_value")
        assert int(cursor.fetchone()[0]) == 0
        conn.close()
