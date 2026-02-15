"""Tests for axis policy loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from mud_server.policies import AxisPolicyLoader


def _write_policy(world_root: Path, axes_yaml: str, thresholds_yaml: str) -> None:
    """Write policy fixtures into a world package."""
    policies_dir = world_root / "policies"
    policies_dir.mkdir(parents=True, exist_ok=True)
    (policies_dir / "axes.yaml").write_text(axes_yaml, encoding="utf-8")
    (policies_dir / "thresholds.yaml").write_text(thresholds_yaml, encoding="utf-8")


@pytest.mark.unit
def test_axis_policy_loader_report_complete(tmp_path: Path) -> None:
    """Loader should report axes, ordering, thresholds, and hash when complete."""
    world_id = "world_one"
    world_root = tmp_path / world_id
    axes_yaml = """
version: 0.1.0
axes:
  wealth:
    values: [poor, wealthy]
    ordering:
      type: ordinal
      values: [poor, wealthy]
  health:
    values: [sick, well]
    ordering:
      type: ordinal
      values: [sick, well]
"""
    thresholds_yaml = """
version: 0.1.0
axes:
  wealth:
    values:
      poor: { min: 0.0, max: 0.5 }
      wealthy: { min: 0.5, max: 1.0 }
  health:
    values:
      sick: { min: 0.0, max: 0.5 }
      well: { min: 0.5, max: 1.0 }
"""
    _write_policy(world_root, axes_yaml, thresholds_yaml)

    loader = AxisPolicyLoader(worlds_root=tmp_path)
    _payload, report = loader.load(world_id)

    assert set(report.axes) == {"wealth", "health"}
    assert set(report.ordering_present) == {"wealth", "health"}
    assert set(report.thresholds_present) == {"wealth", "health"}
    assert "wealth" in report.ordering_definitions
    assert "health" in report.ordering_definitions
    assert "wealth" in report.thresholds_definitions
    assert "health" in report.thresholds_definitions
    assert report.missing_components == []
    assert report.policy_hash
    assert report.version == "0.1.0"


@pytest.mark.unit
def test_axis_policy_loader_missing_components(tmp_path: Path) -> None:
    """Missing ordering/thresholds should be reported."""
    world_id = "world_two"
    world_root = tmp_path / world_id
    axes_yaml = """
version: 0.2.0
axes:
  wealth:
    values: [poor, wealthy]
    ordering:
      type: ordinal
      values: [poor, wealthy]
  health:
    values: [sick, well]
"""
    thresholds_yaml = """
version: 0.2.0
axes:
  wealth:
    values:
      poor: { min: 0.0, max: 0.5 }
      wealthy: { min: 0.5, max: 1.0 }
"""
    _write_policy(world_root, axes_yaml, thresholds_yaml)

    loader = AxisPolicyLoader(worlds_root=tmp_path)
    _payload, report = loader.load(world_id)

    assert "ordering missing for axis: health" in report.missing_components
    assert "thresholds missing for axis: health" in report.missing_components


@pytest.mark.unit
def test_axis_policy_loader_empty_policy(tmp_path: Path) -> None:
    """Empty policies should report missing axes."""
    world_id = "world_three"
    world_root = tmp_path / world_id
    _write_policy(world_root, "{}", "{}")

    loader = AxisPolicyLoader(worlds_root=tmp_path)
    _payload, report = loader.load(world_id)

    assert "axes list missing or empty" in report.missing_components
