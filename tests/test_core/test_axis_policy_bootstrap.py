"""
Tests for axis policy bootstrap logic in GameEngine.

These tests ensure:
- Axis policies are loaded at startup.
- Registry seeding is invoked for worlds with axes definitions.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from mud_server.config import use_test_database
from mud_server.core.engine import GameEngine
from mud_server.db import database
from mud_server.policies import AxisPolicyValidationReport
from mud_server.services import policy_service


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_seeds_registry(temp_db_path, monkeypatch, caplog) -> None:
    """Engine startup should load policies and call registry seeding."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        fake_bundle = policy_service.EffectiveAxisBundle(
            manifest_policy_id="manifest_bundle:world.manifests:pipeworks_web",
            manifest_variant="v1",
            axis_policy_id="axis_bundle:axis.bundles:axis_core_v1",
            axis_variant="v1",
            bundle_id="axis_core_v1",
            bundle_version="1",
            manifest_payload={},
            axes_payload={
                "axes": {
                    "wealth": {
                        "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
                    }
                }
            },
            thresholds_payload={
                "axes": {
                    "wealth": {
                        "values": {
                            "poor": {"min": 0.0, "max": 0.5},
                            "wealthy": {"min": 0.5, "max": 1.0},
                        }
                    }
                }
            },
            resolution_payload={"version": "1.0"},
            required_runtime_inputs=set(),
            policy_hash="testhash",
        )

        def _fake_seed_axis_registry(**kwargs):
            return database.AxisRegistrySeedStats(
                axes_upserted=1,
                axis_values_inserted=2,
                axes_missing_thresholds=0,
                axis_values_skipped=0,
            )

        monkeypatch.setattr(
            "mud_server.services.policy_service.resolve_effective_axis_bundle",
            lambda **kwargs: fake_bundle,
        )
        monkeypatch.setattr(database, "seed_axis_registry", _fake_seed_axis_registry)

        with caplog.at_level(logging.INFO):
            GameEngine()

        assert any("Axis registry seeded" in message for message in caplog.messages)


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_no_worlds(caplog) -> None:
    """Bootstrap should warn and exit when no worlds are registered."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
    cast(Any, engine).world_registry = SimpleNamespace(list_worlds=lambda include_inactive: [])

    with caplog.at_level(logging.WARNING):
        engine._bootstrap_axis_policies()

    assert any("no worlds registered" in message for message in caplog.messages)


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_missing_world_id(caplog, monkeypatch) -> None:
    """Malformed world rows should be skipped with a warning."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
    cast(Any, engine).world_registry = SimpleNamespace(
        list_worlds=lambda include_inactive: [{"name": "Bad"}]
    )

    monkeypatch.setattr(
        "mud_server.services.policy_service.resolve_effective_axis_bundle",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Resolver should not be called for malformed world rows.")
        ),
    )

    with caplog.at_level(logging.WARNING):
        engine._bootstrap_axis_policies()

    assert any("malformed world row" in message for message in caplog.messages)


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_skips_empty_axes(caplog, monkeypatch) -> None:
    """Worlds without axes should skip registry seeding."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
    cast(Any, engine).world_registry = SimpleNamespace(
        list_worlds=lambda include_inactive: [{"id": "empty_axes_world"}]
    )

    fake_bundle = policy_service.EffectiveAxisBundle(
        manifest_policy_id="manifest_bundle:world.manifests:empty_axes_world",
        manifest_variant="v1",
        axis_policy_id="axis_bundle:axis.bundles:axis_core_v1",
        axis_variant="v1",
        bundle_id="axis_core_v1",
        bundle_version="1",
        manifest_payload={},
        axes_payload={},
        thresholds_payload={},
        resolution_payload={"version": "1.0"},
        required_runtime_inputs=set(),
        policy_hash="hash",
    )

    def _fail_seed(**_kwargs):
        raise AssertionError("seed_axis_registry should not run when axes are missing.")

    monkeypatch.setattr(
        "mud_server.services.policy_service.resolve_effective_axis_bundle",
        lambda **kwargs: fake_bundle,
    )
    monkeypatch.setattr(database, "seed_axis_registry", _fail_seed)

    with caplog.at_level(logging.WARNING):
        engine._bootstrap_axis_policies()

    assert any("no axes defined" in message for message in caplog.messages)


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_imports_missing_canonical_bundle(caplog, monkeypatch) -> None:
    """Missing activation pointers should trigger import and retry once."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
    cast(Any, engine).world_registry = SimpleNamespace(
        list_worlds=lambda include_inactive: [{"id": "pipeworks_web"}]
    )

    fake_bundle = policy_service.EffectiveAxisBundle(
        manifest_policy_id="manifest_bundle:world.manifests:pipeworks_web",
        manifest_variant="v1",
        axis_policy_id="axis_bundle:axis.bundles:axis_core_v1",
        axis_variant="v1",
        bundle_id="axis_core_v1",
        bundle_version="1",
        manifest_payload={},
        axes_payload={
            "axes": {
                "wealth": {
                    "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
                }
            }
        },
        thresholds_payload={
            "axes": {
                "wealth": {
                    "values": {
                        "poor": {"min": 0.0, "max": 0.5},
                        "wealthy": {"min": 0.5, "max": 1.0},
                    }
                }
            }
        },
        resolution_payload={"version": "1.0"},
        required_runtime_inputs=set(),
        policy_hash="testhash",
    )
    calls = {"resolve": 0, "import": 0, "seed": 0}

    def _resolve(**_kwargs):
        calls["resolve"] += 1
        if calls["resolve"] == 1:
            raise policy_service.PolicyServiceError(
                status_code=404,
                code="POLICY_EFFECTIVE_MANIFEST_NOT_FOUND",
                detail="No effective manifest bundle activation found.",
            )
        return fake_bundle

    def _import(**kwargs):
        calls["import"] += 1
        assert kwargs["world_id"] == "pipeworks_web"
        assert kwargs["activate"] is True
        assert kwargs["status"] == "active"
        return SimpleNamespace(imported_count=2, updated_count=0, skipped_count=0, error_count=0)

    def _seed_axis_registry(**_kwargs):
        calls["seed"] += 1
        return database.AxisRegistrySeedStats(
            axes_upserted=1,
            axis_values_inserted=2,
            axes_missing_thresholds=0,
            axis_values_skipped=0,
        )

    monkeypatch.setattr(
        "mud_server.services.policy_service.resolve_effective_axis_bundle", _resolve
    )
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_axis_manifest_policies_from_legacy_files",
        _import,
    )
    monkeypatch.setattr(database, "seed_axis_registry", _seed_axis_registry)

    with caplog.at_level(logging.INFO):
        engine._bootstrap_axis_policies()

    assert calls["resolve"] == 2
    assert calls["import"] == 1
    assert calls["seed"] == 1
    assert any(
        "imported canonical axis bundle for pipeworks_web" in message for message in caplog.messages
    )


@pytest.mark.unit
def test_engine_bootstrap_axis_policy_logs_warning_when_import_retry_fails(
    caplog, monkeypatch
) -> None:
    """Import retry failures should log and skip registry seeding."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
    cast(Any, engine).world_registry = SimpleNamespace(
        list_worlds=lambda include_inactive: [{"id": "pipeworks_web"}]
    )

    def _resolve(**_kwargs):
        raise policy_service.PolicyServiceError(
            status_code=404,
            code="POLICY_EFFECTIVE_MANIFEST_NOT_FOUND",
            detail="No effective manifest bundle activation found.",
        )

    def _import(**_kwargs):
        raise policy_service.PolicyServiceError(
            status_code=404,
            code="POLICY_EFFECTIVE_MANIFEST_NOT_FOUND",
            detail="No effective manifest bundle activation found.",
        )

    def _fail_seed(**_kwargs):
        raise AssertionError("seed_axis_registry should not run when import retry fails.")

    monkeypatch.setattr(
        "mud_server.services.policy_service.resolve_effective_axis_bundle", _resolve
    )
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_axis_manifest_policies_from_legacy_files",
        _import,
    )
    monkeypatch.setattr(database, "seed_axis_registry", _fail_seed)

    with caplog.at_level(logging.WARNING):
        engine._bootstrap_axis_policies()

    assert any("after import attempt" in message for message in caplog.messages)


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
