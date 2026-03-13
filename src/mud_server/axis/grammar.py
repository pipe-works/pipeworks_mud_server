"""Resolution grammar parser and typed rule dataclasses.

The resolution grammar is a deterministic rules payload for axis mutations.
In canonical runtime mode, this payload is resolved from activated DB policy
variants (``axis_bundle.content.resolution``) and parsed via
``parse_resolution_grammar_payload``.

Design notes:
1. All dataclasses are frozen (immutable after parse).
2. This module is payload-based and does not read policy files from disk.
3. Legacy file loading remains available only in
   ``mud_server.axis.legacy_file_loader`` for migration/testing workflows.
4. ``AxisRuleConfig.base_magnitude`` defaults to ``0.0`` for ``no_effect``
   resolvers; payloads may omit the field for those axes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Typed dataclasses
# ---------------------------------------------------------------------------

#: All resolver names accepted in the grammar.  Validated at load time.
VALID_RESOLVERS: frozenset[str] = frozenset({"dominance_shift", "shared_drain", "no_effect"})

#: Channel names required in every ``chat.channel_multipliers`` block.
REQUIRED_CHANNELS: frozenset[str] = frozenset({"say", "yell", "whisper"})


@dataclass(frozen=True)
class AxisRuleConfig:
    """Configuration for one axis within one interaction type.

    Attributes:
        resolver:        Name of the resolver function — one of
                         ``"dominance_shift"``, ``"shared_drain"``, or
                         ``"no_effect"``.  The axis engine looks up the
                         callable via the resolver registry in ``engine.py``.
        base_magnitude:  Scaling factor fed into the resolver (e.g. ``0.03``
                         for demeanor, ``0.01`` for health).  Defaults to
                         ``0.0`` for ``no_effect`` axes; the YAML may omit the
                         field entirely for those axes.
    """

    resolver: str
    base_magnitude: float = field(default=0.0)


@dataclass(frozen=True)
class ChatGrammar:
    """Resolution rules for the ``chat`` stimulus type.

    Attributes:
        channel_multipliers:  Per-channel scaling factors applied to every axis
                              delta.  Keys are channel names (``"say"``,
                              ``"yell"``, ``"whisper"``); values are positive
                              floats (e.g. ``1.5`` for yell, ``0.5`` for
                              whisper).
        min_gap_threshold:    Minimum absolute score difference below which
                              ``dominance_shift`` produces no delta.  Two
                              similarly-matched characters interact without
                              either gaining social ground.  ``shared_drain``
                              (health) ignores this threshold — social cost is
                              universal regardless of demeanor gap.
        axes:                 Mapping from axis name to its
                              :class:`AxisRuleConfig`.  Every axis registered
                              in the world should appear here (explicitly, even
                              as ``no_effect``), so the engine can assert full
                              coverage.
    """

    channel_multipliers: dict[str, float]
    min_gap_threshold: float
    axes: dict[str, AxisRuleConfig]


@dataclass(frozen=True)
class ResolutionGrammar:
    """Top-level container for all resolution rules in a world.

    Currently only the ``chat`` interaction type is defined.  Future stimulus
    types (``environmental``, ``physical``, ``economic``) will add new
    attributes here alongside their own YAML blocks.

    Attributes:
        version:  Schema version string read from the YAML file (e.g. ``"1.0"``).
                  Stored on ``chat.mechanical_resolution`` ledger events for
                  audit and replay traceability.
        chat:     Rules governing axis mutations produced by chat interactions.
    """

    version: str
    chat: ChatGrammar


def parse_resolution_grammar_payload(*, raw: object, source: str) -> ResolutionGrammar:
    """Parse and validate one resolution grammar mapping payload.

    Args:
        raw: Untrusted payload object expected to be a top-level mapping.
        source: Human-readable source label used in validation errors.

    Returns:
        A fully-constructed immutable :class:`ResolutionGrammar`.

    Raises:
        ValueError: On schema validation failure.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"{source} must be a YAML mapping at the top level.")

    version = raw.get("version")
    if not version:
        raise ValueError(f"{source}: missing required field 'version'.")
    version = str(version)

    interactions = raw.get("interactions")
    if not isinstance(interactions, dict):
        raise ValueError(f"{source}: missing required field 'interactions' (must be a mapping).")

    chat_raw = interactions.get("chat")
    if not isinstance(chat_raw, dict):
        raise ValueError(
            f"{source}: missing required field 'interactions.chat' (must be a mapping)."
        )

    chat = _parse_chat_grammar(chat_raw)
    return ResolutionGrammar(version=version, chat=chat)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_chat_grammar(raw: dict) -> ChatGrammar:
    """Parse the ``interactions.chat`` block into a :class:`ChatGrammar`.

    Args:
        raw: The parsed YAML dict for the ``interactions.chat`` sub-block.

    Returns:
        A :class:`ChatGrammar` instance.

    Raises:
        ValueError: On missing or invalid fields.
    """
    # ── Channel multipliers ──────────────────────────────────────────────────
    channel_multipliers_raw = raw.get("channel_multipliers")
    if not isinstance(channel_multipliers_raw, dict):
        raise ValueError(
            "resolution.yaml: interactions.chat.channel_multipliers must be a mapping."
        )
    missing_channels = REQUIRED_CHANNELS - set(channel_multipliers_raw)
    if missing_channels:
        raise ValueError(
            "resolution.yaml: interactions.chat.channel_multipliers missing channels: "
            f"{sorted(missing_channels)}"
        )
    channel_multipliers: dict[str, float] = {
        k: float(v) for k, v in channel_multipliers_raw.items()
    }

    # ── Min gap threshold ────────────────────────────────────────────────────
    min_gap_raw = raw.get("min_gap_threshold")
    if min_gap_raw is None:
        raise ValueError("resolution.yaml: interactions.chat.min_gap_threshold is required.")
    min_gap_threshold = float(min_gap_raw)

    # ── Axis rules ───────────────────────────────────────────────────────────
    axes_raw = raw.get("axes")
    if not isinstance(axes_raw, dict):
        raise ValueError("resolution.yaml: interactions.chat.axes must be a mapping.")

    axes: dict[str, AxisRuleConfig] = {}
    for axis_name, axis_config in axes_raw.items():
        if not isinstance(axis_config, dict):
            raise ValueError(
                f"resolution.yaml: interactions.chat.axes.{axis_name} must be a mapping."
            )
        resolver = axis_config.get("resolver")
        if not isinstance(resolver, str) or resolver not in VALID_RESOLVERS:
            raise ValueError(
                f"resolution.yaml: axes.{axis_name}.resolver must be one of "
                f"{sorted(VALID_RESOLVERS)}, got {resolver!r}."
            )
        base_magnitude = float(axis_config.get("base_magnitude", 0.0))
        axes[str(axis_name)] = AxisRuleConfig(resolver=resolver, base_magnitude=base_magnitude)

    return ChatGrammar(
        channel_multipliers=channel_multipliers,
        min_gap_threshold=min_gap_threshold,
        axes=axes,
    )
