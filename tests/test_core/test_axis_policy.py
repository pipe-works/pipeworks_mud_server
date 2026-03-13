"""Tests for axis policy loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from mud_server.policies import AxisPolicyLoader


def _write_policy(world_root: Path, axes_yaml: str, thresholds_yaml: str) -> None:
    """Write policy fixtures into a world package."""
    axis_dir = world_root / "policies" / "axis"
    axis_dir.mkdir(parents=True, exist_ok=True)
    (axis_dir / "axes.yaml").write_text(axes_yaml, encoding="utf-8")
    (axis_dir / "thresholds.yaml").write_text(thresholds_yaml, encoding="utf-8")


def _write_manifest_axis_paths(world_root: Path) -> None:
    """Write a minimal manifest that points axis assets at nested paths."""
    policies_dir = world_root / "policies"
    manifest = """
schema_version: 0.1.0
policy_schema: pipeworks_policy_v1
world_id: test_world
policy_bundle:
  id: bundle
  version: 1
axis:
  active_bundle:
    id: axis_core_v1
    version: 1
    files:
      axes: policies/axis/axes.yaml
      thresholds: policies/axis/thresholds.yaml
      resolution: policies/axis/resolution.yaml
translation:
  active_prompt:
    id: ic_default_v1
    version: 1
    path: policies/translation/prompts/ic/default_v1.txt
image:
  descriptor_layer:
    id: id_card_v1
    version: 1
    path: policies/image/descriptor_layers/id_card_v1.txt
  tone_profile:
    id: ledger_engraving_v1
    version: 1
    path: policies/image/tone_profiles/ledger_engraving_v1.json
  registries:
    species: policies/image/registries/species_registry.yaml
    clothing: policies/image/registries/clothing_registry.yaml
  composition:
    order:
      - species_canon_block
      - descriptor_layer_output
      - clothing_block
      - tone_profile_block
    required_runtime_inputs:
      - entity.identity.gender
      - entity.species
      - entity.axes
"""
    (policies_dir / "manifest.yaml").write_text(manifest, encoding="utf-8")
    (world_root / "policies" / "axis").mkdir(parents=True, exist_ok=True)
    (world_root / "policies" / "translation" / "prompts" / "ic").mkdir(parents=True, exist_ok=True)
    (world_root / "policies" / "image" / "descriptor_layers").mkdir(parents=True, exist_ok=True)
    (world_root / "policies" / "image" / "tone_profiles").mkdir(parents=True, exist_ok=True)
    (world_root / "policies" / "image" / "registries").mkdir(parents=True, exist_ok=True)

    (world_root / "policies" / "translation" / "prompts" / "ic" / "default_v1.txt").write_text(
        "ic prompt",
        encoding="utf-8",
    )
    (world_root / "policies" / "image" / "descriptor_layers" / "id_card_v1.txt").write_text(
        "descriptor",
        encoding="utf-8",
    )
    (world_root / "policies" / "image" / "tone_profiles" / "ledger_engraving_v1.json").write_text(
        '{"name":"ledger_engraving_v1"}', encoding="utf-8"
    )
    (world_root / "policies" / "image" / "registries" / "species_registry.yaml").write_text(
        "registry: { id: species_registry, version: 1, kind: species }",
        encoding="utf-8",
    )
    (world_root / "policies" / "image" / "registries" / "clothing_registry.yaml").write_text(
        "registry: { id: clothing_registry, version: 1, kind: clothing }",
        encoding="utf-8",
    )


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


@pytest.mark.unit
def test_axis_policy_loader_prefers_manifest_axis_paths(tmp_path: Path) -> None:
    """When manifest exists, axis payloads should come from manifest-referenced paths."""
    world_id = "manifest_world"
    world_root = tmp_path / world_id
    _write_policy(
        world_root,
        """
version: 0.1.0
axes:
  legacy_only:
    values: [a, b]
    ordering:
      type: ordinal
      values: [a, b]
""",
        """
version: 0.1.0
axes:
  legacy_only:
    values:
      a: { min: 0.0, max: 0.5 }
      b: { min: 0.5, max: 1.0 }
""",
    )
    _write_manifest_axis_paths(world_root)
    (world_root / "policies" / "axis" / "axes.yaml").write_text(
        """
version: 0.1.0
axes:
  manifest_only:
    values: [x, y]
    ordering:
      type: ordinal
      values: [x, y]
""",
        encoding="utf-8",
    )
    (world_root / "policies" / "axis" / "thresholds.yaml").write_text(
        """
version: 0.1.0
axes:
  manifest_only:
    values:
      x: { min: 0.0, max: 0.5 }
      y: { min: 0.5, max: 1.0 }
""",
        encoding="utf-8",
    )
    (world_root / "policies" / "axis" / "resolution.yaml").write_text(
        "version: '1.0'\n", encoding="utf-8"
    )

    loader = AxisPolicyLoader(worlds_root=tmp_path)
    _payload, report = loader.load(world_id)

    assert report.axes == ["manifest_only"]
    assert "ordering missing for axis: manifest_only" not in report.missing_components
    assert "thresholds missing for axis: manifest_only" not in report.missing_components


@pytest.mark.unit
def test_axis_policy_loader_manifest_mode_does_not_fallback_to_default_axis_paths(
    tmp_path: Path,
) -> None:
    """When manifest exists, missing manifest assets must not use non-manifest axis files."""
    world_id = "manifest_missing_axis_files"
    world_root = tmp_path / world_id
    _write_policy(
        world_root,
        """
version: 0.1.0
axes:
  legacy_only:
    values: [a, b]
    ordering:
      type: ordinal
      values: [a, b]
""",
        """
version: 0.1.0
axes:
  legacy_only:
    values:
      a: { min: 0.0, max: 0.5 }
      b: { min: 0.5, max: 1.0 }
""",
    )
    _write_manifest_axis_paths(world_root)
    manifest_path = world_root / "policies" / "manifest.yaml"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        manifest_text.replace("policies/axis/axes.yaml", "policies/axis/missing_axes.yaml").replace(
            "policies/axis/thresholds.yaml", "policies/axis/missing_thresholds.yaml"
        ),
        encoding="utf-8",
    )

    loader = AxisPolicyLoader(worlds_root=tmp_path)
    _payload, report = loader.load(world_id)

    assert report.axes == []
    assert "axes list missing or empty" in report.missing_components
    assert (
        "manifest axis payload missing or invalid: axis.active_bundle" in report.missing_components
    )
    assert (
        "manifest threshold payload missing or invalid: axis.active_bundle"
        in report.missing_components
    )
