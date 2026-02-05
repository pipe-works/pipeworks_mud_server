"""
Tests for user-configurable keybindings in the Admin TUI.

These tests focus on the JSON loading, merging, and normalization behavior
so the TUI can safely consume keybinding configuration overrides.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mud_server.admin_tui.keybindings import (
    DEFAULT_KEYBINDINGS,
    ENV_KEYBINDINGS_PATH,
    KeyBindings,
)


def _write_json(path: Path, payload: dict) -> None:
    """Helper to write JSON fixtures for keybinding tests."""
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_defaults_used_when_file_missing(tmp_path: Path) -> None:
    """Missing keybindings file should fall back to defaults."""
    missing_path = tmp_path / "missing.json"

    bindings = KeyBindings.load(path=missing_path)

    assert bindings.bindings == DEFAULT_KEYBINDINGS


def test_overrides_replace_action(tmp_path: Path) -> None:
    """Overrides should replace the full key list for a given action."""
    config_path = tmp_path / "keybindings.json"
    _write_json(config_path, {"next_tab": ["n"]})

    bindings = KeyBindings.load(path=config_path)

    assert bindings.get_keys("next_tab") == ["n"]
    assert bindings.get_keys("select") == DEFAULT_KEYBINDINGS["select"]


def test_wrapped_bindings_payload(tmp_path: Path) -> None:
    """Support the {"bindings": {...}} JSON format."""
    config_path = tmp_path / "keybindings.json"
    _write_json(config_path, {"bindings": {"select": ["enter"]}})

    bindings = KeyBindings.load(path=config_path)

    assert bindings.get_keys("select") == ["enter"]


def test_key_normalization(tmp_path: Path) -> None:
    """Keys should be trimmed and lowercased."""
    config_path = tmp_path / "keybindings.json"
    _write_json(config_path, {"select": [" Enter ", "SPACE"]})

    bindings = KeyBindings.load(path=config_path)

    assert bindings.get_keys("select") == ["enter", "space"]


def test_invalid_keys_do_not_override(tmp_path: Path) -> None:
    """Invalid key lists should not replace defaults."""
    config_path = tmp_path / "keybindings.json"
    _write_json(config_path, {"next_tab": [123, None]})

    bindings = KeyBindings.load(path=config_path)

    assert bindings.get_keys("next_tab") == DEFAULT_KEYBINDINGS["next_tab"]


def test_env_path_override(tmp_path: Path) -> None:
    """Environment variable should override the default file path."""
    config_path = tmp_path / "keybindings.json"
    _write_json(config_path, {"next_tab": ["n"]})

    with patch.dict(os.environ, {ENV_KEYBINDINGS_PATH: str(config_path)}, clear=True):
        bindings = KeyBindings.load()

    assert bindings.get_keys("next_tab") == ["n"]


def test_invalid_json_falls_back_to_defaults(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed JSON should be ignored with a safe fallback."""
    config_path = tmp_path / "keybindings.json"
    config_path.write_text("not-json", encoding="utf-8")

    bindings = KeyBindings.load(path=config_path)

    assert bindings.bindings == DEFAULT_KEYBINDINGS
    assert any("Failed to load keybindings" in record.message for record in caplog.records)
