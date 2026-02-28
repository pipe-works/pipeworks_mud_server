"""Axis resolution engine.

:class:`AxisEngine` is the orchestrator that ties together the resolution
grammar, the resolver functions, the JSONL ledger, and the SQLite materialized
view.  One instance is created per :class:`~mud_server.core.world.World` at
startup and remains live for the server's lifetime.

Resolution sequence (``resolve_chat_interaction``):

1. Resolve character IDs from names (world-scoped, raises
   :exc:`CharacterNotFoundError` on miss).
2. Acquire per-character threading locks in ascending ID order (deadlock
   prevention).
3. Read current axis scores from the SQLite DB.
4. Compute ipc_hash via :func:`~pipeworks_ipc.compute_payload_hash` over the
   pre-interaction snapshot.
5. Compute axis deltas for every axis in the chat grammar.
6. Write ``chat.mechanical_resolution`` to the JSONL ledger — the authoritative
   act that makes the interaction permanent.
7. Clamp deltas to ``[0.0, 1.0]`` and apply to the DB via
   :func:`~mud_server.db.facade.apply_axis_event`.
8. Release locks.
9. Return :class:`~mud_server.axis.types.AxisResolutionResult`.

Locking strategy:
    Each character has a :class:`threading.Lock` stored in a dict keyed by
    ``character_id``.  Locks are always acquired in ascending ID order to
    prevent deadlocks when two interactions share a character.  The dict
    itself is protected by a separate ``_locks_mutex``.

Note on ipc_hash computation (deviation from plan):
    :func:`~pipeworks_ipc.compute_ipc_id` requires ``system_prompt_hash: str``
    — a concept that has no meaning in a purely mechanical resolution (no LLM
    call).  :func:`~pipeworks_ipc.compute_payload_hash` is used directly on
    the resolution payload dict instead.  When the translation service
    subsequently uses this ``ipc_hash`` for deterministic Ollama seeding it
    calls :func:`~pipeworks_ipc.compute_ipc_id` with this hash as
    ``input_hash``, which is the intended design.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from pipeworks_ipc import compute_payload_hash

from mud_server.axis.grammar import ResolutionGrammar
from mud_server.axis.resolvers import dominance_shift, no_effect, shared_drain
from mud_server.axis.types import AxisDelta, AxisResolutionResult, EntityResolution
from mud_server.db import facade as database
from mud_server.db.constants import DEFAULT_AXIS_SCORE
from mud_server.ledger import append_event as _ledger_append

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolver registry
# ---------------------------------------------------------------------------

#: Maps YAML resolver names → resolver callables.  New resolver algorithms
#: are registered here; the grammar YAML refers to them by name.
_RESOLVER_REGISTRY: dict[str, Callable] = {
    "dominance_shift": dominance_shift,
    "shared_drain": shared_drain,
    "no_effect": no_effect,
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CharacterNotFoundError(Exception):
    """Raised when a character name cannot be resolved within a world.

    Attributes:
        character_name: The name that could not be resolved.
        world_id:       The world in which the lookup was attempted.
    """

    def __init__(self, character_name: str, world_id: str) -> None:
        self.character_name = character_name
        self.world_id = world_id
        super().__init__(f"Character {character_name!r} not found in world {world_id!r}.")


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AxisEngine:
    """General-purpose resolver registry for axis mutations.

    Instantiated once per :class:`~mud_server.core.world.World` (same
    lifecycle as the translation service).  The chat resolver is the first
    concrete implementation; future stimulus types (environmental, physical,
    economic) will add new ``resolve_*`` methods following the same pattern.

    Args:
        world_id: The world this engine is scoped to.  Used when reading and
                  writing the JSONL ledger and the DB.
        grammar:  The parsed :class:`~mud_server.axis.grammar.ResolutionGrammar`
                  for this world.  Immutable for the engine's lifetime.
    """

    def __init__(self, *, world_id: str, grammar: ResolutionGrammar) -> None:
        self._world_id = world_id
        self._grammar = grammar
        # Per-character threading.Lock pool.  Protects the read-compute-write
        # cycle in resolve_chat_interaction against concurrent interactions.
        self._locks: dict[int, threading.Lock] = {}
        self._locks_mutex = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_chat_interaction(
        self,
        *,
        speaker_name: str,
        listener_name: str,
        channel: str,
        world_id: str,
    ) -> AxisResolutionResult:
        """Resolve a chat interaction between two characters.

        This is the primary entry point.  All ten steps of the resolution
        sequence (see module docstring) are executed here atomically under
        per-character locks.

        Args:
            speaker_name:  Display name of the character who sent the message.
            listener_name: Display name of the character who received it.
            channel:       Chat channel — ``"say"``, ``"yell"``, or
                           ``"whisper"``.  Governs the channel multiplier
                           applied to every axis delta.
            world_id:      World in which the interaction occurs.  Must match
                           ``self._world_id`` (passed explicitly to make the
                           call site readable).

        Returns:
            :class:`~mud_server.axis.types.AxisResolutionResult` containing
            the ipc_hash, per-character deltas (only axes with non-zero actual
            change), and the pre-interaction axis snapshot.

        Raises:
            CharacterNotFoundError: If either *speaker_name* or *listener_name*
                                    is not registered in *world_id*.
        """
        # 1. Resolve character IDs (raises CharacterNotFoundError on miss)
        speaker_id, listener_id = self._resolve_ids(speaker_name, listener_name, world_id)

        # 2. Acquire per-character locks in ascending ID order
        lock_order = sorted([speaker_id, listener_id])
        locks = [self._get_lock(cid) for cid in lock_order]
        for lock in locks:
            lock.acquire()

        try:
            return self._run_resolution(
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                listener_id=listener_id,
                listener_name=listener_name,
                channel=channel,
                world_id=world_id,
            )
        finally:
            # Release in reverse-acquisition order (conventional RAII pattern)
            for lock in reversed(locks):
                lock.release()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_lock(self, character_id: int) -> threading.Lock:
        """Return the per-character lock, creating it on first use."""
        with self._locks_mutex:
            if character_id not in self._locks:
                self._locks[character_id] = threading.Lock()
            return self._locks[character_id]

    def _resolve_ids(
        self,
        speaker_name: str,
        listener_name: str,
        world_id: str,
    ) -> tuple[int, int]:
        """Look up character IDs from names; raise on miss."""
        speaker_char = database.get_character_by_name_in_world(speaker_name, world_id)
        if speaker_char is None:
            raise CharacterNotFoundError(speaker_name, world_id)

        listener_char = database.get_character_by_name_in_world(listener_name, world_id)
        if listener_char is None:
            raise CharacterNotFoundError(listener_name, world_id)

        return int(speaker_char["id"]), int(listener_char["id"])

    def _read_scores(self, character_id: int) -> dict[str, float]:
        """Read current axis scores for one character from the DB.

        Returns:
            Mapping of ``axis_name → score``.  Falls back to
            :data:`~mud_server.db.constants.DEFAULT_AXIS_SCORE` for axes with
            no score row (character not yet seeded).
        """
        state = database.get_character_axis_state(character_id)
        if state is None:
            return {}
        return {a["axis_name"]: float(a["axis_score"]) for a in (state.get("axes") or [])}

    def _run_resolution(
        self,
        *,
        speaker_id: int,
        speaker_name: str,
        listener_id: int,
        listener_name: str,
        channel: str,
        world_id: str,
    ) -> AxisResolutionResult:
        """Inner resolution logic executed under both character locks.

        Separated from :meth:`resolve_chat_interaction` so that the locking
        boilerplate stays clean and this method can be tested independently.
        """
        # 3. Read current axis scores
        speaker_scores = self._read_scores(speaker_id)
        listener_scores = self._read_scores(listener_id)

        chat_grammar = self._grammar.chat
        multiplier = chat_grammar.channel_multipliers.get(channel, 1.0)

        # Determine which axes have non-no_effect resolvers (used for snapshot
        # scoping — we only include active axes in axis_snapshot_before)
        active_axis_names = [
            name for name, rule in chat_grammar.axes.items() if rule.resolver != "no_effect"
        ]

        # 4. Build axis_snapshot_before (scoped to active axes only)
        axis_snapshot_before: dict[str, dict[str, float]] = {
            str(speaker_id): {
                name: speaker_scores.get(name, DEFAULT_AXIS_SCORE) for name in active_axis_names
            },
            str(listener_id): {
                name: listener_scores.get(name, DEFAULT_AXIS_SCORE) for name in active_axis_names
            },
        }

        # 5. Compute ipc_hash from pre-interaction state
        ipc_hash = _compute_resolution_hash(
            world_id=world_id,
            speaker_id=speaker_id,
            listener_id=listener_id,
            channel=channel,
            axis_snapshot_before=axis_snapshot_before,
            grammar_version=self._grammar.version,
        )

        # 6. Compute axis deltas for every axis in the grammar
        speaker_axis_deltas: list[AxisDelta] = []
        listener_axis_deltas: list[AxisDelta] = []
        speaker_actual_deltas: dict[str, float] = {}
        listener_actual_deltas: dict[str, float] = {}

        for axis_name, rule in chat_grammar.axes.items():
            sp_old = speaker_scores.get(axis_name, DEFAULT_AXIS_SCORE)
            li_old = listener_scores.get(axis_name, DEFAULT_AXIS_SCORE)

            sp_raw, li_raw = _call_resolver(
                resolver_name=rule.resolver,
                speaker_score=sp_old,
                listener_score=li_old,
                base_magnitude=rule.base_magnitude,
                multiplier=multiplier,
                min_gap_threshold=chat_grammar.min_gap_threshold,
            )

            # Clamp new scores to [0.0, 1.0]; compute actual (post-clamp) delta
            sp_new = max(0.0, min(1.0, sp_old + sp_raw))
            li_new = max(0.0, min(1.0, li_old + li_raw))
            sp_actual = sp_new - sp_old
            li_actual = li_new - li_old

            # Only record axes with a non-zero actual change
            if abs(sp_actual) > 1e-12:
                speaker_axis_deltas.append(
                    AxisDelta(
                        axis_name=axis_name,
                        old_score=sp_old,
                        new_score=sp_new,
                        delta=sp_actual,
                    )
                )
                speaker_actual_deltas[axis_name] = sp_actual

            if abs(li_actual) > 1e-12:
                listener_axis_deltas.append(
                    AxisDelta(
                        axis_name=axis_name,
                        old_score=li_old,
                        new_score=li_new,
                        delta=li_actual,
                    )
                )
                listener_actual_deltas[axis_name] = li_actual

        # 7. Write chat.mechanical_resolution to JSONL ledger (authoritative act)
        _write_ledger_event(
            world_id=world_id,
            ipc_hash=ipc_hash,
            channel=channel,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            listener_id=listener_id,
            listener_name=listener_name,
            speaker_deltas=speaker_axis_deltas,
            listener_deltas=listener_axis_deltas,
            axis_snapshot_before=axis_snapshot_before,
            grammar_version=self._grammar.version,
        )

        # 8. Apply deltas to DB (materialization of the ledger event)
        if speaker_actual_deltas:
            _apply_to_db(
                world_id=world_id,
                character_id=speaker_id,
                actual_deltas=speaker_actual_deltas,
                ipc_hash=ipc_hash,
                channel=channel,
                peer_id=listener_id,
            )

        if listener_actual_deltas:
            _apply_to_db(
                world_id=world_id,
                character_id=listener_id,
                actual_deltas=listener_actual_deltas,
                ipc_hash=ipc_hash,
                channel=channel,
                peer_id=speaker_id,
            )

        # 9. Return result
        return AxisResolutionResult(
            ipc_hash=ipc_hash,
            world_id=world_id,
            channel=channel,
            speaker=EntityResolution(
                character_id=speaker_id,
                character_name=speaker_name,
                deltas=tuple(speaker_axis_deltas),
            ),
            listener=EntityResolution(
                character_id=listener_id,
                character_name=listener_name,
                deltas=tuple(listener_axis_deltas),
            ),
            axis_snapshot_before=axis_snapshot_before,
        )


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions, no instance state)
# ---------------------------------------------------------------------------


def _compute_resolution_hash(
    *,
    world_id: str,
    speaker_id: int,
    listener_id: int,
    channel: str,
    axis_snapshot_before: dict[str, dict[str, float]],
    grammar_version: str,
) -> str:
    """Compute a deterministic fingerprint for a mechanical resolution.

    Uses :func:`~pipeworks_ipc.compute_payload_hash` directly rather than
    :func:`~pipeworks_ipc.compute_ipc_id`, because ``compute_ipc_id`` requires
    ``system_prompt_hash: str`` — a concept that has no meaning in a purely
    mechanical resolution (no LLM call is involved).  This deviation is
    documented on :class:`~mud_server.axis.types.AxisResolutionResult`.

    Args:
        world_id:             World of the interaction.
        speaker_id:           DB primary key of the speaker.
        listener_id:          DB primary key of the listener.
        channel:              Chat channel name.
        axis_snapshot_before: Pre-interaction axis scores (active axes only).
        grammar_version:      Version string from the loaded grammar.

    Returns:
        SHA-256 hex digest of the canonical resolution payload dict.
    """
    payload: dict[str, Any] = {
        "world_id": world_id,
        "speaker_id": speaker_id,
        "listener_id": listener_id,
        "channel": channel,
        "axis_snapshot_before": axis_snapshot_before,
        "grammar_version": grammar_version,
    }
    result: str = compute_payload_hash(payload)
    return result


def _call_resolver(
    *,
    resolver_name: str,
    speaker_score: float,
    listener_score: float,
    base_magnitude: float,
    multiplier: float,
    min_gap_threshold: float,
) -> tuple[float, float]:
    """Dispatch to the appropriate resolver function.

    Unknown resolver names are treated as ``no_effect`` with a WARNING log,
    rather than raising.  Grammar validation at load time should prevent
    unknown names from reaching this point.

    Returns:
        ``(speaker_raw_delta, listener_raw_delta)`` — pre-clamping floats.
    """
    if resolver_name == "no_effect":
        return no_effect()
    if resolver_name == "dominance_shift":
        return dominance_shift(
            speaker_score,
            listener_score,
            base_magnitude=base_magnitude,
            multiplier=multiplier,
            min_gap_threshold=min_gap_threshold,
        )
    if resolver_name == "shared_drain":
        return shared_drain(
            base_magnitude=base_magnitude,
            multiplier=multiplier,
        )
    # Should not reach here if grammar was validated correctly
    logger.warning(
        "Unknown resolver %r encountered during resolution — treating as no_effect.",
        resolver_name,
    )
    return 0.0, 0.0


def _write_ledger_event(
    *,
    world_id: str,
    ipc_hash: str,
    channel: str,
    speaker_id: int,
    speaker_name: str,
    listener_id: int,
    listener_name: str,
    speaker_deltas: list[AxisDelta],
    listener_deltas: list[AxisDelta],
    axis_snapshot_before: dict[str, dict[str, float]],
    grammar_version: str,
) -> None:
    """Write a ``chat.mechanical_resolution`` event to the JSONL ledger.

    This is the authoritative act that makes the interaction permanent.  The
    DB mutation that follows is a materialization of this event.

    Ledger failures are logged as WARNING and do not abort the resolution — the
    DB mutation still proceeds so the in-memory game state stays consistent.
    This is an explicit PoC trade-off: the ledger record may be lost, but the
    player interaction completes.

    TODO(hardening): In production, a ledger failure should trigger an alert
    and possibly halt further ledger writes until the problem is resolved.
    """
    event_data: dict[str, Any] = {
        "channel": channel,
        "speaker": {
            "character_id": speaker_id,
            "character_name": speaker_name,
            "axis_deltas": {d.axis_name: d.delta for d in speaker_deltas},
        },
        "listener": {
            "character_id": listener_id,
            "character_name": listener_name,
            "axis_deltas": {d.axis_name: d.delta for d in listener_deltas},
        },
        "axis_snapshot_before": axis_snapshot_before,
        "grammar_version": grammar_version,
    }
    try:
        _ledger_append(
            world_id=world_id,
            event_type="chat.mechanical_resolution",
            data=event_data,
            ipc_hash=ipc_hash,
        )
    except Exception:
        logger.warning(
            "chat.mechanical_resolution ledger write failed for world %r — continuing.",
            world_id,
            exc_info=True,
        )


def _apply_to_db(
    *,
    world_id: str,
    character_id: int,
    actual_deltas: dict[str, float],
    ipc_hash: str,
    channel: str,
    peer_id: int,
) -> None:
    """Apply clamped axis deltas to the SQLite DB for one character.

    Errors are logged as ERROR (not WARNING) because a failed DB write means
    the materialized view is out of sync with the JSONL ledger — a more serious
    state than a missing ledger event.  The resolution continues regardless so
    that the other character's DB row can still be updated.

    Args:
        world_id:       World to apply the event in.
        character_id:   Character whose scores are being mutated.
        actual_deltas:  ``{axis_name: actual_delta}`` — post-clamp, non-zero only.
        ipc_hash:       The resolution's ipc_hash, stored as event metadata.
        channel:        Chat channel, stored as event metadata.
        peer_id:        The other character's ID, stored as event metadata.
    """
    try:
        database.apply_axis_event(
            world_id=world_id,
            character_id=character_id,
            event_type_name="chat.mechanical_resolution",
            event_type_description="Axis mutation produced by a chat interaction.",
            deltas=actual_deltas,
            metadata={
                "ipc_hash": ipc_hash,
                "channel": channel,
                "peer_id": str(peer_id),
            },
        )
    except Exception:
        logger.error(
            "DB axis mutation failed for character %d in world %r — "
            "materialized view may be out of sync with ledger.",
            character_id,
            world_id,
            exc_info=True,
        )
