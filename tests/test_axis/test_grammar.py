"""Unit tests for the resolution grammar loader.

Tests cover happy-path loading from real world fixtures and error cases
for missing files and invalid YAML content.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mud_server.axis.grammar import (
    AxisRuleConfig,
    ChatGrammar,
    ResolutionGrammar,
    load_resolution_grammar,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_grammar(tmp_path: Path, content: dict | str) -> Path:
    """Write a resolution.yaml to a tmp world_root and return the world_root."""
    policies = tmp_path / "policies"
    policies.mkdir()
    grammar_path = policies / "resolution.yaml"
    if isinstance(content, dict):
        grammar_path.write_text(yaml.dump(content))
    else:
        grammar_path.write_text(content)
    return tmp_path


_VALID_GRAMMAR_DICT: dict = {
    "version": "1.0",
    "interactions": {
        "chat": {
            "channel_multipliers": {"say": 1.0, "yell": 1.5, "whisper": 0.5},
            "min_gap_threshold": 0.05,
            "axes": {
                "demeanor": {"resolver": "dominance_shift", "base_magnitude": 0.03},
                "health": {"resolver": "shared_drain", "base_magnitude": 0.01},
                "wealth": {"resolver": "no_effect"},
            },
        }
    },
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestLoadResolutionGrammarHappyPath:
    """Grammar loads correctly from a valid YAML file."""

    def test_returns_resolution_grammar(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        assert isinstance(grammar, ResolutionGrammar)

    def test_version_parsed(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        assert grammar.version == "1.0"

    def test_chat_grammar_type(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        assert isinstance(grammar.chat, ChatGrammar)

    def test_channel_multipliers(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        assert grammar.chat.channel_multipliers["say"] == pytest.approx(1.0)
        assert grammar.chat.channel_multipliers["yell"] == pytest.approx(1.5)
        assert grammar.chat.channel_multipliers["whisper"] == pytest.approx(0.5)

    def test_min_gap_threshold(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        assert grammar.chat.min_gap_threshold == pytest.approx(0.05)

    def test_axes_parsed(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        assert "demeanor" in grammar.chat.axes
        assert "health" in grammar.chat.axes
        assert "wealth" in grammar.chat.axes

    def test_axis_rule_config_type(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        assert isinstance(grammar.chat.axes["demeanor"], AxisRuleConfig)

    def test_dominance_shift_axis(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        rule = grammar.chat.axes["demeanor"]
        assert rule.resolver == "dominance_shift"
        assert rule.base_magnitude == pytest.approx(0.03)

    def test_shared_drain_axis(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        rule = grammar.chat.axes["health"]
        assert rule.resolver == "shared_drain"
        assert rule.base_magnitude == pytest.approx(0.01)

    def test_no_effect_axis_defaults_magnitude_zero(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        rule = grammar.chat.axes["wealth"]
        assert rule.resolver == "no_effect"
        assert rule.base_magnitude == pytest.approx(0.0)

    def test_grammar_is_immutable(self, tmp_path):
        world_root = _write_grammar(tmp_path, _VALID_GRAMMAR_DICT)
        grammar = load_resolution_grammar(world_root)
        with pytest.raises((TypeError, AttributeError)):
            grammar.version = "2.0"  # type: ignore[misc]

    def test_real_pipeworks_web_grammar_loads(self):
        """Smoke test against the real pipeworks_web grammar file."""
        repo_root = Path(__file__).parent.parent.parent
        world_root = repo_root / "data" / "worlds" / "pipeworks_web"
        grammar = load_resolution_grammar(world_root)
        assert grammar.version == "1.0"
        assert "demeanor" in grammar.chat.axes
        assert "health" in grammar.chat.axes

    def test_real_daily_undertaking_grammar_loads(self):
        """Smoke test against the real daily_undertaking grammar file."""
        repo_root = Path(__file__).parent.parent.parent
        world_root = repo_root / "data" / "worlds" / "daily_undertaking"
        grammar = load_resolution_grammar(world_root)
        assert grammar.version == "1.0"
        assert "demeanor" in grammar.chat.axes


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestLoadResolutionGrammarErrors:
    """Grammar loader raises on missing file or invalid content."""

    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_resolution_grammar(tmp_path)

    def test_missing_version_raises_value_error(self, tmp_path):
        bad = {k: v for k, v in _VALID_GRAMMAR_DICT.items() if k != "version"}
        world_root = _write_grammar(tmp_path, bad)
        with pytest.raises(ValueError, match="version"):
            load_resolution_grammar(world_root)

    def test_missing_interactions_raises_value_error(self, tmp_path):
        bad = {k: v for k, v in _VALID_GRAMMAR_DICT.items() if k != "interactions"}
        world_root = _write_grammar(tmp_path, bad)
        with pytest.raises(ValueError, match="interactions"):
            load_resolution_grammar(world_root)

    def test_missing_chat_block_raises_value_error(self, tmp_path):
        bad = {**_VALID_GRAMMAR_DICT, "interactions": {}}
        world_root = _write_grammar(tmp_path, bad)
        with pytest.raises(ValueError, match="chat"):
            load_resolution_grammar(world_root)

    def test_missing_channel_multipliers_raises_value_error(self, tmp_path):
        chat = {
            k: v
            for k, v in _VALID_GRAMMAR_DICT["interactions"]["chat"].items()
            if k != "channel_multipliers"
        }
        bad = {**_VALID_GRAMMAR_DICT, "interactions": {"chat": chat}}
        world_root = _write_grammar(tmp_path, bad)
        with pytest.raises(ValueError, match="channel_multipliers"):
            load_resolution_grammar(world_root)

    def test_missing_required_channel_raises_value_error(self, tmp_path):
        chat = {
            **_VALID_GRAMMAR_DICT["interactions"]["chat"],
            "channel_multipliers": {"say": 1.0, "yell": 1.5},  # missing whisper
        }
        bad = {**_VALID_GRAMMAR_DICT, "interactions": {"chat": chat}}
        world_root = _write_grammar(tmp_path, bad)
        with pytest.raises(ValueError, match="whisper"):
            load_resolution_grammar(world_root)

    def test_invalid_resolver_name_raises_value_error(self, tmp_path):
        chat = {
            **_VALID_GRAMMAR_DICT["interactions"]["chat"],
            "axes": {
                "demeanor": {"resolver": "unknown_resolver", "base_magnitude": 0.03},
            },
        }
        bad = {**_VALID_GRAMMAR_DICT, "interactions": {"chat": chat}}
        world_root = _write_grammar(tmp_path, bad)
        with pytest.raises(ValueError, match="resolver"):
            load_resolution_grammar(world_root)

    def test_top_level_not_mapping_raises_value_error(self, tmp_path):
        world_root = _write_grammar(tmp_path, "- just a list\n- not a mapping\n")
        with pytest.raises(ValueError):
            load_resolution_grammar(world_root)
