"""Tests for manifest-driven policy loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from mud_server.policies import PolicyManifestLoader


def _write(path: Path, content: str) -> None:
    """Write one UTF-8 test fixture file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_complete_manifest_fixture(world_root: Path) -> None:
    """Create one complete manifest policy package fixture."""
    _write(
        world_root / "policies" / "manifest.yaml",
        """
schema_version: 0.1.0
policy_schema: pipeworks_policy_v1
world_id: test_world
policy_bundle:
  id: test_bundle
  version: 1
identity_contract:
  fixed_traits:
    gender:
      type: enum
      allowed_values: [male, female]
      required: true
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
""",
    )
    _write(world_root / "policies" / "axis" / "axes.yaml", "axes: { wealth: {} }\n")
    _write(world_root / "policies" / "axis" / "thresholds.yaml", "axes: { wealth: {} }\n")
    _write(world_root / "policies" / "axis" / "resolution.yaml", 'version: "1.0"\n')
    _write(
        world_root / "policies" / "translation" / "prompts" / "ic" / "default_v1.txt",
        "IC PROMPT {{profile_summary}}\n",
    )
    _write(
        world_root / "policies" / "image" / "descriptor_layers" / "id_card_v1.txt",
        "Descriptor layer content.\n",
    )
    _write(
        world_root / "policies" / "image" / "tone_profiles" / "ledger_engraving_v1.json",
        '{"name":"ledger_engraving_v1"}\n',
    )
    _write(
        world_root / "policies" / "image" / "registries" / "species_registry.yaml",
        "registry: { id: species_registry, version: 1, kind: species }\nentries: []\n",
    )
    _write(
        world_root / "policies" / "image" / "registries" / "clothing_registry.yaml",
        "registry: { id: clothing_registry, version: 1, kind: clothing }\nslots: {}\n",
    )


@pytest.mark.unit
def test_policy_manifest_loader_complete_fixture(tmp_path: Path) -> None:
    """Complete fixtures should load all references with no missing components."""
    world_id = "test_world"
    world_root = tmp_path / world_id
    _write_complete_manifest_fixture(world_root)

    loader = PolicyManifestLoader(worlds_root=tmp_path)
    payload, report = loader.load(world_id)

    assert report.policy_schema == "pipeworks_policy_v1"
    assert report.bundle_id == "test_bundle"
    assert report.bundle_version == 1
    assert report.composition_order == [
        "species_canon_block",
        "descriptor_layer_output",
        "clothing_block",
        "tone_profile_block",
    ]
    assert report.required_runtime_inputs[0] == "entity.identity.gender"
    assert report.missing_components == []
    assert isinstance(payload["axis"]["axes"], dict)
    assert isinstance(payload["axis"]["thresholds"], dict)
    assert isinstance(payload["axis"]["resolution"], dict)
    assert isinstance(payload["translation"]["active_prompt"], str)
    assert isinstance(payload["image"]["descriptor_layer"], str)
    assert isinstance(payload["image"]["tone_profile"], dict)
    assert isinstance(payload["image"]["species_registry"], dict)
    assert isinstance(payload["image"]["clothing_registry"], dict)


@pytest.mark.unit
def test_policy_manifest_loader_missing_manifest(tmp_path: Path) -> None:
    """Missing manifest files should return one clear missing-component message."""
    world_id = "missing_manifest_world"
    (tmp_path / world_id / "policies").mkdir(parents=True, exist_ok=True)

    loader = PolicyManifestLoader(worlds_root=tmp_path)
    payload, report = loader.load(world_id)

    assert payload["manifest"] == {}
    assert report.missing_components == ["manifest missing: policies/manifest.yaml"]


@pytest.mark.unit
def test_policy_manifest_loader_requires_gender_runtime_input(tmp_path: Path) -> None:
    """Missing ``entity.identity.gender`` input should be reported."""
    world_id = "missing_gender_world"
    world_root = tmp_path / world_id
    _write_complete_manifest_fixture(world_root)

    manifest_path = world_root / "policies" / "manifest.yaml"
    content = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        content.replace("      - entity.identity.gender\n", ""), encoding="utf-8"
    )

    loader = PolicyManifestLoader(worlds_root=tmp_path)
    _payload, report = loader.load(world_id)

    assert (
        "manifest required runtime input missing: entity.identity.gender"
        in report.missing_components
    )


@pytest.mark.unit
def test_policy_manifest_loader_missing_referenced_asset(tmp_path: Path) -> None:
    """Missing referenced files should be reported with alias context."""
    world_id = "missing_asset_world"
    world_root = tmp_path / world_id
    _write_complete_manifest_fixture(world_root)

    # Simulate missing registry file to verify alias-based reporting.
    (world_root / "policies" / "image" / "registries" / "species_registry.yaml").unlink()

    loader = PolicyManifestLoader(worlds_root=tmp_path)
    payload, report = loader.load(world_id)

    assert payload["image"]["species_registry"] is None
    assert (
        "referenced asset missing (image.species_registry): "
        "policies/image/registries/species_registry.yaml"
    ) in report.missing_components


@pytest.mark.unit
def test_policy_manifest_loader_load_from_world_root(tmp_path: Path) -> None:
    """Explicit world-root loading should support callers with direct world roots."""
    world_id = "test_world"
    world_root = tmp_path / "direct_world_root"
    _write_complete_manifest_fixture(world_root)

    loader = PolicyManifestLoader(worlds_root=tmp_path)
    _payload, report = loader.load_from_world_root(world_id=world_id, world_root=world_root)

    assert report.policy_schema == "pipeworks_policy_v1"
    assert report.bundle_id == "test_bundle"
    assert report.missing_components == []


@pytest.mark.unit
def test_policy_manifest_loader_pipeworks_web_data_package_is_complete() -> None:
    """The committed ``pipeworks_web`` manifest package should resolve without gaps."""
    loader = PolicyManifestLoader(worlds_root=Path("data/worlds"))
    payload, report = loader.load("pipeworks_web")

    assert report.policy_schema == "pipeworks_policy_v1"
    assert report.bundle_id == "pipeworks_web_default"
    assert report.missing_components == []
    assert isinstance(payload["axis"]["axes"], dict)
    assert isinstance(payload["translation"]["active_prompt"], str)
    assert isinstance(payload["image"]["species_registry"], dict)
