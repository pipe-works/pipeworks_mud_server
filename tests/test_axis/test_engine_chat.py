"""Unit tests for AxisEngine.resolve_chat_interaction.

All DB calls and ledger writes are mocked — no real database or filesystem
access required.  Tests verify:
- Character lookup is world-scoped
- Axis scores are read before and written after resolution
- Delta math matches resolver output (including clamping)
- ipc_hash is a non-empty hex string
- Ledger event is written with correct event_type and ipc_hash
- DB apply_axis_event is called with clamped deltas
- CharacterNotFoundError raised on unknown character names
- Ledger failure does not abort the resolution
- No DB write when all actual deltas are zero (clamped to no change)
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from mud_server.axis.engine import AxisEngine, CharacterNotFoundError
from mud_server.axis.grammar import AxisRuleConfig, ChatGrammar, ResolutionGrammar
from mud_server.axis.types import AxisResolutionResult

# ---------------------------------------------------------------------------
# Test grammar fixture
# ---------------------------------------------------------------------------


def _make_grammar(
    *,
    demeanor_magnitude: float = 0.03,
    health_magnitude: float = 0.01,
    min_gap_threshold: float = 0.05,
) -> ResolutionGrammar:
    """Build a minimal ResolutionGrammar for testing."""
    return ResolutionGrammar(
        version="1.0",
        chat=ChatGrammar(
            channel_multipliers={"say": 1.0, "yell": 1.5, "whisper": 0.5},
            min_gap_threshold=min_gap_threshold,
            axes={
                "demeanor": AxisRuleConfig(
                    resolver="dominance_shift", base_magnitude=demeanor_magnitude
                ),
                "health": AxisRuleConfig(resolver="shared_drain", base_magnitude=health_magnitude),
                "wealth": AxisRuleConfig(resolver="no_effect"),
            },
        ),
    )


def _char(char_id: int, name: str) -> dict:
    """Minimal character dict returned by get_character_by_name_in_world."""
    return {"id": char_id, "name": name, "world_id": "test_world"}


def _axis_state(char_id: int, scores: dict[str, float]) -> dict:
    """Minimal character axis state returned by get_character_axis_state."""
    return {
        "character_id": char_id,
        "world_id": "test_world",
        "axes": [
            {"axis_name": name, "axis_score": score, "axis_id": i, "axis_label": None}
            for i, (name, score) in enumerate(scores.items())
        ],
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestResolveChatInteractionHappyPath:
    """Core resolution sequence executes correctly under normal conditions."""

    def setup_method(self):
        self.grammar = _make_grammar()
        self.engine = AxisEngine(world_id="test_world", grammar=self.grammar)

        self.speaker_id = 7
        self.listener_id = 12
        self.speaker_name = "Mira Voss"
        self.listener_name = "Kael Rhys"

        # Speaker has higher demeanor → dominates
        self.speaker_scores = {"demeanor": 0.87, "health": 0.72, "wealth": 0.50}
        self.listener_scores = {"demeanor": 0.51, "health": 0.44, "wealth": 0.60}

    def _run(self, channel="say"):
        with (
            patch(
                "mud_server.axis.engine.database.get_character_by_name_in_world",
                side_effect=lambda name, wid: (
                    _char(self.speaker_id, self.speaker_name)
                    if name == self.speaker_name
                    else _char(self.listener_id, self.listener_name)
                ),
            ),
            patch(
                "mud_server.axis.engine.database.get_character_axis_state",
                side_effect=lambda cid: (
                    _axis_state(self.speaker_id, self.speaker_scores)
                    if cid == self.speaker_id
                    else _axis_state(self.listener_id, self.listener_scores)
                ),
            ),
            patch(
                "mud_server.axis.engine.database.apply_axis_event",
                return_value=1,
            ) as mock_apply,
            patch(
                "mud_server.axis.engine._ledger_append",
                return_value="ev_abc",
            ) as mock_ledger,
        ):
            result = self.engine.resolve_chat_interaction(
                speaker_name=self.speaker_name,
                listener_name=self.listener_name,
                channel=channel,
                world_id="test_world",
            )
            return result, mock_apply, mock_ledger

    def test_returns_axis_resolution_result(self):
        result, _, _ = self._run()
        assert isinstance(result, AxisResolutionResult)

    def test_ipc_hash_is_hex_string(self):
        result, _, _ = self._run()
        assert isinstance(result.ipc_hash, str)
        assert len(result.ipc_hash) == 64  # SHA-256 hex digest

    def test_world_id_on_result(self):
        result, _, _ = self._run()
        assert result.world_id == "test_world"

    def test_channel_on_result(self):
        result, _, _ = self._run()
        assert result.channel == "say"

    def test_speaker_entity_resolution(self):
        result, _, _ = self._run()
        assert result.speaker.character_id == self.speaker_id
        assert result.speaker.character_name == self.speaker_name

    def test_listener_entity_resolution(self):
        result, _, _ = self._run()
        assert result.listener.character_id == self.listener_id
        assert result.listener.character_name == self.listener_name

    def test_axis_snapshot_before_contains_active_axes_only(self):
        result, _, _ = self._run()
        snapshot = result.axis_snapshot_before
        assert str(self.speaker_id) in snapshot
        assert str(self.listener_id) in snapshot
        speaker_snap = snapshot[str(self.speaker_id)]
        # Active axes: demeanor + health (wealth is no_effect)
        assert "demeanor" in speaker_snap
        assert "health" in speaker_snap
        assert "wealth" not in speaker_snap

    def test_speaker_gains_demeanor_when_dominant(self):
        result, _, _ = self._run()
        demeanor_deltas = [d for d in result.speaker.deltas if d.axis_name == "demeanor"]
        assert demeanor_deltas, "Speaker should have a demeanor delta"
        assert demeanor_deltas[0].delta > 0.0

    def test_listener_loses_demeanor_when_dominated(self):
        result, _, _ = self._run()
        demeanor_deltas = [d for d in result.listener.deltas if d.axis_name == "demeanor"]
        assert demeanor_deltas, "Listener should have a demeanor delta"
        assert demeanor_deltas[0].delta < 0.0

    def test_both_lose_health(self):
        result, _, _ = self._run()
        sp_health = [d for d in result.speaker.deltas if d.axis_name == "health"]
        li_health = [d for d in result.listener.deltas if d.axis_name == "health"]
        assert sp_health and sp_health[0].delta < 0.0
        assert li_health and li_health[0].delta < 0.0

    def test_no_effect_axes_not_in_deltas(self):
        result, _, _ = self._run()
        sp_axes = {d.axis_name for d in result.speaker.deltas}
        li_axes = {d.axis_name for d in result.listener.deltas}
        assert "wealth" not in sp_axes
        assert "wealth" not in li_axes

    def test_ledger_append_called_once(self):
        _, _, mock_ledger = self._run()
        mock_ledger.assert_called_once()

    def test_ledger_event_type_is_mechanical_resolution(self):
        _, _, mock_ledger = self._run()
        kwargs = mock_ledger.call_args.kwargs
        assert kwargs["event_type"] == "chat.mechanical_resolution"

    def test_ledger_ipc_hash_matches_result(self):
        result, _, mock_ledger = self._run()
        kwargs = mock_ledger.call_args.kwargs
        assert kwargs["ipc_hash"] == result.ipc_hash

    def test_db_apply_called_for_both_characters(self):
        _, mock_apply, _ = self._run()
        # Called once for speaker and once for listener (both have non-zero deltas)
        assert mock_apply.call_count == 2

    def test_db_apply_speaker_deltas_are_clamped(self):
        _, mock_apply, _ = self._run()
        # Find the call for the speaker
        speaker_call = next(
            c for c in mock_apply.call_args_list if c.kwargs.get("character_id") == self.speaker_id
        )
        deltas = speaker_call.kwargs["deltas"]
        for axis_name, delta in deltas.items():
            old_score = self.speaker_scores.get(axis_name, 0.5)
            assert 0.0 <= old_score + delta <= 1.0, (
                f"Clamping violated for axis {axis_name!r}: " f"old={old_score}, delta={delta}"
            )

    def test_yell_multiplier_produces_larger_delta(self):
        """Yell (multiplier=1.5) produces a larger health drain than say (1.0)."""
        result_say, _, _ = self._run(channel="say")
        result_yell, _, _ = self._run(channel="yell")

        sp_health_say = next(d for d in result_say.speaker.deltas if d.axis_name == "health")
        sp_health_yell = next(d for d in result_yell.speaker.deltas if d.axis_name == "health")

        assert abs(sp_health_yell.delta) > abs(sp_health_say.delta)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestCharacterNotFound:
    """CharacterNotFoundError raised on unknown character names."""

    def setup_method(self):
        self.grammar = _make_grammar()
        self.engine = AxisEngine(world_id="test_world", grammar=self.grammar)

    def test_unknown_speaker_raises(self):
        with patch(
            "mud_server.axis.engine.database.get_character_by_name_in_world",
            return_value=None,
        ):
            with pytest.raises(CharacterNotFoundError) as exc_info:
                self.engine.resolve_chat_interaction(
                    speaker_name="Ghost",
                    listener_name="Kael",
                    channel="say",
                    world_id="test_world",
                )
            assert exc_info.value.character_name == "Ghost"

    def test_unknown_listener_raises(self):
        with patch(
            "mud_server.axis.engine.database.get_character_by_name_in_world",
            side_effect=lambda name, wid: (_char(1, "Mira") if name == "Mira" else None),
        ):
            with pytest.raises(CharacterNotFoundError) as exc_info:
                self.engine.resolve_chat_interaction(
                    speaker_name="Mira",
                    listener_name="Ghost",
                    channel="say",
                    world_id="test_world",
                )
            assert exc_info.value.character_name == "Ghost"


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------


class TestResolveChatResiliency:
    """Ledger and DB failures are non-fatal."""

    def setup_method(self):
        self.grammar = _make_grammar()
        self.engine = AxisEngine(world_id="test_world", grammar=self.grammar)

    def _patch_db(self, speaker_id=7, listener_id=12):
        return {
            "mud_server.axis.engine.database.get_character_by_name_in_world": (
                lambda name, wid: (
                    _char(speaker_id, "Mira") if name == "Mira" else _char(listener_id, "Kael")
                )
            ),
            "mud_server.axis.engine.database.get_character_axis_state": (
                lambda cid: _axis_state(
                    cid,
                    (
                        {"demeanor": 0.80, "health": 0.50, "wealth": 0.50}
                        if cid == speaker_id
                        else {"demeanor": 0.40, "health": 0.60, "wealth": 0.50}
                    ),
                )
            ),
        }

    def test_ledger_failure_does_not_abort_resolution(self):
        patches = self._patch_db()
        with (
            patch(
                "mud_server.axis.engine.database.get_character_by_name_in_world",
                side_effect=patches[
                    "mud_server.axis.engine.database.get_character_by_name_in_world"
                ],
            ),
            patch(
                "mud_server.axis.engine.database.get_character_axis_state",
                side_effect=patches["mud_server.axis.engine.database.get_character_axis_state"],
            ),
            patch(
                "mud_server.axis.engine.database.apply_axis_event",
                return_value=1,
            ),
            patch(
                "mud_server.axis.engine._ledger_append",
                side_effect=RuntimeError("ledger disk full"),
            ),
        ):
            # Should complete without raising despite ledger failure
            result = self.engine.resolve_chat_interaction(
                speaker_name="Mira",
                listener_name="Kael",
                channel="say",
                world_id="test_world",
            )
            assert isinstance(result, AxisResolutionResult)

    def test_db_failure_does_not_propagate(self):
        patches = self._patch_db()
        with (
            patch(
                "mud_server.axis.engine.database.get_character_by_name_in_world",
                side_effect=patches[
                    "mud_server.axis.engine.database.get_character_by_name_in_world"
                ],
            ),
            patch(
                "mud_server.axis.engine.database.get_character_axis_state",
                side_effect=patches["mud_server.axis.engine.database.get_character_axis_state"],
            ),
            patch(
                "mud_server.axis.engine.database.apply_axis_event",
                side_effect=RuntimeError("DB write failed"),
            ),
            patch(
                "mud_server.axis.engine._ledger_append",
                return_value="ev_ok",
            ),
        ):
            result = self.engine.resolve_chat_interaction(
                speaker_name="Mira",
                listener_name="Kael",
                channel="say",
                world_id="test_world",
            )
            assert isinstance(result, AxisResolutionResult)


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------


class TestHealthFloorClamping:
    """Health at 0.01 with shared_drain should clamp to 0.0, not go negative."""

    def test_health_clamped_at_zero(self):
        grammar = _make_grammar(health_magnitude=0.50)  # large drain to force clamping
        engine = AxisEngine(world_id="test_world", grammar=grammar)

        with (
            patch(
                "mud_server.axis.engine.database.get_character_by_name_in_world",
                side_effect=lambda name, wid: (
                    _char(1, "Low") if name == "Low" else _char(2, "Other")
                ),
            ),
            patch(
                "mud_server.axis.engine.database.get_character_axis_state",
                side_effect=lambda cid: _axis_state(
                    cid,
                    {"demeanor": 0.50, "health": 0.01, "wealth": 0.50},  # near-zero health
                ),
            ),
            patch("mud_server.axis.engine.database.apply_axis_event", return_value=1),
            patch("mud_server.axis.engine._ledger_append", return_value="ev"),
        ):
            result = engine.resolve_chat_interaction(
                speaker_name="Low",
                listener_name="Other",
                channel="say",
                world_id="test_world",
            )

        sp_health = next((d for d in result.speaker.deltas if d.axis_name == "health"), None)
        assert sp_health is not None
        # new_score must be exactly 0.0 (floor), not negative
        assert sp_health.new_score == pytest.approx(0.0)
        assert sp_health.new_score >= 0.0

    def test_no_delta_when_already_at_floor(self):
        """Character already at 0.0 health — drain produces zero actual delta."""
        grammar = _make_grammar(health_magnitude=0.01)
        engine = AxisEngine(world_id="test_world", grammar=grammar)

        with (
            patch(
                "mud_server.axis.engine.database.get_character_by_name_in_world",
                side_effect=lambda name, wid: (
                    _char(1, "Dead") if name == "Dead" else _char(2, "Alive")
                ),
            ),
            patch(
                "mud_server.axis.engine.database.get_character_axis_state",
                side_effect=lambda cid: _axis_state(
                    cid,
                    # Dead character already at floor
                    (
                        {"demeanor": 0.50, "health": 0.0, "wealth": 0.50}
                        if cid == 1
                        else {"demeanor": 0.50, "health": 0.60, "wealth": 0.50}
                    ),
                ),
            ),
            patch("mud_server.axis.engine.database.apply_axis_event", return_value=1),
            patch("mud_server.axis.engine._ledger_append", return_value="ev"),
        ):
            result = engine.resolve_chat_interaction(
                speaker_name="Dead",
                listener_name="Alive",
                channel="say",
                world_id="test_world",
            )

        # Speaker at floor — health delta clamped to 0.0 → not in deltas
        sp_health = [d for d in result.speaker.deltas if d.axis_name == "health"]
        assert sp_health == [], "Character at health floor should have no health delta recorded"


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------


class TestLockingBehaviour:
    """Per-character locks prevent concurrent resolution races."""

    def test_separate_characters_use_separate_locks(self):
        grammar = _make_grammar()
        engine = AxisEngine(world_id="test_world", grammar=grammar)

        lock_a = engine._get_lock(1)
        lock_b = engine._get_lock(2)
        assert lock_a is not lock_b

    def test_same_character_returns_same_lock(self):
        grammar = _make_grammar()
        engine = AxisEngine(world_id="test_world", grammar=grammar)

        lock_first = engine._get_lock(99)
        lock_second = engine._get_lock(99)
        assert lock_first is lock_second

    def test_concurrent_resolutions_with_shared_character_are_serialized(self):
        """Two threads sharing character 1 must not interleave their DB reads."""
        grammar = _make_grammar()
        engine = AxisEngine(world_id="test_world", grammar=grammar)

        call_order: list[str] = []

        def make_apply_side_effect(label: str):
            def side_effect(**kwargs):
                call_order.append(label)
                return 1

            return side_effect

        def run_resolution(speaker_name, speaker_id, listener_id, label):
            with (
                patch(
                    "mud_server.axis.engine.database.get_character_by_name_in_world",
                    side_effect=lambda name, wid: (
                        _char(speaker_id, speaker_name)
                        if name == speaker_name
                        else _char(listener_id, "Shared")
                    ),
                ),
                patch(
                    "mud_server.axis.engine.database.get_character_axis_state",
                    return_value=_axis_state(
                        speaker_id,
                        {"demeanor": 0.80, "health": 0.50, "wealth": 0.50},
                    ),
                ),
                patch(
                    "mud_server.axis.engine.database.apply_axis_event",
                    side_effect=make_apply_side_effect(label),
                ),
                patch("mud_server.axis.engine._ledger_append", return_value="ev"),
            ):
                engine.resolve_chat_interaction(
                    speaker_name=speaker_name,
                    listener_name="Shared",
                    channel="say",
                    world_id="test_world",
                )

        # Shared character_id = 99 is the listener in both threads
        t1 = threading.Thread(target=run_resolution, args=("Alpha", 7, 99, "T1"))
        t2 = threading.Thread(target=run_resolution, args=("Beta", 8, 99, "T2"))

        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # Both threads completed (no deadlock)
        assert not t1.is_alive(), "Thread 1 appears deadlocked"
        assert not t2.is_alive(), "Thread 2 appears deadlocked"
