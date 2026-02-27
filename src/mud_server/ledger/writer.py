"""JSONL ledger writer for the PipeWorks axis engine.

Overview
--------
This module is the single implementation file for the ledger package.  It
exposes two public functions (:func:`append_event` and
:func:`verify_world_ledger`) and the types they return.

The ledger is the **authoritative record** of all axis mutations.  The
SQLite database is a *materialized view* derived from the ledger.  The
sequence is always:

1. Compute axis deltas (axis engine).
2. Write a ``chat.mechanical_resolution`` event to the JSONL ledger.  ← authoritative
3. Apply deltas to the DB (materialization step).                       ← derived

Until the axis engine is built, ``chat.translation`` events are written with
``ipc_hash: null`` and ``meta.phase = "pre_axis_engine"``.  These are honest
incomplete records, not errors.

Storage
-------
Each world's events are stored in a single JSONL file::

    data/ledger/<world_id>.jsonl

One file per world.  Events are appended in timestamp order (append order ==
wall-clock order in a single-process server).  The directory and file are
created automatically on the first write.

Envelope format
---------------
Every line is a self-contained JSON object with the following fields:

.. code-block:: json

    {
      "event_id":       "a3f91c9e2d4b5e6f...",
      "timestamp":      "2026-02-27T14:23:01.452345+00:00",
      "world_id":       "daily_undertaking",
      "event_type":     "chat.translation",
      "schema_version": "1.0",
      "ipc_hash":       null,
      "meta":           {"phase": "pre_axis_engine"},
      "data":           { ... event-specific payload ... },
      "_checksum":      "sha256:b94f3e..."
    }

``_checksum`` is computed over the JSON-serialized envelope body (all fields
**except** ``_checksum`` itself, serialized with ``sort_keys=True``).  This
allows corruption detection without the checksum being part of its own input.

Event type namespace
--------------------
::

    chat.mechanical_resolution    axis engine: chat resolver
    chat.translation              translation layer
    environment.condition_applied axis engine: environmental resolver (future)
    action.physical_resolved      axis engine: physical resolver (future)
    outcome.economic_resolved     axis engine: economic resolver (future)
    axis.manual_override          admin/superuser override (future)

Concurrency
-----------
``fcntl.flock(LOCK_EX)`` is acquired before every append and released after
``flush()``.  This serialises concurrent writers within a single process and
across multiple processes on the same host.

**Platform note:** ``fcntl`` is POSIX-only (Darwin + Linux).  Windows is not
supported by the ledger writer.  If Windows support is needed, replace
``fcntl.flock`` with a cross-platform locking library such as ``filelock``.

Failure isolation
-----------------
:exc:`LedgerWriteError` is raised on filesystem failure.  Callers must catch
it, log a warning, and continue.  A ledger failure is **never fatal** to the
calling game interaction — only the audit record is lost.

::

    # Correct caller pattern:
    try:
        append_event(...)
    except LedgerWriteError:
        logger.warning("Ledger write failed — interaction continues.", exc_info=True)

TODO(ledger-hardening): In a production deployment, a failed ledger write
should trigger an alert and degrade the affected world to read-only mode.
The PoC treats ledger failures as non-fatal warnings.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from mud_server.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# ── Schema version ─────────────────────────────────────────────────────────────
# Increment when the envelope format changes in a backwards-incompatible way.
# Readers should reject envelopes with an unknown schema_version.
_SCHEMA_VERSION = "1.0"

# ── Ledger root directory ──────────────────────────────────────────────────────
# Resolved relative to the project root.  Tests monkeypatch this to redirect
# ledger writes into a temporary directory.
_LEDGER_ROOT: Path = PROJECT_ROOT / "data" / "ledger"

# ── Read-tail chunk size ───────────────────────────────────────────────────────
# Number of bytes read from the end of the ledger file when verifying the last
# event.  A single JSONL line for a two-character chat interaction with 11 axes
# is typically 600–1500 bytes.  16 KiB is a safe upper bound for any single
# event in the current schema.
_TAIL_CHUNK_BYTES = 16_384


# ── Exception ─────────────────────────────────────────────────────────────────


class LedgerWriteError(Exception):
    """Raised when a ledger append fails due to a filesystem or encoding error.

    Callers **must** catch this exception, log a warning, and allow the game
    interaction to continue.  A ledger write failure must never propagate to
    the player-facing response.

    Attributes:
        message: Human-readable description of the failure.

    Example::

        try:
            append_event(world_id, event_type, data)
        except LedgerWriteError as exc:
            logger.warning("Ledger write failed: %s", exc)
    """


# ── Result type ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LedgerVerifyResult:
    """Result of a ledger integrity check performed by :func:`verify_world_ledger`.

    Attributes:
        status: One of:
            - ``"ok"``      — last event is valid JSON and checksum matches.
            - ``"empty"``   — file does not exist or contains no events.
            - ``"corrupt"`` — last line is malformed JSON or checksum mismatch.
        last_event_id: The ``event_id`` of the last valid event, or ``None``
            if the ledger is empty or corrupt.
        error_detail: Human-readable description of the failure reason, or
            ``None`` if status is ``"ok"`` or ``"empty"``.
    """

    status: Literal["ok", "empty", "corrupt"]
    last_event_id: str | None
    error_detail: str | None


# ── Public API ────────────────────────────────────────────────────────────────


def append_event(
    world_id: str,
    event_type: str,
    data: dict,
    *,
    ipc_hash: str | None = None,
    meta: dict | None = None,
) -> str:
    """Append one event to the world's JSONL ledger file.

    This is the **only** authorised write path for all axis events.  The
    caller must never write directly to the JSONL file.

    The function:

    1. Validates ``world_id`` and ``event_type``.
    2. Generates a unique ``event_id`` (UUID4 hex) and ISO-8601 UTC timestamp.
    3. Assembles the envelope dict (all fields except ``_checksum``).
    4. Computes a SHA-256 checksum over the canonical JSON serialisation of
       the envelope body.
    5. Appends the completed envelope as a single newline-terminated JSON line
       under an exclusive POSIX file lock.

    The ledger directory and file are created if they do not yet exist.

    Args:
        world_id:   World this event belongs to.  Must be non-empty.  Used as
                    the filename stem: ``data/ledger/<world_id>.jsonl``.
        event_type: Dot-namespaced event type, e.g. ``"chat.translation"`` or
                    ``"chat.mechanical_resolution"``.  Must be non-empty.
        data:       Event-specific payload dict.  Must be JSON-serialisable.
                    The schema is defined by the event type; this module is
                    opaque to the payload content.
        ipc_hash:   Optional IPC hash produced by the axis engine.  ``None``
                    is valid and honest for pre-axis-engine events; it is
                    stored as JSON ``null``.
        meta:       Optional metadata dict for phase markers and diagnostic
                    fields, e.g. ``{"phase": "pre_axis_engine"}``.  If
                    ``None``, an empty dict is stored.

    Returns:
        The ``event_id`` of the written event as a 32-character lowercase hex
        string (UUID4 without hyphens).

    Raises:
        ValueError:        If ``world_id`` or ``event_type`` is empty or
                           blank.
        LedgerWriteError:  If the filesystem write fails for any reason
                           (disk full, permission denied, invalid path).
                           Callers must catch this and log a warning.

    Example::

        event_id = append_event(
            world_id="daily_undertaking",
            event_type="chat.translation",
            data={"status": "success", "ic_output": "The shadows suit you."},
            ipc_hash=None,
            meta={"phase": "pre_axis_engine"},
        )
        logger.debug("Ledger event written: %s", event_id)
    """
    if not world_id or not world_id.strip():
        raise ValueError("append_event: world_id must be a non-empty string.")
    if not event_type or not event_type.strip():
        raise ValueError("append_event: event_type must be a non-empty string.")

    event_id = uuid.uuid4().hex  # 32-char lowercase hex, no hyphens
    timestamp = datetime.now(UTC).isoformat()

    # ── Assemble envelope body (all fields except _checksum) ──────────────────
    # sort_keys=True is used throughout so that the canonical serialisation is
    # deterministic regardless of dict insertion order.
    envelope_body: dict = {
        "event_id": event_id,
        "timestamp": timestamp,
        "world_id": world_id,
        "event_type": event_type,
        "schema_version": _SCHEMA_VERSION,
        "ipc_hash": ipc_hash,
        "meta": meta if meta is not None else {},
        "data": data,
    }

    # ── Compute and embed checksum ─────────────────────────────────────────────
    # The checksum covers all fields in envelope_body with sort_keys=True.
    # The _checksum field is then added to produce the final envelope.
    checksum = _compute_checksum(envelope_body)
    envelope = {**envelope_body, "_checksum": f"sha256:{checksum}"}

    # ── Serialise and write ────────────────────────────────────────────────────
    line = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
    ledger_path = _ledger_path(world_id)

    try:
        _append_line_locked(ledger_path, line)
    except OSError as exc:
        raise LedgerWriteError(
            f"Failed to write event {event_id!r} to ledger for world "
            f"{world_id!r} at {ledger_path}: {exc}"
        ) from exc

    logger.debug(
        "ledger: appended %r event %s to %s",
        event_type,
        event_id,
        ledger_path.name,
    )
    return event_id


def verify_world_ledger(world_id: str) -> LedgerVerifyResult:
    """Verify the integrity of the most recent event in a world's ledger.

    Intended to be called at **server startup** to detect corruption before
    the first write.  Only the last non-empty line is inspected; a full
    replay verification (reading every line from the beginning) is future
    scope.

    The check performs two assertions:

    1. The last line deserialises as valid JSON.
    2. The ``_checksum`` field in that line matches the SHA-256 computed from
       the line body (all fields except ``_checksum``, serialised with
       ``sort_keys=True``).

    If the last line is corrupt, the caller should log a ``CRITICAL``-level
    warning.  The server is **not** blocked from starting in the PoC — this
    is a diagnostic tool, not an enforced gate.  Mark with
    ``TODO(ledger-hardening)`` when upgrading to a production guard.

    Args:
        world_id: The world whose ledger to verify.

    Returns:
        A :class:`LedgerVerifyResult` describing the outcome.  The
        ``last_event_id`` field is populated on ``"ok"`` status and is
        ``None`` for ``"empty"`` or ``"corrupt"``.

    Example::

        result = verify_world_ledger("daily_undertaking")
        if result.status == "corrupt":
            logger.critical(
                "Ledger integrity failure for world %r: %s",
                "daily_undertaking",
                result.error_detail,
            )
        elif result.status == "ok":
            logger.info("Ledger OK, last event: %s", result.last_event_id)
    """
    path = _ledger_path(world_id)

    # ── File absent or empty ───────────────────────────────────────────────────
    if not path.exists():
        return LedgerVerifyResult(status="empty", last_event_id=None, error_detail=None)

    last_line = _read_last_nonempty_line(path)
    if last_line is None:
        return LedgerVerifyResult(status="empty", last_event_id=None, error_detail=None)

    # ── JSON parse ────────────────────────────────────────────────────────────
    try:
        envelope = json.loads(last_line)
    except json.JSONDecodeError as exc:
        return LedgerVerifyResult(
            status="corrupt",
            last_event_id=None,
            error_detail=f"Last line is not valid JSON: {exc}",
        )

    if not isinstance(envelope, dict):
        return LedgerVerifyResult(
            status="corrupt",
            last_event_id=None,
            error_detail="Last line deserialised to a non-dict type.",
        )

    # ── Checksum verification ─────────────────────────────────────────────────
    recorded_checksum = envelope.get("_checksum")
    if not isinstance(recorded_checksum, str):
        return LedgerVerifyResult(
            status="corrupt",
            last_event_id=None,
            error_detail=(
                "Last line is missing or has a non-string '_checksum' field."
            ),
        )

    # Reconstruct the body (sans _checksum) exactly as it was when the checksum
    # was originally computed: same keys, same sort_keys=True serialisation.
    body = {k: v for k, v in envelope.items() if k != "_checksum"}
    expected_checksum = f"sha256:{_compute_checksum(body)}"

    if recorded_checksum != expected_checksum:
        return LedgerVerifyResult(
            status="corrupt",
            last_event_id=envelope.get("event_id"),  # best-effort ID, may be wrong
            error_detail=(
                f"Checksum mismatch on last event. "
                f"Recorded: {recorded_checksum!r}. "
                f"Expected: {expected_checksum!r}."
            ),
        )

    # ── event_id presence ─────────────────────────────────────────────────────
    event_id = envelope.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        return LedgerVerifyResult(
            status="corrupt",
            last_event_id=None,
            error_detail="Last line is missing a valid 'event_id' string.",
        )

    return LedgerVerifyResult(status="ok", last_event_id=event_id, error_detail=None)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _ledger_path(world_id: str) -> Path:
    """Resolve the absolute JSONL ledger path for a given world.

    The path is ``<_LEDGER_ROOT>/<world_id>.jsonl``.  ``_LEDGER_ROOT``
    defaults to ``<project_root>/data/ledger`` and can be monkeypatched in
    tests to redirect writes to a temporary directory.

    Args:
        world_id: The world ID string.  Expected to be a valid filesystem name
                  component (alphanumeric + underscore).  No sanitisation is
                  performed here; callers are responsible for validated input.

    Returns:
        Absolute :class:`~pathlib.Path` to the JSONL ledger file.
    """
    return _LEDGER_ROOT / f"{world_id}.jsonl"


def _compute_checksum(payload: dict) -> str:
    """Compute a SHA-256 hex digest of the canonical JSON serialisation of ``payload``.

    The payload is serialised with ``ensure_ascii=False, sort_keys=True`` to
    produce a stable byte representation regardless of dict insertion order or
    key ordering.  This is the same serialisation used when writing the
    envelope, so checksums are always reproducible given the same input dict.

    Args:
        payload: The dict to checksum.  Must be JSON-serialisable.  The
                 ``_checksum`` field must **not** be present in ``payload``
                 when this function is used for verification — strip it first.

    Returns:
        64-character lowercase hex SHA-256 digest string.  The ``sha256:``
        prefix is **not** included; callers prepend it when embedding.

    Example::

        body = {"event_id": "abc", "data": {}}
        digest = _compute_checksum(body)
        assert len(digest) == 64
        assert digest == _compute_checksum({"data": {}, "event_id": "abc"})  # sort_keys stable
    """
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _append_line_locked(path: Path, line: str) -> None:
    """Append a single newline-terminated line to ``path`` under an exclusive lock.

    Creates the parent directory hierarchy and the file itself if they do not
    exist.  Acquires an exclusive POSIX file lock (``fcntl.LOCK_EX``) before
    writing, flushes the write buffer, and releases the lock in the ``finally``
    block.

    Locking semantics
    ~~~~~~~~~~~~~~~~~
    ``fcntl.LOCK_EX`` blocks until the lock is available, so concurrent writers
    queue up and execute in arrival order.  There is no timeout; if a writer
    holds the lock indefinitely (e.g. due to a hang), other writers will block.
    For the PoC this is acceptable.

    ``TODO(ledger-hardening)``: add a configurable lock-acquisition timeout and
    raise ``LedgerWriteError`` if the timeout is exceeded, to prevent request
    pile-up under pathological conditions.

    Platform note
    ~~~~~~~~~~~~~
    ``fcntl`` is a POSIX API available on Darwin and Linux.  It is **not**
    available on Windows.  If Windows support is needed, replace this function
    with one that uses ``msvcrt.locking`` or a cross-platform library.

    Args:
        path: Absolute path to the JSONL file.  Parent directories are created
              with ``mkdir(parents=True, exist_ok=True)`` before opening.
        line: Fully-serialised JSON string.  A trailing newline (``"\\n"``) is
              appended by this function; callers must not include one.

    Raises:
        OSError: If the directory creation, file open, or write fails.  The
                 caller (:func:`append_event`) converts this to a
                 :exc:`LedgerWriteError`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(line + "\n")
            fh.flush()
        finally:
            # Always release the lock, even if the write raised.
            fcntl.flock(fh, fcntl.LOCK_UN)


def _read_last_nonempty_line(path: Path) -> str | None:
    """Return the last non-empty line from a file without reading it fully.

    Reads at most :data:`_TAIL_CHUNK_BYTES` bytes from the end of the file and
    searches backwards for the last line that contains non-whitespace content.
    This avoids loading large ledger files into memory when only the tail is
    needed (e.g. for integrity verification at startup).

    Chunk size assumption
    ~~~~~~~~~~~~~~~~~~~~~
    :data:`_TAIL_CHUNK_BYTES` (16 KiB) is large enough to contain any single
    JSONL event in the current schema (a two-character interaction with 11
    axes produces a line of approximately 600–1500 bytes).  If a future event
    type produces lines exceeding 16 KiB, increase ``_TAIL_CHUNK_BYTES``
    accordingly.  The function does not handle the case where the last line
    straddles the chunk boundary — it will silently return an earlier line.

    ``TODO(ledger-hardening)``: For production reliability, iterate backwards
    in multiple chunks if the first chunk does not contain a complete line.

    Args:
        path: Path to the file to read.  Must exist (callers check this first).

    Returns:
        The last non-empty, non-whitespace line as a stripped string, or
        ``None`` if the file contains only whitespace/blank lines or an
        :exc:`OSError` occurs during reading.
    """
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)  # SEEK_END — position cursor at the end of the file
            size = fh.tell()

            if size == 0:
                return None

            # Read the tail chunk (up to _TAIL_CHUNK_BYTES from the end).
            chunk_start = max(0, size - _TAIL_CHUNK_BYTES)
            fh.seek(chunk_start)
            chunk = fh.read()

        # Decode and search the lines in reverse for the last non-empty one.
        # Errors='replace' prevents UnicodeDecodeError on corrupt bytes.
        lines = chunk.decode("utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            stripped = line.strip()
            if stripped:
                return stripped

        return None

    except OSError:
        # If the file cannot be read (permissions, I/O error), treat as
        # unreadable — the caller handles the None return.
        return None
