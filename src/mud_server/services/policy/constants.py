"""Canonical constants for policy service modules.

This module centralizes the policy contract constants that were previously
spread through a monolithic service file. Keeping these values in one place
reduces drift across validation, activation, publish, and import logic.
"""

from __future__ import annotations

_SUPPORTED_POLICY_TYPES = {
    "species_block",
    "clothing_block",
    "registry",
    "prompt",
    "descriptor_layer",
    "tone_profile",
    "axis_bundle",
    "manifest_bundle",
}

_LAYER1_POLICY_TYPES = {
    "species_block",
    "clothing_block",
    "prompt",
    "tone_profile",
}

_LAYER2_POLICY_TYPES = {
    "descriptor_layer",
    "registry",
}

_SPECIES_PILOT_POLICY_TYPE = "species_block"
_SPECIES_PILOT_NAMESPACE = "image.blocks.species"
_SUPPORTED_STATUSES = {"draft", "candidate", "active", "archived"}

_POLICY_SCHEMA_VERSION_V1 = "1.0"
_POLICY_EXPORT_SCHEMA_VERSION = "1.0"
_POLICY_EXPORT_WORLD_DIRNAME = "worlds"
_POLICY_EXPORT_REPO_NAME = "pipe-works-world-policies"
_POLICY_EXPORT_ROOT_ENV = "MUD_POLICY_EXPORTS_ROOT"
_POLICY_EXPORT_LATEST_FILENAME = "latest.json"
