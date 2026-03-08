"""Compatibility tests for mud-server <-> upstream condition-axis metadata contract.

Coverage focus:
- upstream metadata shape permutations (payload/header fallbacks)
- canonical provenance metadata stability in service responses
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mud_server.services import condition_axis_service


class _CompatResponse:
    """Minimal response double for upstream compatibility matrix tests."""

    def __init__(self, *, body: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        self.status_code = 200
        self._body = body
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._body


def _base_inputs() -> dict[str, Any]:
    """Return minimal valid runtime inputs for strict validation paths."""
    return {
        "entity": {
            "identity": {"gender": "male"},
            "species": "human",
        }
    }


def _configure_policy_context(monkeypatch) -> None:
    """Patch policy resolution so tests focus on upstream metadata contract behavior."""
    monkeypatch.setattr(
        condition_axis_service,
        "_resolve_policy_context",
        lambda **_: condition_axis_service.ConditionAxisPolicyContext(
            bundle_id="pipeworks_web_default",
            bundle_version="1",
            policy_hash="policy-hash",
            required_runtime_inputs={"entity.identity.gender", "entity.species"},
        ),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("payload", "headers", "expected_version", "expected_capabilities"),
    [
        (
            {
                "axes": {"demeanor": {"score": 0.5}},
                "generator_version": "payload-v2",
                "generator_capabilities": ["axes_v2", "deterministic_seed"],
            },
            {},
            "payload-v2",
            ("axes_v2", "deterministic_seed"),
        ),
        (
            {
                "axes": {"demeanor": {"score": 0.5}},
                "version": "payload-v1",
                "generator_capabilities": "axes_v1, deterministic_seed",
            },
            {"x-generator-capabilities": "deterministic_seed,legacy_axis_schema"},
            "payload-v1",
            ("axes_v1", "deterministic_seed", "legacy_axis_schema"),
        ),
        (
            {"axes": {"demeanor": {"score": 0.5}}},
            {
                "X-Generator-Version": "header-v9",
                "X-Generator-Capabilities": "axes_v3, deterministic_seed",
            },
            "header-v9",
            ("axes_v3", "deterministic_seed"),
        ),
        (
            {"axes": {"demeanor": {"score": 0.5}}},
            {},
            "unknown",
            (),
        ),
    ],
)
def test_generate_condition_axis_accepts_metadata_contract_variants(
    monkeypatch,
    tmp_path: Path,
    payload: dict[str, Any],
    headers: dict[str, str],
    expected_version: str,
    expected_capabilities: tuple[str, ...],
) -> None:
    """Service provenance should remain stable across upstream metadata variants."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        condition_axis_service.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org/",
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_timeout_seconds", 5.0
    )
    _configure_policy_context(monkeypatch)

    monkeypatch.setattr(
        condition_axis_service.requests,
        "post",
        lambda *_a, **_k: _CompatResponse(body=payload, headers=headers),
    )

    result = condition_axis_service.generate_condition_axis(
        world_id="pipeworks_web",
        world_root=tmp_path,
        seed=1234,
        inputs=_base_inputs(),
        strict_inputs=True,
    )

    assert result.provenance.generator_version == expected_version
    assert result.provenance.generator_capabilities == expected_capabilities
