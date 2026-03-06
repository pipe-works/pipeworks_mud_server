"""Manifest-driven world policy loader.

This module introduces a read-only loader for world policy manifests.
It is intentionally conservative in phase 1:

- load one world's ``policies/manifest.yaml``
- validate required structural fields
- resolve referenced policy assets
- return a structured validation report without mutating runtime state

The loader does not perform prompt compilation; it only resolves and validates
policy package inputs required by downstream systems.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class PolicyManifestValidationReport:
    """Structured validation report for one world's policy manifest.

    Attributes:
        world_id: Target world identifier.
        policy_schema: Manifest policy schema identifier when present.
        bundle_id: Policy bundle id when present.
        bundle_version: Policy bundle version when present.
        required_runtime_inputs: Runtime input keys required by composition.
        composition_order: Ordered prompt composition blocks from manifest.
        referenced_paths: Referenced asset paths read from the manifest.
        resolved_paths: Absolute resolved file paths for referenced assets.
        missing_components: Human-readable validation and loading issues.
    """

    world_id: str
    policy_schema: str | None
    bundle_id: str | None
    bundle_version: int | str | None
    required_runtime_inputs: list[str]
    composition_order: list[str]
    referenced_paths: dict[str, str]
    resolved_paths: dict[str, str]
    missing_components: list[str]


class PolicyManifestLoader:
    """Load and validate manifest-driven policy assets for one world.

    The loader is deterministic and side-effect free:

    - no database access
    - no network access
    - no file writes

    It returns a payload dictionary suitable for downstream policy services
    plus a validation report that captures all missing/invalid components.
    """

    def __init__(self, *, worlds_root: Path) -> None:
        self._worlds_root = worlds_root

    def load(self, world_id: str) -> tuple[dict[str, Any], PolicyManifestValidationReport]:
        """Load one world's manifest and referenced assets.

        Args:
            world_id: Target world id under ``worlds_root``.

        Returns:
            Tuple of ``(payload, report)``. The payload includes loaded asset
            contents where available and ``None`` for unresolved entries.
        """
        world_root = self._worlds_root / world_id
        return self.load_from_world_root(world_id=world_id, world_root=world_root)

    def load_from_world_root(
        self, *, world_id: str, world_root: Path
    ) -> tuple[dict[str, Any], PolicyManifestValidationReport]:
        """Load one world's manifest using an explicit world root path.

        This path-based variant is used by lab/helper code that already holds
        the exact world root and should not re-derive it from ``world_id``.
        """
        policy_root = world_root / "policies"
        manifest_path = policy_root / "manifest.yaml"

        payload: dict[str, Any] = {
            "manifest": {},
            "axis": {"axes": None, "thresholds": None, "resolution": None},
            "translation": {"active_prompt": None},
            "image": {
                "descriptor_layer": None,
                "tone_profile": None,
                "species_registry": None,
                "clothing_registry": None,
                "composition_order": [],
                "required_runtime_inputs": [],
            },
        }
        missing_components: list[str] = []

        if not manifest_path.exists():
            missing_components.append("manifest missing: policies/manifest.yaml")
            report = PolicyManifestValidationReport(
                world_id=world_id,
                policy_schema=None,
                bundle_id=None,
                bundle_version=None,
                required_runtime_inputs=[],
                composition_order=[],
                referenced_paths={},
                resolved_paths={},
                missing_components=missing_components,
            )
            return payload, report

        manifest_payload = self._read_yaml(manifest_path, missing_components, "manifest")
        payload["manifest"] = manifest_payload

        required_runtime_inputs = self._expect_list(
            manifest_payload,
            ["image", "composition", "required_runtime_inputs"],
            missing_components=missing_components,
            missing_message="manifest missing required list: image.composition.required_runtime_inputs",
        )
        composition_order = self._expect_list(
            manifest_payload,
            ["image", "composition", "order"],
            missing_components=missing_components,
            missing_message="manifest missing required list: image.composition.order",
        )
        payload["image"]["required_runtime_inputs"] = required_runtime_inputs
        payload["image"]["composition_order"] = composition_order

        if "entity.identity.gender" not in required_runtime_inputs:
            missing_components.append(
                "manifest required runtime input missing: entity.identity.gender"
            )

        referenced_paths: dict[str, str] = {}
        resolved_paths: dict[str, str] = {}

        for alias, path_keys, missing_message in (
            (
                "axis.axes",
                ["axis", "active_bundle", "files", "axes"],
                "manifest missing required path: axis.active_bundle.files.axes",
            ),
            (
                "axis.thresholds",
                ["axis", "active_bundle", "files", "thresholds"],
                "manifest missing required path: axis.active_bundle.files.thresholds",
            ),
            (
                "axis.resolution",
                ["axis", "active_bundle", "files", "resolution"],
                "manifest missing required path: axis.active_bundle.files.resolution",
            ),
            (
                "translation.active_prompt",
                ["translation", "active_prompt", "path"],
                "manifest missing required path: translation.active_prompt.path",
            ),
            (
                "image.descriptor_layer",
                ["image", "descriptor_layer", "path"],
                "manifest missing required path: image.descriptor_layer.path",
            ),
            (
                "image.tone_profile",
                ["image", "tone_profile", "path"],
                "manifest missing required path: image.tone_profile.path",
            ),
            (
                "image.species_registry",
                ["image", "registries", "species"],
                "manifest missing required path: image.registries.species",
            ),
            (
                "image.clothing_registry",
                ["image", "registries", "clothing"],
                "manifest missing required path: image.registries.clothing",
            ),
        ):
            rel_path = self._expect_str(
                manifest_payload,
                path_keys,
                missing_components=missing_components,
                missing_message=missing_message,
            )
            if rel_path is None:
                continue
            referenced_paths[alias] = rel_path
            resolved = self._resolve_world_relative_path(world_root, rel_path)
            resolved_paths[alias] = str(resolved)

        payload["axis"]["axes"] = self._load_referenced_asset(
            "axis.axes",
            referenced_paths=referenced_paths,
            resolved_paths=resolved_paths,
            missing_components=missing_components,
            expected_kind="yaml",
        )
        payload["axis"]["thresholds"] = self._load_referenced_asset(
            "axis.thresholds",
            referenced_paths=referenced_paths,
            resolved_paths=resolved_paths,
            missing_components=missing_components,
            expected_kind="yaml",
        )
        payload["axis"]["resolution"] = self._load_referenced_asset(
            "axis.resolution",
            referenced_paths=referenced_paths,
            resolved_paths=resolved_paths,
            missing_components=missing_components,
            expected_kind="yaml",
        )
        payload["translation"]["active_prompt"] = self._load_referenced_asset(
            "translation.active_prompt",
            referenced_paths=referenced_paths,
            resolved_paths=resolved_paths,
            missing_components=missing_components,
            expected_kind="text",
        )
        payload["image"]["descriptor_layer"] = self._load_referenced_asset(
            "image.descriptor_layer",
            referenced_paths=referenced_paths,
            resolved_paths=resolved_paths,
            missing_components=missing_components,
            expected_kind="text",
        )
        payload["image"]["tone_profile"] = self._load_referenced_asset(
            "image.tone_profile",
            referenced_paths=referenced_paths,
            resolved_paths=resolved_paths,
            missing_components=missing_components,
            expected_kind="json",
        )
        payload["image"]["species_registry"] = self._load_referenced_asset(
            "image.species_registry",
            referenced_paths=referenced_paths,
            resolved_paths=resolved_paths,
            missing_components=missing_components,
            expected_kind="yaml",
        )
        payload["image"]["clothing_registry"] = self._load_referenced_asset(
            "image.clothing_registry",
            referenced_paths=referenced_paths,
            resolved_paths=resolved_paths,
            missing_components=missing_components,
            expected_kind="yaml",
        )

        report = PolicyManifestValidationReport(
            world_id=world_id,
            policy_schema=self._expect_str(
                manifest_payload,
                ["policy_schema"],
                missing_components=missing_components,
                missing_message="manifest missing required field: policy_schema",
            ),
            bundle_id=self._expect_str(
                manifest_payload,
                ["policy_bundle", "id"],
                missing_components=missing_components,
                missing_message="manifest missing required field: policy_bundle.id",
            ),
            bundle_version=self._get_nested(manifest_payload, ["policy_bundle", "version"]),
            required_runtime_inputs=required_runtime_inputs,
            composition_order=composition_order,
            referenced_paths=referenced_paths,
            resolved_paths=resolved_paths,
            missing_components=missing_components,
        )
        return payload, report

    def _load_referenced_asset(
        self,
        alias: str,
        *,
        referenced_paths: dict[str, str],
        resolved_paths: dict[str, str],
        missing_components: list[str],
        expected_kind: str,
    ) -> Any:
        """Load one referenced manifest asset by expected payload type."""
        rel_path = referenced_paths.get(alias)
        abs_path = resolved_paths.get(alias)
        if rel_path is None or abs_path is None:
            return None

        path = Path(abs_path)
        if not path.exists():
            missing_components.append(f"referenced asset missing ({alias}): {rel_path}")
            return None

        try:
            if expected_kind == "yaml":
                with path.open("r", encoding="utf-8") as handle:
                    return yaml.safe_load(handle) or {}
            if expected_kind == "json":
                return json.loads(path.read_text(encoding="utf-8"))
            if expected_kind == "text":
                return path.read_text(encoding="utf-8")
        except (OSError, json.JSONDecodeError, yaml.YAMLError):
            missing_components.append(f"referenced asset unreadable ({alias}): {rel_path}")
            return None

        missing_components.append(
            f"internal loader error: unsupported expected_kind={expected_kind}"
        )
        return None

    def _read_yaml(self, path: Path, missing_components: list[str], label: str) -> dict[str, Any]:
        """Read one YAML file as a mapping; report failures as missing components."""
        try:
            with path.open("r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
        except (OSError, yaml.YAMLError):
            missing_components.append(f"{label} unreadable: {path}")
            return {}

        if not isinstance(loaded, dict):
            missing_components.append(f"{label} invalid: expected mapping payload")
            return {}
        return loaded

    def _resolve_world_relative_path(self, world_root: Path, rel_path: str) -> Path:
        """Resolve one world-relative path from manifest to an absolute path."""
        return world_root / rel_path

    def _expect_str(
        self,
        payload: dict[str, Any],
        path_keys: list[str],
        *,
        missing_components: list[str],
        missing_message: str,
    ) -> str | None:
        """Extract a required string field from a nested mapping payload."""
        value = self._get_nested(payload, path_keys)
        if isinstance(value, str) and value.strip():
            return value
        missing_components.append(missing_message)
        return None

    def _expect_list(
        self,
        payload: dict[str, Any],
        path_keys: list[str],
        *,
        missing_components: list[str],
        missing_message: str,
    ) -> list[str]:
        """Extract a required list[str] field from a nested mapping payload."""
        value = self._get_nested(payload, path_keys)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        missing_components.append(missing_message)
        return []

    def _get_nested(self, payload: dict[str, Any], path_keys: list[str]) -> Any:
        """Return nested value by key path, or ``None`` when any segment is missing."""
        current: Any = payload
        for key in path_keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current
