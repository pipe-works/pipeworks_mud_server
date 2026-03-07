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
from types import SimpleNamespace
from typing import Any, cast

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


@pytest.mark.unit
def test_generate_condition_axis_raises_when_upstream_has_no_numeric_axes(
    monkeypatch, tmp_path: Path
):
    """Service should reject upstream payloads that normalize to an empty axis map."""
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
        condition_axis_service,
        "_fetch_entity_state_from_upstream",
        lambda **_: ({"axes": {"demeanor": {"label": "timid"}}}, {}),
    )

    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service.generate_condition_axis(
            world_id="pipeworks_web",
            world_root=tmp_path,
            seed=9,
            inputs=_base_inputs(),
            strict_inputs=True,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "CONDITION_AXIS_UPSTREAM_GENERATION_FAILED"


@pytest.mark.unit
def test_resolve_seed_rejects_non_integer() -> None:
    """Seed validation should reject non-integer values with a 422 contract."""
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._resolve_seed(cast(Any, "abc"))

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "CONDITION_AXIS_VALIDATION_ERROR"


@pytest.mark.unit
def test_resolve_seed_rejects_out_of_range_integer() -> None:
    """Seed validation should reject values outside canonical bounds."""
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._resolve_seed(0)

    assert exc_info.value.status_code == 422
    assert "between" in exc_info.value.detail


@pytest.mark.unit
def test_resolve_policy_context_prefers_manifest_when_available(monkeypatch, tmp_path: Path):
    """Manifest-first resolution should return manifest bundle metadata."""
    world_root = tmp_path / "pipeworks_web"
    policies = world_root / "policies"
    policies.mkdir(parents=True)
    (policies / "manifest.yaml").write_text("manifest: true\n", encoding="utf-8")

    class _FakeLoader:
        def __init__(self, *, worlds_root: Path) -> None:
            self.worlds_root = worlds_root

        def load_from_world_root(self, *, world_id: str, world_root: Path):
            _ = world_id, world_root
            return (
                {
                    "manifest": {"policy_bundle": {"id": "bundle-1"}},
                    "axis": {
                        "axes": {"version": "3", "axes": {"demeanor": {}}},
                        "thresholds": {"version": "3"},
                        "resolution": {"version": "3"},
                    },
                },
                SimpleNamespace(
                    bundle_id="bundle-1",
                    bundle_version="3",
                    required_runtime_inputs=["entity.species", "entity.axes"],
                ),
            )

    monkeypatch.setattr(condition_axis_service, "PolicyManifestLoader", _FakeLoader)

    ctx = condition_axis_service._resolve_policy_context(
        world_id="pipeworks_web",
        world_root=world_root,
        bundle_id=None,
    )

    assert ctx.bundle_id == "bundle-1"
    assert ctx.bundle_version == "3"
    assert ctx.policy_hash is not None
    # Service always enforces species+gender even if manifest does not include gender.
    assert "entity.species" in ctx.required_runtime_inputs
    assert "entity.identity.gender" in ctx.required_runtime_inputs
    # Non-axis required inputs are filtered out for this endpoint.
    assert "entity.axes" not in ctx.required_runtime_inputs


@pytest.mark.unit
def test_resolve_policy_context_rejects_unknown_manifest_bundle(monkeypatch, tmp_path: Path):
    """Manifest path should return 404 when requested bundle id is unavailable."""
    world_root = tmp_path / "pipeworks_web"
    policies = world_root / "policies"
    policies.mkdir(parents=True)
    (policies / "manifest.yaml").write_text("manifest: true\n", encoding="utf-8")

    class _FakeLoader:
        def __init__(self, *, worlds_root: Path) -> None:
            self.worlds_root = worlds_root

        def load_from_world_root(self, *, world_id: str, world_root: Path):
            _ = world_id, world_root
            return (
                {
                    "manifest": {},
                    "axis": {
                        "axes": {"axes": {"demeanor": {}}},
                        "thresholds": {},
                        "resolution": {},
                    },
                },
                SimpleNamespace(
                    bundle_id="bundle-a", bundle_version="1", required_runtime_inputs=[]
                ),
            )

    monkeypatch.setattr(condition_axis_service, "PolicyManifestLoader", _FakeLoader)

    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._resolve_policy_context(
            world_id="pipeworks_web",
            world_root=world_root,
            bundle_id="bundle-b",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "CONDITION_AXIS_BUNDLE_NOT_FOUND"


@pytest.mark.unit
def test_resolve_policy_context_fallback_requires_axes_file(tmp_path: Path):
    """Fallback mode should return unsupported when canonical axes are unavailable."""
    world_root = tmp_path / "pipeworks_web"
    (world_root / "policies").mkdir(parents=True)

    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._resolve_policy_context(
            world_id="pipeworks_web",
            world_root=world_root,
            bundle_id=None,
        )

    assert exc_info.value.status_code == 501
    assert exc_info.value.code == "CONDITION_AXIS_UPSTREAM_UNSUPPORTED"


@pytest.mark.unit
def test_resolve_policy_context_fallback_rejects_unknown_bundle(tmp_path: Path):
    """Fallback mode should reject non-default bundle overrides."""
    world_root = tmp_path / "pipeworks_web"
    policies = world_root / "policies"
    policies.mkdir(parents=True)
    (policies / "axes.yaml").write_text("version: 1\naxes:\n  demeanor: {}\n", encoding="utf-8")

    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._resolve_policy_context(
            world_id="pipeworks_web",
            world_root=world_root,
            bundle_id="another_bundle",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "CONDITION_AXIS_BUNDLE_NOT_FOUND"


@pytest.mark.unit
def test_resolve_policy_context_fallback_builds_default_context(tmp_path: Path):
    """Fallback mode should synthesize default bundle metadata when manifest is absent."""
    world_root = tmp_path / "pipeworks_web"
    policies = world_root / "policies"
    policies.mkdir(parents=True)
    (policies / "axes.yaml").write_text("axes:\n  demeanor: {}\n", encoding="utf-8")

    ctx = condition_axis_service._resolve_policy_context(
        world_id="pipeworks_web",
        world_root=world_root,
        bundle_id=None,
    )

    assert ctx.bundle_id == "pipeworks_web_default"
    # With no explicit version in fallback files, service should default to version "1".
    assert ctx.bundle_version == "1"
    assert isinstance(ctx.policy_hash, str) and ctx.policy_hash
    assert ctx.required_runtime_inputs == {"entity.identity.gender", "entity.species"}


@pytest.mark.unit
def test_read_yaml_returns_empty_for_invalid_yaml_mapping(tmp_path: Path):
    """YAML helper should return empty dict for non-mapping or parse failures."""
    file_path = tmp_path / "payload.yaml"
    file_path.write_text("- list\n- item\n", encoding="utf-8")
    assert condition_axis_service._read_yaml(file_path) == {}

    file_path.write_text("invalid: [\n", encoding="utf-8")
    assert condition_axis_service._read_yaml(file_path) == {}


@pytest.mark.unit
def test_validate_runtime_inputs_rejects_non_mapping_inputs() -> None:
    """Strict validation should reject requests where inputs is not a mapping."""
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._validate_runtime_inputs(
            inputs=cast(Any, None),
            required_runtime_inputs={"entity.identity.gender", "entity.species"},
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "CONDITION_AXIS_VALIDATION_ERROR"


@pytest.mark.unit
def test_validate_runtime_inputs_rejects_unknown_top_level_key() -> None:
    """Strict validation should reject unknown keys on inputs payload."""
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._validate_runtime_inputs(
            inputs={"entity": {}, "extra": 1},
            required_runtime_inputs={"entity.identity.gender", "entity.species"},
        )
    assert exc_info.value.status_code == 422


@pytest.mark.unit
def test_validate_runtime_inputs_rejects_non_dict_entity() -> None:
    """Strict validation should reject non-mapping entity payloads."""
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._validate_runtime_inputs(
            inputs={"entity": "bad"},
            required_runtime_inputs={"entity.identity.gender", "entity.species"},
        )
    assert exc_info.value.status_code == 422


@pytest.mark.unit
def test_validate_runtime_inputs_rejects_unknown_entity_and_identity_keys() -> None:
    """Strict validation should reject unknown entity/identity keys."""
    with pytest.raises(condition_axis_service.ConditionAxisServiceError):
        condition_axis_service._validate_runtime_inputs(
            inputs={
                "entity": {"identity": {"gender": "male"}, "species": "human", "unknown_entity": 1}
            },
            required_runtime_inputs={"entity.identity.gender", "entity.species"},
        )

    with pytest.raises(condition_axis_service.ConditionAxisServiceError):
        condition_axis_service._validate_runtime_inputs(
            inputs={
                "entity": {
                    "identity": {"gender": "male", "unknown_identity": 1},
                    "species": "human",
                }
            },
            required_runtime_inputs={"entity.identity.gender", "entity.species"},
        )


@pytest.mark.unit
def test_validate_runtime_inputs_requires_axes_when_declared() -> None:
    """Strict validation should enforce entity.axes when policy requires it."""
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._validate_runtime_inputs(
            inputs={"entity": {"identity": {"gender": "male"}, "species": "human"}},
            required_runtime_inputs={"entity.identity.gender", "entity.species", "entity.axes"},
        )
    assert "entity.axes" in exc_info.value.detail


@pytest.mark.unit
def test_validate_runtime_inputs_requires_non_blank_species_and_gender() -> None:
    """Strict validation should reject blank required string fields for species/gender."""
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info:
        condition_axis_service._validate_runtime_inputs(
            inputs={
                "entity": {
                    "identity": {"gender": ""},
                    "species": "   ",
                }
            },
            required_runtime_inputs={"entity.identity.gender", "entity.species"},
        )

    assert "entity.species" in exc_info.value.detail
    assert "entity.identity.gender" in exc_info.value.detail


@pytest.mark.unit
def test_fetch_entity_state_handles_disabled_and_missing_url(monkeypatch) -> None:
    """Upstream helper should map disabled/blank-url states to 501."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", False)
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info_disabled:
        condition_axis_service._fetch_entity_state_from_upstream(1)
    assert exc_info_disabled.value.status_code == 501

    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_base_url", "   ")
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_info_url:
        condition_axis_service._fetch_entity_state_from_upstream(1)
    assert exc_info_url.value.status_code == 501


@pytest.mark.unit
def test_fetch_entity_state_maps_http_statuses(monkeypatch) -> None:
    """Upstream helper should map unsupported/timeout/failure HTTP statuses."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        condition_axis_service.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_timeout_seconds", 3.0
    )

    monkeypatch.setattr(
        condition_axis_service.requests, "post", lambda *_a, **_k: _FakeResponse(status_code=404)
    )
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_unsupported:
        condition_axis_service._fetch_entity_state_from_upstream(1)
    assert exc_unsupported.value.status_code == 501

    monkeypatch.setattr(
        condition_axis_service.requests, "post", lambda *_a, **_k: _FakeResponse(status_code=408)
    )
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_timeout:
        condition_axis_service._fetch_entity_state_from_upstream(1)
    assert exc_timeout.value.status_code == 504

    monkeypatch.setattr(
        condition_axis_service.requests, "post", lambda *_a, **_k: _FakeResponse(status_code=500)
    )
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_failure:
        condition_axis_service._fetch_entity_state_from_upstream(1)
    assert exc_failure.value.status_code == 502


@pytest.mark.unit
def test_fetch_entity_state_handles_request_exceptions_and_bad_json(monkeypatch) -> None:
    """Upstream helper should map request/json/body failures to canonical 502."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        condition_axis_service.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_timeout_seconds", 3.0
    )

    monkeypatch.setattr(
        condition_axis_service.requests,
        "post",
        lambda *_a, **_k: (_ for _ in ()).throw(requests.exceptions.RequestException("network")),
    )
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_request:
        condition_axis_service._fetch_entity_state_from_upstream(1)
    assert exc_request.value.status_code == 502

    class _BadJsonResponse:
        status_code = 200
        headers: dict[str, str] = {}

        @staticmethod
        def json():
            raise ValueError("bad json")

    monkeypatch.setattr(
        condition_axis_service.requests, "post", lambda *_a, **_k: _BadJsonResponse()
    )
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_json:
        condition_axis_service._fetch_entity_state_from_upstream(1)
    assert exc_json.value.status_code == 502

    monkeypatch.setattr(
        condition_axis_service.requests, "post", lambda *_a, **_k: _FakeResponse(body=["bad"])
    )
    with pytest.raises(condition_axis_service.ConditionAxisServiceError) as exc_shape:
        condition_axis_service._fetch_entity_state_from_upstream(1)
    assert exc_shape.value.status_code == 502


@pytest.mark.unit
def test_fetch_entity_state_success_returns_payload_and_headers(monkeypatch) -> None:
    """Successful upstream responses should return body and headers unchanged."""
    monkeypatch.setattr(condition_axis_service.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        condition_axis_service.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org/",
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_timeout_seconds", 2.5
    )
    monkeypatch.setattr(
        condition_axis_service.config.integrations, "entity_state_include_prompts", True
    )

    response = _FakeResponse(
        body={"axes": {"demeanor": {"score": 0.5}}},
        headers={"x-generator-version": "v2"},
    )

    def post_mock(*_a, **_k):
        return response

    monkeypatch.setattr(condition_axis_service.requests, "post", post_mock)

    body, headers = condition_axis_service._fetch_entity_state_from_upstream(123)
    assert body["axes"]["demeanor"]["score"] == pytest.approx(0.5)
    assert headers["x-generator-version"] == "v2"


@pytest.mark.unit
def test_normalize_axes_and_extract_helpers_cover_fallback_paths() -> None:
    """Axis normalization and metadata extraction helpers should cover fallbacks."""
    normalized = condition_axis_service._normalize_axes(
        {
            "axes": {"demeanor": {"score": 0.2}, "wealth": 0.8},
            "character": {"health": 0.3},
            "occupation": {"wealth": 0.1, "legitimacy": {"score": 0.6}},
        }
    )
    assert normalized["demeanor"] == pytest.approx(0.2)
    assert normalized["health"] == pytest.approx(0.3)
    # Existing axes payload value should win over group fallback for same key.
    assert normalized["wealth"] == pytest.approx(0.8)
    assert normalized["legitimacy"] == pytest.approx(0.6)

    assert condition_axis_service._extract_score("bad") is None
    assert condition_axis_service._extract_score({"score": "bad"}) is None
    assert condition_axis_service._extract_score(1) == pytest.approx(1.0)
    assert condition_axis_service._extract_score({"score": 0.25}) == pytest.approx(0.25)

    assert condition_axis_service._extract_generator_version({"version": "1.2.3"}, {}) == "1.2.3"
    assert (
        condition_axis_service._extract_generator_version({}, {"X-Generator-Version": "9.9.9"})
        == "9.9.9"
    )
    assert condition_axis_service._extract_generator_version({}, {}) == "unknown"

    assert condition_axis_service._extract_generated_at(
        {"generated_at": "2026-03-08T00:00:00Z"}
    ) == ("2026-03-08T00:00:00Z")
    fallback = condition_axis_service._extract_generated_at({})
    assert fallback.endswith("Z")
