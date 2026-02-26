"""Character profile builder for the OOC→IC translation layer.

``CharacterProfileBuilder`` is responsible for building the flat context
dictionary that is injected into the system prompt template.  It fetches
axis scores from the database and resolves them to their human-readable
labels.

World scoping
-------------
All DB lookups use *both* ``character_name`` and ``world_id``.  This is
non-negotiable: two characters in different worlds may share the same
name, and a name-only lookup would silently return the wrong character.
Any attempt to call this builder without a concrete ``world_id`` will
raise a ``ValueError`` at construction time.

Axis sourcing
-------------
The builder calls ``database.get_character_by_name_in_world`` to resolve
the character name to a ``character_id``, then calls
``database.get_character_axis_state(character_id)`` which returns both
axis scores and their resolved threshold labels (e.g. score ``0.87``
on the ``demeanor`` axis → label ``"proud"``).

Active axes filtering
---------------------
Only axes listed in ``active_axes`` are included in the returned profile
dict.  If a character has no score for an active axis yet (e.g. the
world just gained a new axis and old characters haven't been seeded),
the builder defaults to ``label="unknown"`` and ``score=0.0`` rather
than omitting the key, so the prompt template never contains an
unfilled placeholder.
"""

from __future__ import annotations

import logging
from typing import Any

from mud_server.db import facade as database

logger = logging.getLogger(__name__)


class CharacterProfileBuilder:
    """Builds a character profile dict suitable for system prompt rendering.

    Attributes:
        _world_id:     World that this builder is scoped to.
        _active_axes:  Axis names to include in the profile.  An empty list
                       means "all axes present for this character".
    """

    def __init__(self, world_id: str, active_axes: list[str]) -> None:
        """Initialise the builder.

        Args:
            world_id:    World the builder is scoped to.  Required; raises
                         ``ValueError`` if empty so that silent world-scope
                         omissions are caught at construction rather than
                         producing wrong DB queries.
            active_axes: Axis names to include in the profile.

        Raises:
            ValueError: If ``world_id`` is empty or blank.
        """
        if not world_id or not world_id.strip():
            raise ValueError(
                "CharacterProfileBuilder requires an explicit world_id.  "
                "Silent world-scope omissions corrupt multi-world experiments."
            )
        self._world_id = world_id
        self._active_axes = active_axes

    def build(self, character_name: str) -> dict[str, Any] | None:
        """Build a profile dict for the given character in this world.

        The returned dict contains flat ``{axis_name}_label`` and
        ``{axis_name}_score`` keys for every axis in ``active_axes``, plus
        a ``character_name`` key.  These map directly to the ``{{key}}``
        placeholders in the world's ``ic_prompt.txt`` template.

        Returns ``None`` in three situations (all logged at WARNING):
        - The character is not found in this world.
        - The character has no axis state at all.
        - An unexpected DB error occurs.

        In all ``None`` cases the caller (``TranslationService``) treats
        the result as an unresolvable fallback condition and returns ``None``
        from ``translate()``, causing the engine to use the original OOC
        message instead.

        Args:
            character_name: Name of the character to build a profile for.

        Returns:
            Flat profile dict on success, ``None`` on failure.
        """
        # ── Step 1: Resolve character_name → character_id within this world ──
        #
        # We MUST use the world-scoped lookup.  ``get_character_by_name`` (no
        # world filter) is not safe here because two worlds can have characters
        # with identical names.
        character_row = database.get_character_by_name_in_world(character_name, self._world_id)
        if character_row is None:
            logger.warning(
                "CharacterProfileBuilder: character %r not found in world %r",
                character_name,
                self._world_id,
            )
            return None

        character_id: int = int(character_row["id"])

        # ── Step 2: Fetch axis state (scores + resolved threshold labels) ─────
        axis_state = database.get_character_axis_state(character_id)
        if axis_state is None:
            logger.warning(
                "CharacterProfileBuilder: no axis state for character_id=%d "
                "(character=%r, world=%r)",
                character_id,
                character_name,
                self._world_id,
            )
            return None

        # ── Step 3: Build the flat profile dict ──────────────────────────────
        #
        # Index the axes list by name for O(1) lookups.
        axes_by_name: dict[str, dict] = {
            entry["axis_name"]: entry for entry in axis_state.get("axes", [])
        }

        # Determine which axes to expose.  An empty active_axes list means
        # "all axes that exist for this character".
        axes_to_include = self._active_axes if self._active_axes else list(axes_by_name.keys())

        profile: dict[str, Any] = {"character_name": character_name}

        for axis_name in axes_to_include:
            entry = axes_by_name.get(axis_name)
            if entry:
                profile[f"{axis_name}_label"] = entry.get("axis_label") or "unknown"
                profile[f"{axis_name}_score"] = float(entry.get("axis_score", 0.0))
            else:
                # Axis is configured as active but the character has no score yet
                # (e.g. newly added axis, old character).  Default to safe values
                # so the prompt template does not contain unfilled placeholders.
                logger.debug(
                    "CharacterProfileBuilder: axis %r has no score for character %r; "
                    "defaulting to unknown/0.0",
                    axis_name,
                    character_name,
                )
                profile[f"{axis_name}_label"] = "unknown"
                profile[f"{axis_name}_score"] = 0.0

        return profile
