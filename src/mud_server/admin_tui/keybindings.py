"""
User-configurable keybindings for the Admin TUI.

This module defines a small configuration layer for Textual keybindings so
users can customize navigation without editing source code. It supports:
- A default keybinding set (Tab, hjkl, Space select, etc.)
- Optional JSON overrides via a config file
- Safe fallback to defaults if the file is missing or invalid

Design Goals:
- Keep the format simple (JSON)
- Merge overrides on top of defaults
- Validate and normalize key strings
- Avoid crashing the TUI if config is malformed
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# =============================================================================
# DEFAULTS
# =============================================================================

# Default keybindings for the TUI. These are used when no user config exists
# or when a specific action has no override.
DEFAULT_KEYBINDINGS: dict[str, list[str]] = {
    # Tab navigation
    "next_tab": ["tab"],
    "prev_tab": ["shift+tab"],
    # Vim-style movement (also allow arrows via Textual defaults)
    "cursor_up": ["k"],
    "cursor_down": ["j"],
    "cursor_left": ["h"],
    "cursor_right": ["l"],
    # Selection
    "select": ["space", "enter"],
    # Session management
    "kick": ["x"],
}

# Environment variable to override the keybindings file path.
ENV_KEYBINDINGS_PATH = "MUD_TUI_KEYBINDINGS_PATH"

# Default location for user keybindings.
DEFAULT_KEYBINDINGS_PATH = Path.home() / ".config" / "pipeworks-admin-tui" / "keybindings.json"


# =============================================================================
# PUBLIC API
# =============================================================================


@dataclass(frozen=True)
class KeyBindings:
    """
    Immutable keybindings container.

    Attributes:
        bindings: Mapping of action -> list of keys (Textual key syntax).
    """

    bindings: dict[str, list[str]]

    def get_keys(self, action: str) -> list[str]:
        """Return the list of keys for an action, defaulting to empty list."""
        return list(self.bindings.get(action, []))

    @classmethod
    def load(cls, path: Path | None = None) -> KeyBindings:
        """
        Load keybindings from JSON, merged with defaults.

        Priority:
            1. Explicit path argument (if provided)
            2. ENV_KEYBINDINGS_PATH
            3. DEFAULT_KEYBINDINGS_PATH

        The JSON file can be either:
            { "bindings": { "next_tab": ["tab"] } }
        or:
            { "next_tab": ["tab"] }

        Invalid or missing files fall back to defaults.
        """
        file_path = _resolve_path(path)
        overrides: dict[str, list[str]] = {}

        if file_path and file_path.exists():
            try:
                overrides = _load_overrides(file_path)
            except Exception as exc:
                logger.warning("Failed to load keybindings from %s: %s", file_path, exc)

        merged = _merge_bindings(DEFAULT_KEYBINDINGS, overrides)
        return cls(bindings=merged)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _resolve_path(path: Path | None) -> Path | None:
    """Resolve the keybindings config path from args/env/defaults."""
    if path is not None:
        return path

    if ENV_KEYBINDINGS_PATH in os.environ:
        return Path(os.environ[ENV_KEYBINDINGS_PATH])

    return DEFAULT_KEYBINDINGS_PATH


def _load_overrides(path: Path) -> dict[str, list[str]]:
    """Load override bindings from JSON file with validation."""
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    # Accept either top-level mapping or {"bindings": {...}}.
    if isinstance(raw, dict) and "bindings" in raw:
        raw = raw.get("bindings")

    if not isinstance(raw, dict):
        raise ValueError("Keybindings JSON must be a mapping")

    overrides: dict[str, list[str]] = {}
    for action, keys in raw.items():
        if not isinstance(action, str):
            continue
        normalized_keys = _normalize_keys(keys)
        if normalized_keys:
            overrides[action] = normalized_keys

    return overrides


def _normalize_keys(keys: Any) -> list[str]:
    """Normalize a key or list of keys into a clean list of strings."""
    if isinstance(keys, str):
        return [_normalize_key(keys)] if _normalize_key(keys) else []

    if isinstance(keys, list):
        normalized: list[str] = []
        for key in keys:
            if not isinstance(key, str):
                continue
            normalized_key = _normalize_key(key)
            if normalized_key:
                normalized.append(normalized_key)
        return normalized

    return []


def _normalize_key(key: str) -> str:
    """Trim and lowercase a key string; return empty string if invalid."""
    cleaned = key.strip().lower()
    return cleaned


def _merge_bindings(
    defaults: dict[str, list[str]],
    overrides: dict[str, list[str]],
) -> dict[str, list[str]]:
    """
    Merge overrides on top of defaults.

    Overrides replace the entire key list for an action. Defaults remain
    for any action not specified in overrides.
    """
    merged = {action: list(keys) for action, keys in defaults.items()}
    for action, keys in overrides.items():
        merged[action] = list(keys)
    return merged
