"""Shared database constants for the DB package.

This module centralizes constants that are consumed by multiple DB submodules.
Keeping them in one location prevents accidental divergence when schema,
runtime queries, and tests evolve independently.
"""

from __future__ import annotations

# Default world id used by migration-era callers that still rely on an implicit
# world context. This remains available for transition safety while 0.3.10
# removes implicit world fallbacks at the API/repository boundary.
DEFAULT_WORLD_ID = "pipeworks_web"

# Neutral axis score used when no explicit axis value exists yet.
DEFAULT_AXIS_SCORE = 0.5
