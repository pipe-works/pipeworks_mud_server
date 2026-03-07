"""Unit tests for canonical condition-axis generation service.

Coverage focus:
- deterministic behavior for fixed seeds
- random-seed allocation when omitted
- provenance construction
- strict input validation
- upstream failure/timeout error mapping
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from mud_server.services import condition_axis_service


class _FakeResponse:
    """Simple fake ``requests.Response`` for service tests.

    Attributes:
        status_code: HTTP status value returned to the service.
        _body: JSON body returned by ``json()``.
        headers: Response headers used by provenance extraction tests.
    """

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: dict[str, Any] | list[Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self) -> dict[str, Any] | list[Any]:
        return self._body


def _base_inputs() -> dict[str, Any]:
    """Return minimal valid runtime inputs for strict validation paths."""
    return {
        "entity": {
            "identity": {"gender": "male"},
            "species": "human",
        }
    }


@pytest.mark.unit
def test_generate_condition_axis_is_deterministic_for_fixed_seed(monkeypatch, tmp_path: Path):
    """Identical fixed seeds should produce identical service output."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        condition_axis_service.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_timeout_seconds", 5.0
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_include_prompts", False
    )

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

    def _fake_post(_url: str, json: dict[str, Any], timeout: float) -> _FakeResponse:
        assert timeout == 5.0
        seed = int(json["seed"])
        # Deterministic upstream score derivation from request seed.
        score = (seed % 100) / 100.0
        return _FakeResponse(
            body={
                "axes": {
                    "demeanor": {"score": score},
                    "health": {"score": 0.77},
                },
                "generator_version": "v-test",
                "generated_at": "2026-03-07T12:00:00Z",
            }
        )

    monkeypatch.setattr(condition_axis_service.requests, "post", _fake_post)

    result_a = condition_axis_service.generate_condition_axis(
        world_id="pipeworks_web",
        world_root=tmp_path,
        seed=12345,
        inputs=_base_inputs(),
        strict_inputs=True,
    )
    result_b = condition_axis_service.generate_condition_axis(
        world_id="pipeworks_web",
        world_root=tmp_path,
        seed=12345,
        inputs=_base_inputs(),
        strict_inputs=True,
    )

    assert result_a.seed == 12345
    assert result_b.seed == 12345
    assert result_a.axes == result_b.axes
    assert result_a.axes["demeanor"] == pytest.approx(0.45)


@pytest.mark.unit
def test_generate_condition_axis_uses_random_seed_when_omitted(monkeypatch, tmp_path: Path):
    """Omitted seeds should be generated server-side and differ per call."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        condition_axis_service.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_timeout_seconds", 5.0
    )
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

    # ``randbelow`` returns raw offsets; service adds +1 to enforce non-zero seed.
    generated = iter([10, 20])
    monkeypatch.setattr(condition_axis_service, "randbelow", lambda _limit: next(generated))

    def _fake_post(_url: str, json: dict[str, Any], timeout: float) -> _FakeResponse:
        seed = int(json["seed"])
        return _FakeResponse(
            body={
                "axes": {"demeanor": {"score": float(seed) / 100.0}},
                "generator_version": "v-test",
            }
        )

    monkeypatch.setattr(condition_axis_service.requests, "post", _fake_post)

    result_a = condition_axis_service.generate_condition_axis(
        world_id="pipeworks_web",
        world_root=tmp_path,
        inputs=_base_inputs(),
        strict_inputs=True,
    )
    result_b = condition_axis_service.generate_condition_axis(
        world_id="pipeworks_web",
        world_root=tmp_path,
        inputs=_base_inputs(),
        strict_inputs=True,
    )

    assert result_a.seed == 11
    assert result_b.seed == 21
    assert result_a.seed != result_b.seed


@pytest.mark.unit
def test_generate_condition_axis_returns_canonical_provenance(monkeypatch, tmp_path: Path):
    """Service should emit stable provenance fields for canonical endpoint."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        condition_axis_service.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_timeout_seconds", 5.0
    )
    monkeypatch.setattr(
        condition_axis_service,
        "_resolve_policy_context",
        lambda **_: condition_axis_service.ConditionAxisPolicyContext(
            bundle_id="pipeworks_web_default",
            bundle_version="9",
            policy_hash="policy-hash",
            required_runtime_inputs={"entity.identity.gender", "entity.species"},
        ),
    )
    monkeypatch.setattr(
        condition_axis_service.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            body={
                "axes": {"health": {"score": 0.77}},
                "generator_version": "2.1.0",
                "generated_at": "2026-03-07T16:00:00Z",
            }
        ),
    )

    result = condition_axis_service.generate_condition_axis(
        world_id="pipeworks_web",
        world_root=tmp_path,
        seed=123,
        bundle_id="pipeworks_web_default",
        inputs=_base_inputs(),
        strict_inputs=True,
    )

    assert result.bundle_version == "9"
    assert result.policy_hash == "policy-hash"
    assert result.provenance.source == "mud_server_canonical"
    assert result.provenance.served_via == "/api/pipeline/condition-axis/generate"
    assert result.provenance.generator == "entity_state_generation"
    assert result.provenance.generator_version == "2.1.0"
    assert result.provenance.generated_at == "2026-03-07T16:00:00Z"


@pytest.mark.unit
def test_generate_condition_axis_rejects_invalid_inputs(monkeypatch, tmp_path: Path):
    """Strict mode should reject malformed runtime input payloads."""
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

    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service.generate_condition_axis(
            world_id="pipeworks_web",
            world_root=tmp_path,
            seed=123,
            inputs={"entity": {"species": "human"}},
            strict_inputs=True,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "CONDITION_AXIS_VALIDATION_ERROR"


@pytest.mark.unit
def test_generate_condition_axis_maps_timeout_to_504(monkeypatch, tmp_path: Path):
    """Upstream request timeouts should map to canonical 504 contract."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        condition_axis_service.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_timeout_seconds", 1.0
    )
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
    monkeypatch.setattr(
        condition_axis_service.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.exceptions.Timeout()),
    )

    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service.generate_condition_axis(
            world_id="pipeworks_web",
            world_root=tmp_path,
            seed=123,
            inputs=_base_inputs(),
            strict_inputs=True,
        )

    assert exc_info.value.status_code == 504
    assert exc_info.value.code == "CONDITION_AXIS_UPSTREAM_TIMEOUT"


@pytest.mark.unit
def test_generate_condition_axis_maps_upstream_failure_to_502(monkeypatch, tmp_path: Path):
    """Non-timeout upstream failures should map to canonical 502 contract."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        condition_axis_service.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_timeout_seconds", 5.0
    )
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
    monkeypatch.setattr(
        condition_axis_service.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(status_code=503, body={"detail": "unavailable"}),
    )

    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service.generate_condition_axis(
            world_id="pipeworks_web",
            world_root=tmp_path,
            seed=123,
            inputs=_base_inputs(),
            strict_inputs=True,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "CONDITION_AXIS_UPSTREAM_GENERATION_FAILED"
