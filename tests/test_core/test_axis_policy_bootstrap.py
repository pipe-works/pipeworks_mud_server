"""
Tests for axis policy bootstrap logic in GameEngine.

These tests ensure:
- Axis policies are loaded at startup.
- Registry seeding is invoked for worlds with axes definitions.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

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


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_no_worlds(caplog) -> None:
    """Bootstrap should warn and exit when no worlds are registered."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
    engine.world_registry = SimpleNamespace(list_worlds=lambda include_inactive: [])

    with caplog.at_level(logging.WARNING):
        engine._bootstrap_axis_policies()

    assert any("no worlds registered" in message for message in caplog.messages)


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_missing_world_id(caplog, monkeypatch) -> None:
    """Malformed world rows should be skipped with a warning."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
    engine.world_registry = SimpleNamespace(list_worlds=lambda include_inactive: [{"name": "Bad"}])

    class _FailingLoader:
        def __init__(self, *, worlds_root):
            self.worlds_root = worlds_root

        def load(self, _world_id):
            raise AssertionError("Loader should not be called for malformed world rows.")

    monkeypatch.setattr("mud_server.policies.AxisPolicyLoader", _FailingLoader)

    with caplog.at_level(logging.WARNING):
        engine._bootstrap_axis_policies()

    assert any("malformed world row" in message for message in caplog.messages)


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_skips_empty_axes(caplog, monkeypatch) -> None:
    """Worlds without axes should skip registry seeding."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
    engine.world_registry = SimpleNamespace(
        list_worlds=lambda include_inactive: [{"id": "empty_axes_world"}]
    )

    report = AxisPolicyValidationReport(
        world_id="empty_axes_world",
        axes=[],
        ordering_present=[],
        ordering_definitions={},
        thresholds_present=[],
        thresholds_definitions={},
        missing_components=["axes list missing or empty"],
        policy_hash="hash",
        version="0.1.0",
    )

    class _FakeLoader:
        def __init__(self, *, worlds_root):
            self.worlds_root = worlds_root

        def load(self, _world_id):
            return {"axes": {}, "thresholds": {}}, report

    def _fail_seed(**_kwargs):
        raise AssertionError("seed_axis_registry should not run when axes are missing.")

    monkeypatch.setattr("mud_server.policies.AxisPolicyLoader", _FakeLoader)
    monkeypatch.setattr(database, "seed_axis_registry", _fail_seed)

    with caplog.at_level(logging.WARNING):
        engine._bootstrap_axis_policies()

    assert any("no axes defined" in message for message in caplog.messages)


@pytest.mark.unit
def test_log_axis_policy_report_missing_components(caplog) -> None:
    """Missing policy components should emit a warning entry."""
    report = AxisPolicyValidationReport(
        world_id="test_world",
        axes=["wealth"],
        ordering_present=[],
        ordering_definitions={},
        thresholds_present=[],
        thresholds_definitions={},
        missing_components=["ordering missing for axis: wealth"],
        policy_hash="hash",
        version=None,
    )

    logger = logging.getLogger("mud_server.core.engine")
    with caplog.at_level(logging.WARNING):
        GameEngine._log_axis_policy_report(logger, report)

    assert any("missing components" in message for message in caplog.messages)
