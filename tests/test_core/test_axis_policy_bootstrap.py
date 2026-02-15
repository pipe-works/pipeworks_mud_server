"""
Tests for axis policy bootstrap logic in GameEngine.

These tests ensure:
- Axis policies are loaded at startup.
- Registry seeding is invoked for worlds with axes definitions.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from mud_server.config import use_test_database
from mud_server.core.engine import GameEngine
from mud_server.db import database
from mud_server.policies import AxisPolicyValidationReport


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_seeds_registry(temp_db_path, monkeypatch, caplog) -> None:
    """Engine startup should load policies and call registry seeding."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        fake_payload: dict[str, Any] = {
            "axes": {
                "wealth": {
                    "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
                }
            },
            "thresholds": {
                "axes": {
                    "wealth": {
                        "values": {
                            "poor": {"min": 0.0, "max": 0.5},
                            "wealthy": {"min": 0.5, "max": 1.0},
                        }
                    }
                }
            },
        }

        report = AxisPolicyValidationReport(
            world_id=database.DEFAULT_WORLD_ID,
            axes=["wealth"],
            ordering_present=["wealth"],
            ordering_definitions={"wealth": {"type": "ordinal", "values": ["poor", "wealthy"]}},
            thresholds_present=["wealth"],
            thresholds_definitions=fake_payload["thresholds"]["axes"],
            missing_components=[],
            policy_hash="testhash",
            version="0.1.0",
        )

        class _FakeLoader:
            def __init__(self, *, worlds_root):
                self.worlds_root = worlds_root

            def load(self, world_id):
                return fake_payload, report

        def _fake_seed_axis_registry(**kwargs):
            return database.AxisRegistrySeedStats(
                axes_upserted=1,
                axis_values_inserted=2,
                axes_missing_thresholds=0,
                axis_values_skipped=0,
            )

        monkeypatch.setattr("mud_server.policies.AxisPolicyLoader", _FakeLoader)
        monkeypatch.setattr(database, "seed_axis_registry", _fake_seed_axis_registry)

        with caplog.at_level(logging.INFO):
            GameEngine()

        assert any("Axis registry seeded" in message for message in caplog.messages)
