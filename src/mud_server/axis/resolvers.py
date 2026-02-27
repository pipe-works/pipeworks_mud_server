"""Axis resolver functions.

Each resolver computes raw (pre-clamping) axis deltas for both the speaker and
the listener during one mechanical resolution step.  The engine clamps final
scores to ``[0.0, 1.0]`` *after* calling the resolver — resolvers operate in
unbounded float arithmetic and must not clamp internally.

Resolver contract:
- Accept keyword-only arguments (except the positional score values for
  ``dominance_shift``).
- Return ``(speaker_delta, listener_delta)`` as a ``tuple[float, float]``.
- Be pure functions: no I/O, no shared state, no side effects.
- Never raise on valid float inputs.

The resolver registry in ``engine.py`` maps YAML resolver names → callables:

    _RESOLVER_REGISTRY: dict[str, Callable] = {
        "dominance_shift": dominance_shift,
        "shared_drain":    shared_drain,
        "no_effect":       no_effect,
    }
"""

from __future__ import annotations


def dominance_shift(
    speaker_score: float,
    listener_score: float,
    *,
    base_magnitude: float,
    multiplier: float,
    min_gap_threshold: float,
) -> tuple[float, float]:
    """Compute demeanor deltas from a dominance contest between two characters.

    The character with the higher score is the "winner" and gains a positive
    delta; the lower-scored character loses the same magnitude (symmetric
    transfer).

    Delta formula::

        gap       = abs(speaker_score - listener_score)
        magnitude = base_magnitude * multiplier * gap

    If ``gap < min_gap_threshold`` both deltas are zero — two similarly-matched
    characters interact without either gaining social ground.

    Note on ties (``speaker_score == listener_score``)
        A zero gap is always below threshold, so ``(0.0, 0.0)`` is returned.
        This is consistent: a true tie produces no dominance delta.

    Args:
        speaker_score:     Speaker's current score on this axis (0.0–1.0).
        listener_score:    Listener's current score on this axis (0.0–1.0).
        base_magnitude:    Scaling factor from the grammar (e.g. ``0.03``).
        multiplier:        Channel multiplier (e.g. ``1.5`` for yell,
                           ``0.5`` for whisper).
        min_gap_threshold: Minimum gap below which no delta is produced
                           (e.g. ``0.05``).

    Returns:
        ``(speaker_delta, listener_delta)`` — positive for the winner,
        negative for the loser, or ``(0.0, 0.0)`` when the gap is below
        threshold.
    """
    gap = abs(speaker_score - listener_score)
    if gap < min_gap_threshold:
        return 0.0, 0.0

    magnitude = base_magnitude * multiplier * gap
    if speaker_score > listener_score:
        # Speaker dominates
        return magnitude, -magnitude
    else:
        # Listener dominates (or exact tie beyond threshold — treated as
        # listener win to avoid a silent no-op when gap >= threshold)
        return -magnitude, magnitude


def shared_drain(
    *,
    base_magnitude: float,
    multiplier: float,
) -> tuple[float, float]:
    """Compute the universal health cost of a social interaction.

    Both the speaker and the listener lose the same amount of health regardless
    of the demeanor outcome.  Social interaction has a physical cost — the
    conversation happened whether or not either character dominated.

    This applies even when the demeanor gap is below ``min_gap_threshold``
    (i.e. health drains even when demeanor does not shift).

    Delta formula::

        drain = -(base_magnitude * multiplier)

    Args:
        base_magnitude: Scaling factor from the grammar (e.g. ``0.01``).
        multiplier:     Channel multiplier (e.g. ``1.5`` for yell,
                        ``0.5`` for whisper).

    Returns:
        ``(speaker_delta, listener_delta)`` — both are the same negative float.
    """
    drain = -(base_magnitude * multiplier)
    return drain, drain


def no_effect() -> tuple[float, float]:
    """Return ``(0.0, 0.0)`` — explicit no-op for axes not involved in this interaction.

    Axes are listed explicitly in the grammar with ``resolver: no_effect``
    rather than silently omitted so that the engine can assert complete axis
    coverage.  Future stimulus types that affect these axes will add their own
    YAML blocks (e.g. ``interactions.environmental.axes.wealth``) without
    modifying existing blocks.

    Returns:
        ``(0.0, 0.0)``
    """
    return 0.0, 0.0
