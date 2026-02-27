"""Unit tests for the ledger writer module.

Each test uses pytest's ``tmp_path`` fixture to redirect ledger writes to an
isolated temporary directory.  The module-level ``_LEDGER_ROOT`` variable in
``mud_server.ledger.writer`` is monkeypatched to this temporary directory so
that no test ever touches the real ``data/ledger/`` directory.

Test organisation
-----------------
- :class:`TestAppendEvent`     — happy path and argument validation for
                                  :func:`~mud_server.ledger.writer.append_event`.
- :class:`TestEnvelopeSchema`  — envelope field presence, types, and values.
- :class:`TestChecksum`        — checksum computation and tamper detection.
- :class:`TestVerifyWorldLedger` — all :func:`~mud_server.ledger.writer.verify_world_ledger`
                                    branches (ok, empty, corrupt).
- :class:`TestMultipleWorlds`  — file isolation between worlds.
- :class:`TestEdgeCases`       — null ipc_hash, meta passthrough, error paths.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import mud_server.ledger.writer as _writer
from mud_server.ledger import (
    LedgerVerifyResult,
    LedgerWriteError,
    append_event,
    verify_world_ledger,
)


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def ledger_tmp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all ledger writes to a temporary directory for test isolation.

    Monkeypatches ``mud_server.ledger.writer._LEDGER_ROOT`` to a fresh
    ``tmp_path / "ledger"`` directory.  The ``autouse=True`` flag applies
    this to every test in the module automatically.

    Returns:
        The temporary ledger root directory (``tmp_path / "ledger"``).
    """
    ledger_root = tmp_path / "ledger"
    monkeypatch.setattr(_writer, "_LEDGER_ROOT", ledger_root)
    return ledger_root


def _ledger_file(world_id: str, tmp_path: Path) -> Path:
    """Convenience helper — return the expected ledger path for ``world_id``."""
    return tmp_path / "ledger" / f"{world_id}.jsonl"


def _read_last_line(path: Path) -> dict:
    """Read and parse the last non-empty line of a JSONL file."""
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1])


def _all_lines(path: Path) -> list[dict]:
    """Read and parse all non-empty lines of a JSONL file."""
    return [
        json.loads(l)
        for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


# ── TestAppendEvent ───────────────────────────────────────────────────────────


class TestAppendEvent:
    """Tests for the happy path and basic argument validation of append_event."""

    def test_creates_ledger_file_when_absent(self, tmp_path: Path) -> None:
        """append_event creates the ledger file if it does not yet exist.

        The data/ledger/ directory and <world_id>.jsonl file must both be
        created automatically on the first write.
        """
        path = _ledger_file("test_world", tmp_path)
        assert not path.exists(), "Pre-condition: file must not exist before write."

        append_event("test_world", "chat.translation", data={})

        assert path.exists(), "Ledger file must be created after first append."

    def test_returns_non_empty_event_id(self, tmp_path: Path) -> None:
        """append_event returns a non-empty string event ID."""
        event_id = append_event("test_world", "chat.translation", data={})

        assert isinstance(event_id, str), "event_id must be a string."
        assert len(event_id) > 0, "event_id must not be empty."

    def test_returns_32_char_hex_event_id(self, tmp_path: Path) -> None:
        """append_event returns a 32-character lowercase hex string (UUID4 hex)."""
        event_id = append_event("test_world", "chat.translation", data={})

        assert len(event_id) == 32, f"Expected 32 chars, got {len(event_id)}."
        assert event_id == event_id.lower(), "event_id must be lowercase hex."
        # Verify it is valid hex (no ValueError on conversion).
        int(event_id, 16)

    def test_each_call_returns_unique_event_id(self, tmp_path: Path) -> None:
        """Successive calls return different event IDs."""
        ids = {append_event("test_world", "chat.translation", data={}) for _ in range(5)}
        assert len(ids) == 5, "Every append must produce a unique event_id."

    def test_appends_as_single_newline_terminated_line(self, tmp_path: Path) -> None:
        """Each append adds exactly one newline-terminated line to the file."""
        path = _ledger_file("test_world", tmp_path)

        for i in range(3):
            append_event("test_world", "chat.translation", data={"i": i})

        lines = [l for l in path.read_text().splitlines() if l.strip()]
        assert len(lines) == 3, f"Expected 3 lines, found {len(lines)}."

    def test_raises_value_error_on_empty_world_id(self, tmp_path: Path) -> None:
        """append_event raises ValueError when world_id is empty."""
        with pytest.raises(ValueError, match="world_id"):
            append_event("", "chat.translation", data={})

    def test_raises_value_error_on_blank_world_id(self, tmp_path: Path) -> None:
        """append_event raises ValueError when world_id is all whitespace."""
        with pytest.raises(ValueError, match="world_id"):
            append_event("   ", "chat.translation", data={})

    def test_raises_value_error_on_empty_event_type(self, tmp_path: Path) -> None:
        """append_event raises ValueError when event_type is empty."""
        with pytest.raises(ValueError, match="event_type"):
            append_event("test_world", "", data={})

    def test_raises_ledger_write_error_on_unwritable_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """append_event raises LedgerWriteError when the filesystem write fails.

        Simulated by pointing _LEDGER_ROOT at a path inside an existing file
        (so mkdir fails because a file blocks the directory creation).
        """
        # Create a plain file where the ledger directory should go.
        blocker = tmp_path / "ledger"
        blocker.write_text("not a directory")

        with pytest.raises(LedgerWriteError):
            append_event("test_world", "chat.translation", data={})


# ── TestEnvelopeSchema ────────────────────────────────────────────────────────


class TestEnvelopeSchema:
    """Tests for the envelope field presence, types, and fixed values."""

    @pytest.fixture
    def envelope(self, tmp_path: Path) -> dict:
        """Return the parsed envelope of a single appended event."""
        append_event(
            "test_world",
            "chat.translation",
            data={"status": "success"},
            ipc_hash=None,
            meta={"phase": "pre_axis_engine"},
        )
        return _read_last_line(_ledger_file("test_world", tmp_path))

    def test_envelope_contains_event_id(self, envelope: dict) -> None:
        """Envelope must contain a string 'event_id' field."""
        assert "event_id" in envelope
        assert isinstance(envelope["event_id"], str)

    def test_envelope_contains_timestamp(self, envelope: dict) -> None:
        """Envelope must contain a non-empty string 'timestamp' field."""
        assert "timestamp" in envelope
        assert isinstance(envelope["timestamp"], str)
        assert len(envelope["timestamp"]) > 0

    def test_envelope_contains_world_id(self, envelope: dict) -> None:
        """Envelope must record the world_id passed to append_event."""
        assert envelope["world_id"] == "test_world"

    def test_envelope_contains_event_type(self, envelope: dict) -> None:
        """Envelope must record the event_type passed to append_event."""
        assert envelope["event_type"] == "chat.translation"

    def test_envelope_schema_version_is_1_0(self, envelope: dict) -> None:
        """Envelope must contain schema_version '1.0'."""
        assert envelope["schema_version"] == "1.0"

    def test_envelope_ipc_hash_null_when_none(self, envelope: dict) -> None:
        """ipc_hash is stored as JSON null when None is passed."""
        assert envelope["ipc_hash"] is None

    def test_envelope_ipc_hash_stored_when_provided(self, tmp_path: Path) -> None:
        """ipc_hash is stored verbatim when a non-None value is passed."""
        fake_hash = "a" * 64
        append_event("test_world", "chat.translation", data={}, ipc_hash=fake_hash)
        env = _read_last_line(_ledger_file("test_world", tmp_path))
        assert env["ipc_hash"] == fake_hash

    def test_envelope_meta_stored_correctly(self, envelope: dict) -> None:
        """meta dict is stored verbatim in the envelope."""
        assert envelope["meta"] == {"phase": "pre_axis_engine"}

    def test_envelope_meta_defaults_to_empty_dict(self, tmp_path: Path) -> None:
        """When meta=None, the envelope stores an empty dict, not null."""
        append_event("test_world", "chat.translation", data={}, meta=None)
        env = _read_last_line(_ledger_file("test_world", tmp_path))
        assert env["meta"] == {}

    def test_envelope_data_round_trips(self, tmp_path: Path) -> None:
        """The data payload is stored and recovered without loss."""
        payload = {"status": "success", "ic_output": "The shadows suit you.", "score": 0.87}
        append_event("test_world", "chat.translation", data=payload)
        env = _read_last_line(_ledger_file("test_world", tmp_path))
        assert env["data"] == payload

    def test_envelope_contains_checksum_field(self, envelope: dict) -> None:
        """Envelope must contain a '_checksum' field."""
        assert "_checksum" in envelope

    def test_envelope_checksum_has_sha256_prefix(self, envelope: dict) -> None:
        """The '_checksum' value must start with 'sha256:'."""
        assert envelope["_checksum"].startswith("sha256:")

    def test_envelope_event_id_matches_returned_id(self, tmp_path: Path) -> None:
        """The event_id in the envelope must match what append_event returned."""
        returned_id = append_event("test_world", "chat.translation", data={})
        env = _read_last_line(_ledger_file("test_world", tmp_path))
        assert env["event_id"] == returned_id


# ── TestChecksum ──────────────────────────────────────────────────────────────


class TestChecksum:
    """Tests for checksum integrity — both computation and tamper detection."""

    def test_checksum_is_valid_sha256_hex(self, tmp_path: Path) -> None:
        """The checksum value (after the 'sha256:' prefix) must be 64 hex chars."""
        append_event("test_world", "chat.translation", data={})
        env = _read_last_line(_ledger_file("test_world", tmp_path))
        digest = env["_checksum"].removeprefix("sha256:")
        assert len(digest) == 64
        int(digest, 16)  # Must be valid hex — raises ValueError if not.

    def test_checksum_matches_computed_value(self, tmp_path: Path) -> None:
        """The stored checksum must match the SHA-256 of the envelope body.

        Replicates the verification logic: strip _checksum, serialise with
        sort_keys=True, compute SHA-256, compare.
        """
        append_event("test_world", "chat.translation", data={"x": 1})
        env = _read_last_line(_ledger_file("test_world", tmp_path))

        body = {k: v for k, v in env.items() if k != "_checksum"}
        canonical = json.dumps(body, ensure_ascii=False, sort_keys=True)
        expected = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        assert env["_checksum"] == expected

    def test_verify_detects_tampered_data_field(self, tmp_path: Path) -> None:
        """verify_world_ledger returns 'corrupt' when the data payload is modified.

        Simulates a partial write or in-place file edit that changes the
        payload without updating the checksum.
        """
        append_event("test_world", "chat.translation", data={"original": True})
        path = _ledger_file("test_world", tmp_path)

        # Read the line, modify the data field, write it back.
        env = _read_last_line(path)
        env["data"]["original"] = False  # Tamper: flip the boolean.
        tampered_line = json.dumps(env, ensure_ascii=False, sort_keys=True)
        path.write_text(tampered_line + "\n", encoding="utf-8")

        result = verify_world_ledger("test_world")
        assert result.status == "corrupt"
        assert "mismatch" in (result.error_detail or "").lower()

    def test_verify_detects_missing_checksum_field(self, tmp_path: Path) -> None:
        """verify_world_ledger returns 'corrupt' when _checksum is absent."""
        append_event("test_world", "chat.translation", data={})
        path = _ledger_file("test_world", tmp_path)

        env = _read_last_line(path)
        del env["_checksum"]  # Remove the checksum field entirely.
        path.write_text(json.dumps(env) + "\n", encoding="utf-8")

        result = verify_world_ledger("test_world")
        assert result.status == "corrupt"

    def test_checksum_stable_across_key_insertion_order(self) -> None:
        """_compute_checksum is stable regardless of dict key insertion order.

        Two dicts with the same content but different insertion order must
        produce identical checksums (due to sort_keys=True serialisation).
        """
        dict_a = {"b": 2, "a": 1, "c": 3}
        dict_b = {"a": 1, "c": 3, "b": 2}
        assert _writer._compute_checksum(dict_a) == _writer._compute_checksum(dict_b)


# ── TestVerifyWorldLedger ─────────────────────────────────────────────────────


class TestVerifyWorldLedger:
    """Tests for all branches of verify_world_ledger."""

    def test_returns_empty_when_file_absent(self) -> None:
        """Returns status='empty' when the ledger file does not exist."""
        result = verify_world_ledger("nonexistent_world")
        assert result.status == "empty"
        assert result.last_event_id is None
        assert result.error_detail is None

    def test_returns_empty_when_file_is_blank(self, tmp_path: Path) -> None:
        """Returns status='empty' when the ledger file exists but has no events."""
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir(parents=True)
        (ledger_dir / "empty_world.jsonl").write_text("\n\n\n", encoding="utf-8")

        result = verify_world_ledger("empty_world")
        assert result.status == "empty"
        assert result.last_event_id is None

    def test_returns_ok_for_valid_single_event(self, tmp_path: Path) -> None:
        """Returns status='ok' and the event_id after a single valid append."""
        returned_id = append_event("test_world", "chat.translation", data={})

        result = verify_world_ledger("test_world")
        assert result.status == "ok"
        assert result.last_event_id == returned_id
        assert result.error_detail is None

    def test_returns_ok_for_valid_multiple_events(self, tmp_path: Path) -> None:
        """Returns status='ok' referencing the last event after multiple appends."""
        for _ in range(5):
            last_id = append_event("test_world", "chat.translation", data={})

        result = verify_world_ledger("test_world")
        assert result.status == "ok"
        assert result.last_event_id == last_id

    def test_returns_corrupt_on_invalid_json_last_line(self, tmp_path: Path) -> None:
        """Returns status='corrupt' when the last line is not valid JSON.

        Simulates a crash mid-write that left a partial JSON line.
        """
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir(parents=True)
        (ledger_dir / "test_world.jsonl").write_text(
            '{"event_id": "abc"}\n{"truncated": true, "no_clos',
            encoding="utf-8",
        )

        result = verify_world_ledger("test_world")
        assert result.status == "corrupt"
        assert result.last_event_id is None
        assert result.error_detail is not None

    def test_returns_corrupt_on_checksum_mismatch(self, tmp_path: Path) -> None:
        """Returns status='corrupt' when _checksum does not match the body."""
        append_event("test_world", "chat.translation", data={})
        path = _ledger_file("test_world", tmp_path)

        env = _read_last_line(path)
        env["_checksum"] = "sha256:" + "0" * 64  # Wrong checksum.
        path.write_text(json.dumps(env) + "\n", encoding="utf-8")

        result = verify_world_ledger("test_world")
        assert result.status == "corrupt"

    def test_returns_corrupt_when_non_dict_json(self, tmp_path: Path) -> None:
        """Returns status='corrupt' when the last line is a JSON array, not object."""
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir(parents=True)
        (ledger_dir / "test_world.jsonl").write_text('[1, 2, 3]\n', encoding="utf-8")

        result = verify_world_ledger("test_world")
        assert result.status == "corrupt"

    def test_result_is_frozen_dataclass(self, tmp_path: Path) -> None:
        """LedgerVerifyResult is immutable (frozen=True dataclass)."""
        append_event("test_world", "chat.translation", data={})
        result = verify_world_ledger("test_world")

        with pytest.raises((AttributeError, TypeError)):
            result.status = "corrupt"  # type: ignore[misc]


# ── TestMultipleWorlds ────────────────────────────────────────────────────────


class TestMultipleWorlds:
    """Tests confirming that different world IDs use separate ledger files."""

    def test_separate_files_per_world(self, tmp_path: Path) -> None:
        """Events for different worlds are written to different files."""
        append_event("world_a", "chat.translation", data={"world": "a"})
        append_event("world_b", "chat.translation", data={"world": "b"})

        path_a = _ledger_file("world_a", tmp_path)
        path_b = _ledger_file("world_b", tmp_path)

        assert path_a.exists(), "world_a ledger must exist."
        assert path_b.exists(), "world_b ledger must exist."
        assert path_a != path_b, "Files must be at different paths."

    def test_world_a_events_not_in_world_b(self, tmp_path: Path) -> None:
        """An event appended to world_a does not appear in world_b's file."""
        append_event("world_a", "chat.translation", data={"marker": "a_only"})
        append_event("world_b", "chat.translation", data={"marker": "b_only"})

        b_content = _ledger_file("world_b", tmp_path).read_text()
        assert "a_only" not in b_content

    def test_verify_only_checks_target_world(self, tmp_path: Path) -> None:
        """verify_world_ledger is scoped to the specified world only."""
        append_event("world_a", "chat.translation", data={})
        # world_b has no ledger — should return empty, not world_a's state.
        result = verify_world_ledger("world_b")
        assert result.status == "empty"


# ── TestEdgeCases ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: null ipc_hash, complex data payloads, non-ASCII content."""

    def test_null_ipc_hash_is_valid(self, tmp_path: Path) -> None:
        """ipc_hash=None is a valid, expected value for pre-axis-engine events."""
        event_id = append_event(
            "test_world", "chat.translation", data={}, ipc_hash=None
        )
        env = _read_last_line(_ledger_file("test_world", tmp_path))
        assert env["ipc_hash"] is None
        assert env["event_id"] == event_id

    def test_meta_phase_pre_axis_engine_round_trips(self, tmp_path: Path) -> None:
        """The pre_axis_engine phase marker is stored and recoverable."""
        append_event(
            "test_world",
            "chat.translation",
            data={},
            ipc_hash=None,
            meta={"phase": "pre_axis_engine"},
        )
        env = _read_last_line(_ledger_file("test_world", tmp_path))
        assert env["meta"]["phase"] == "pre_axis_engine"

    def test_unicode_data_payload_round_trips(self, tmp_path: Path) -> None:
        """Non-ASCII characters in the data payload survive the write/read cycle."""
        payload = {"ic_output": "The lantern flickers. «Qu'est-ce que c'est?»", "emoji": "⚔️"}
        append_event("test_world", "chat.translation", data=payload)
        env = _read_last_line(_ledger_file("test_world", tmp_path))
        assert env["data"]["ic_output"] == payload["ic_output"]
        assert env["data"]["emoji"] == payload["emoji"]

    def test_nested_data_dict_round_trips(self, tmp_path: Path) -> None:
        """Deeply nested data payloads are preserved without flattening."""
        payload = {
            "speaker": {"character_id": 7, "axis_deltas": {"demeanor": 0.011}},
            "listener": {"character_id": 12, "axis_deltas": {"demeanor": -0.011}},
        }
        append_event("test_world", "chat.mechanical_resolution", data=payload)
        env = _read_last_line(_ledger_file("test_world", tmp_path))
        assert env["data"]["speaker"]["axis_deltas"]["demeanor"] == 0.011

    def test_many_appends_all_valid(self, tmp_path: Path) -> None:
        """Appending 50 events in sequence produces 50 valid parseable lines."""
        for i in range(50):
            append_event("test_world", "chat.translation", data={"i": i})

        lines = _all_lines(_ledger_file("test_world", tmp_path))
        assert len(lines) == 50
        # Every line must have a unique event_id.
        event_ids = {env["event_id"] for env in lines}
        assert len(event_ids) == 50

    def test_verify_ok_after_many_appends(self, tmp_path: Path) -> None:
        """verify_world_ledger returns 'ok' after many sequential appends."""
        last_id = None
        for i in range(20):
            last_id = append_event("test_world", "chat.translation", data={"i": i})

        result = verify_world_ledger("test_world")
        assert result.status == "ok"
        assert result.last_event_id == last_id
