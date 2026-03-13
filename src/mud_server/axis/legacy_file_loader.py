"""Legacy file-backed resolution grammar loader.

This module is intentionally outside the canonical runtime contract.

Use cases:
1. Migration/testing workflows that still validate YAML grammar fixtures.
2. Transitional tooling that reads ``policies/axis/resolution.yaml`` from disk.

Non-goals:
1. Runtime policy resolution for world startup. Canonical runtime reads
   activated DB policy payloads and parses them via
   ``mud_server.axis.grammar.parse_resolution_grammar_payload``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from mud_server.axis.grammar import ResolutionGrammar, parse_resolution_grammar_payload


def load_resolution_grammar(world_root: Path) -> ResolutionGrammar:
    """Load and validate a legacy file-backed resolution grammar payload.

    Args:
        world_root: World package root. The loader expects the grammar file at
            ``<world_root>/policies/axis/resolution.yaml``.

    Returns:
        Parsed immutable ``ResolutionGrammar``.

    Raises:
        FileNotFoundError: If the expected file path does not exist.
        ValueError: If YAML content is invalid for the grammar schema.
    """
    grammar_path = world_root / "policies" / "axis" / "resolution.yaml"
    if not grammar_path.exists():
        raise FileNotFoundError(f"Resolution grammar not found: {grammar_path}")

    with grammar_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    return parse_resolution_grammar_payload(
        raw=raw,
        source=str(grammar_path),
    )
