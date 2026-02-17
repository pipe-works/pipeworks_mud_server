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
from mud_server.db import connection as db_connection
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


@pytest.mark.unit
@pytest.mark.db
def test_seed_axis_registry_handles_invalid_ordering(temp_db_path) -> None:
    """Invalid ordering definitions should yield None ordinals without crashing."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        axes_payload: dict[str, Any] = {
            "axes": {
                "demeanor": {
                    "description": "Disposition",
                    "ordering": "ordinal",
                }
            }
        }
        thresholds_payload: dict[str, Any] = {
            "axes": {
                "demeanor": {
                    "values": {
                        "calm": {"min": 0.0, "max": 0.5},
                        "angry": {"min": 0.5, "max": 1.0},
                    }
                }
            }
        }

        stats = database.seed_axis_registry(
            world_id="test_world",
            axes_payload=axes_payload,
            thresholds_payload=thresholds_payload,
        )

        assert stats.axis_values_inserted == 2

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ordinal
            FROM axis_value
            ORDER BY value
            """,
        )
        ordinals = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert ordinals == [None, None]


@pytest.mark.unit
@pytest.mark.db
def test_seed_axis_registry_handles_non_list_ordering_values(temp_db_path) -> None:
    """Ordering values that are not lists should default to None ordinals."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        axes_payload: dict[str, Any] = {
            "axes": {
                "temper": {
                    "description": "Temper level",
                    "ordering": {"type": "ordinal", "values": "volatile"},
                }
            }
        }
        thresholds_payload: dict[str, Any] = {
            "axes": {
                "temper": {
                    "values": {
                        "calm": {"min": 0.0, "max": 0.5},
                        "volatile": {"min": 0.5, "max": 1.0},
                    }
                }
            }
        }

        stats = database.seed_axis_registry(
            world_id="test_world",
            axes_payload=axes_payload,
            thresholds_payload=thresholds_payload,
        )

        assert stats.axis_values_inserted == 2

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ordinal
            FROM axis_value
            ORDER BY value
            """,
        )
        ordinals = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert ordinals == [None, None]


@pytest.mark.unit
@pytest.mark.db
def test_seed_axis_registry_skips_invalid_threshold_values(temp_db_path) -> None:
    """Non-dict threshold values should skip axis_value inserts."""
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
                    "values": ["poor", "wealthy"],
                }
            }
        }

        stats = database.seed_axis_registry(
            world_id="test_world",
            axes_payload=axes_payload,
            thresholds_payload=thresholds_payload,
        )

        assert stats.axis_values_inserted == 0
        assert stats.axis_values_skipped == 1

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM axis_value")
        assert int(cursor.fetchone()[0]) == 0
        conn.close()


@pytest.mark.unit
def test_seed_axis_registry_skips_missing_axis_row(monkeypatch) -> None:
    """Missing axis rows should increment skipped counts and continue safely."""

    class _FakeCursor:
        def execute(self, _sql, _params=None) -> None:
            return None

        def fetchone(self):
            return None

    class _FakeConnection:
        def __init__(self) -> None:
            self._cursor = _FakeCursor()

        def cursor(self):
            return self._cursor

        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(db_connection, "get_connection", lambda: _FakeConnection())

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
    assert stats.axis_values_inserted == 0
    assert stats.axis_values_skipped == 1
