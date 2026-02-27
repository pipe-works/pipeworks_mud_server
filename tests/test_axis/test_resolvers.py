"""Unit tests for axis resolver functions.

All resolvers are pure functions — tests are straightforward arithmetic checks.
No fixtures, mocks, or database access required.
"""

import pytest

from mud_server.axis.resolvers import dominance_shift, no_effect, shared_drain


class TestNoEffect:
    """no_effect always returns (0.0, 0.0)."""

    def test_returns_zero_tuple(self):
        assert no_effect() == (0.0, 0.0)

    def test_return_type_is_tuple(self):
        result = no_effect()
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestSharedDrain:
    """shared_drain — both entities lose base_magnitude * multiplier."""

    def test_basic_drain(self):
        sp, li = shared_drain(base_magnitude=0.01, multiplier=1.0)
        assert sp == pytest.approx(-0.01)
        assert li == pytest.approx(-0.01)

    def test_yell_multiplier(self):
        sp, li = shared_drain(base_magnitude=0.01, multiplier=1.5)
        assert sp == pytest.approx(-0.015)
        assert li == pytest.approx(-0.015)

    def test_whisper_multiplier(self):
        sp, li = shared_drain(base_magnitude=0.01, multiplier=0.5)
        assert sp == pytest.approx(-0.005)
        assert li == pytest.approx(-0.005)

    def test_speaker_and_listener_are_equal(self):
        sp, li = shared_drain(base_magnitude=0.02, multiplier=1.3)
        assert sp == li

    def test_both_deltas_negative(self):
        sp, li = shared_drain(base_magnitude=0.01, multiplier=1.0)
        assert sp < 0.0
        assert li < 0.0


class TestDominanceShift:
    """dominance_shift — winner gains, loser loses; zero below threshold."""

    def test_speaker_dominates(self):
        """Speaker has higher score → speaker gains, listener loses."""
        sp, li = dominance_shift(
            0.80,
            0.50,
            base_magnitude=0.03,
            multiplier=1.0,
            min_gap_threshold=0.05,
        )
        gap = abs(0.80 - 0.50)  # 0.30
        expected = 0.03 * 1.0 * gap
        assert sp == pytest.approx(expected)
        assert li == pytest.approx(-expected)

    def test_listener_dominates(self):
        """Listener has higher score → listener gains, speaker loses."""
        sp, li = dominance_shift(
            0.40,
            0.80,
            base_magnitude=0.03,
            multiplier=1.0,
            min_gap_threshold=0.05,
        )
        gap = abs(0.40 - 0.80)  # 0.40
        expected = 0.03 * 1.0 * gap
        assert sp == pytest.approx(-expected)
        assert li == pytest.approx(expected)

    def test_below_gap_threshold_returns_zero(self):
        """Gap smaller than threshold → (0.0, 0.0)."""
        sp, li = dominance_shift(
            0.50,
            0.53,
            base_magnitude=0.03,
            multiplier=1.0,
            min_gap_threshold=0.05,
        )
        assert sp == 0.0
        assert li == 0.0

    def test_exact_threshold_produces_nonzero_delta(self):
        """Gap exactly equal to threshold is NOT below it — produces a real delta.

        The resolver uses strict ``<`` comparison: ``gap < min_gap_threshold``.
        When gap == threshold the condition is False, so the delta is computed.
        """
        sp, li = dominance_shift(
            0.50,
            0.55,
            base_magnitude=0.03,
            multiplier=1.0,
            min_gap_threshold=0.05,
        )
        # gap == 0.05 == threshold → gap < threshold is False → real delta
        assert li > 0.0  # listener (0.55) dominates
        assert sp < 0.0

    def test_just_above_threshold_produces_nonzero_delta(self):
        """Gap just above threshold → real delta produced."""
        sp, li = dominance_shift(
            0.50,
            0.56,
            base_magnitude=0.03,
            multiplier=1.0,
            min_gap_threshold=0.05,
        )
        # gap = 0.06, which is > 0.05
        assert li > 0.0  # listener dominates
        assert sp < 0.0

    def test_channel_multiplier_scales_delta(self):
        """Yell multiplier (1.5) produces larger delta than say (1.0)."""
        _, li_say = dominance_shift(
            0.40, 0.80, base_magnitude=0.03, multiplier=1.0, min_gap_threshold=0.05
        )
        _, li_yell = dominance_shift(
            0.40, 0.80, base_magnitude=0.03, multiplier=1.5, min_gap_threshold=0.05
        )
        assert li_yell == pytest.approx(li_say * 1.5)

    def test_equal_scores_returns_zero(self):
        """Exact tie — gap is zero, always below threshold."""
        sp, li = dominance_shift(
            0.60,
            0.60,
            base_magnitude=0.03,
            multiplier=1.0,
            min_gap_threshold=0.05,
        )
        assert sp == 0.0
        assert li == 0.0

    def test_delta_is_symmetric(self):
        """Speaker delta and listener delta are always equal in magnitude."""
        sp, li = dominance_shift(
            0.70,
            0.30,
            base_magnitude=0.03,
            multiplier=1.0,
            min_gap_threshold=0.05,
        )
        assert abs(sp) == pytest.approx(abs(li))
        assert sp > 0.0  # speaker wins

    def test_max_scores_uses_full_gap(self):
        """Gap of 1.0 (0.0 vs 1.0) uses the full magnitude."""
        sp, li = dominance_shift(
            0.0,
            1.0,
            base_magnitude=0.03,
            multiplier=1.0,
            min_gap_threshold=0.05,
        )
        expected = 0.03 * 1.0 * 1.0
        assert li == pytest.approx(expected)
        assert sp == pytest.approx(-expected)
