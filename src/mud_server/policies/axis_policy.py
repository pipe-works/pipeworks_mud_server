"""Axis policy loader and validator for world packages.

This module loads world-specific axis definitions and threshold mappings
from policy files. It validates required components and produces a summary
report that can be logged or shown in admin tooling.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class AxisPolicyValidationReport:
    """Structured validation report for axis policy files.

    Attributes:
        world_id: World identifier associated with the policy.
        axes: Axis names discovered in the policy.
        ordering_present: Axis names with ordering definitions.
        ordering_definitions: Mapping of axis name to ordering payload.
        thresholds_present: Axis names with threshold definitions.
        thresholds_definitions: Mapping of axis name to threshold payload.
        missing_components: Human-readable missing/invalid entries.
        policy_hash: Deterministic hash of the policy payload.
        version: Policy version string when available.
    """

    world_id: str
    axes: list[str]
    ordering_present: list[str]
    ordering_definitions: dict[str, Any]
    thresholds_present: list[str]
    thresholds_definitions: dict[str, Any]
    missing_components: list[str]
    policy_hash: str
    version: str | None


class AxisPolicyLoader:
    """Load and validate axis policy files for a world."""

    def __init__(self, *, worlds_root: Path) -> None:
        self._worlds_root = worlds_root

    def load(self, world_id: str) -> tuple[dict[str, Any], AxisPolicyValidationReport]:
        """Load axis policy files for a world and return a validation report.

        Args:
            world_id: Target world id.

        Returns:
            Tuple of (policy_payload, validation_report).
        """
        policy_root = self._worlds_root / world_id / "policies"

        # Load policy files (empty dicts if missing) so validation can report gaps.
        axes_payload = self._read_yaml(policy_root / "axes.yaml")
        thresholds_payload = self._read_yaml(policy_root / "thresholds.yaml")

        # Extract axis names plus their ordering/threshold definitions.
        axes = list((axes_payload.get("axes") or {}).keys())
        ordering_present, ordering_definitions = self._extract_ordering_axes(axes_payload)
        thresholds_present, thresholds_definitions = self._extract_thresholds(thresholds_payload)

        # Validate required components for each axis.
        missing_components = self._validate_components(
            axes=axes,
            ordering_present=ordering_present,
            thresholds_present=thresholds_present,
        )

        # Hash the combined payload so the policy can be versioned/diffed reliably.
        payload = {
            "axes": axes_payload,
            "thresholds": thresholds_payload,
        }
        policy_hash = self._hash_payload(payload)
        version = axes_payload.get("version") or thresholds_payload.get("version")

        report = AxisPolicyValidationReport(
            world_id=world_id,
            axes=axes,
            ordering_present=ordering_present,
            ordering_definitions=ordering_definitions,
            thresholds_present=thresholds_present,
            thresholds_definitions=thresholds_definitions,
            missing_components=missing_components,
            policy_hash=policy_hash,
            version=version,
        )

        return payload, report

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        """Read a YAML file and return a dict; returns empty dict if missing."""
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def _extract_ordering_axes(
        self, axes_payload: dict[str, Any]
    ) -> tuple[list[str], dict[str, Any]]:
        """Extract axes that declare ordering definitions plus their payloads."""
        axes = axes_payload.get("axes") or {}
        ordering_axes = []
        ordering_definitions: dict[str, Any] = {}
        for axis_name, axis_data in axes.items():
            ordering = (axis_data or {}).get("ordering")
            if ordering and isinstance(ordering, dict):
                ordering_axes.append(axis_name)
                ordering_definitions[axis_name] = ordering
        return ordering_axes, ordering_definitions

    def _extract_thresholds(
        self, thresholds_payload: dict[str, Any]
    ) -> tuple[list[str], dict[str, Any]]:
        """Extract axes that declare thresholds plus their payloads."""
        axes = thresholds_payload.get("axes") or {}
        axis_names = list(axes.keys())
        return axis_names, axes

    def _validate_components(
        self,
        *,
        axes: list[str],
        ordering_present: list[str],
        thresholds_present: list[str],
    ) -> list[str]:
        """Return a list of missing component messages."""
        missing = []
        if not axes:
            missing.append("axes list missing or empty")

        for axis_name in axes:
            if axis_name not in ordering_present:
                missing.append(f"ordering missing for axis: {axis_name}")
            if axis_name not in thresholds_present:
                missing.append(f"thresholds missing for axis: {axis_name}")

        return missing

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        """Compute a deterministic hash for the policy payload."""
        serialized = yaml.safe_dump(payload, sort_keys=True)
        return sha256(serialized.encode("utf-8")).hexdigest()
