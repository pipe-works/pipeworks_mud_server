"""Immutable result types for the axis resolution engine.

These frozen dataclasses represent the inputs and outputs of a single
mechanical resolution step — the permanent record of what happened when
two characters interacted.  They flow between the resolver functions,
the engine, and the JSONL ledger.

Design note: all score values stored here reflect the **post-clamping**
state (i.e. clamped to [0.0, 1.0]).  The engine clamps before writing;
these types never carry out-of-range floats.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AxisDelta:
    """The result of a resolver function for one axis and one entity.

    ``new_score`` and ``delta`` reflect the actual changes applied to the
    database after clamping, not the raw resolver output.  A character
    whose health is already at ``0.0`` would show ``delta = 0.0`` here
    even though the resolver returned ``-0.01``.

    Attributes:
        axis_name:  Name of the axis that was (potentially) mutated,
                    e.g. ``"demeanor"`` or ``"health"``.
        old_score:  Score read from the database before this resolution.
                    Always in [0.0, 1.0] for valid DB rows.
        new_score:  Score written to the database after clamping.
                    Always in [0.0, 1.0].
        delta:      Actual applied change = ``new_score - old_score``.
                    May be smaller in magnitude than the resolver's raw
                    delta if clamping was needed (e.g. health floor at
                    ``0.0``).
    """

    axis_name: str
    old_score: float
    new_score: float
    delta: float


@dataclass(frozen=True)
class EntityResolution:
    """The axis mutations produced for one entity during an interaction.

    Attributes:
        character_id:   Database primary key of the character.
        character_name: Display name at resolution time (informational;
                        not re-read after resolution completes).
        deltas:         Tuple of :class:`AxisDelta` objects — one per
                        axis whose resolver produced a non-zero actual
                        delta.  Axes with ``no_effect`` resolvers or
                        axes that were fully clamped to zero are omitted.
    """

    character_id: int
    character_name: str
    deltas: tuple[AxisDelta, ...]


@dataclass(frozen=True)
class AxisResolutionResult:
    """The complete result of one mechanical axis resolution.

    Returned by :meth:`~mud_server.axis.engine.AxisEngine.resolve_chat_interaction`
    after all ledger writes and database mutations are committed.

    The ``ipc_hash`` is the authoritative fingerprint of this interaction.
    It incorporates the world, channel, both character IDs, and the
    pre-interaction axis snapshot.  Passing it to the translation service
    enables deterministic rendering.

    Note on ``ipc_hash`` computation (deviation from plan):
        :func:`~pipeworks_ipc.compute_ipc_id` requires a
        ``system_prompt_hash`` string — a concept that has no meaning in a
        purely mechanical resolution (there is no LLM call).  Instead,
        :func:`~pipeworks_ipc.compute_payload_hash` is used directly on
        the resolution payload dict.  This is documented in
        :func:`~mud_server.axis.engine._compute_resolution_hash`.
        When the translation service uses the ``ipc_hash`` for deterministic
        Ollama seeding, it calls :func:`~pipeworks_ipc.compute_ipc_id` with
        this hash as the ``input_hash``, which is the intended design.

    Attributes:
        ipc_hash:             SHA-256 hex digest of the mechanical resolution
                              payload (``compute_payload_hash`` output).
        world_id:             World in which the interaction occurred.
        channel:              Chat channel (``"say"``, ``"yell"``,
                              ``"whisper"``).
        speaker:              :class:`EntityResolution` for the character
                              who spoke.
        listener:             :class:`EntityResolution` for the character
                              who received the message.
        axis_snapshot_before: Pre-interaction scores for the axes that
                              participate in the resolution (i.e. axes
                              with non-``no_effect`` resolvers).
                              Shape: ``{str(character_id): {axis_name: score}}``.
                              Stored in both the DB event ledger and the
                              JSONL ledger for audit and replay purposes.
    """

    ipc_hash: str
    world_id: str
    channel: str
    speaker: EntityResolution
    listener: EntityResolution
    axis_snapshot_before: dict[str, dict[str, float]]
