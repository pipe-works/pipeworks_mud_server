"""Ledger package — append-only JSONL event store.

The ledger is the **authoritative record** of all axis mutations in the
PipeWorks system.  The SQLite database is a *materialized view* derived from
it.  Nothing writes axis state to the database without first writing to the
ledger.

Public surface
--------------
- :func:`append_event`        — append a single event to a world's ledger file.
- :func:`verify_world_ledger` — check integrity of the last event in a ledger.
- :exc:`LedgerWriteError`     — raised when a filesystem write fails.
- :class:`LedgerVerifyResult` — result object returned by :func:`verify_world_ledger`.

Usage example
-------------
::

    from mud_server.ledger import append_event, LedgerWriteError

    try:
        event_id = append_event(
            world_id="daily_undertaking",
            event_type="chat.translation",
            data={"status": "success", "ic_output": "The shadows suit you."},
            ipc_hash=None,
            meta={"phase": "pre_axis_engine"},
        )
    except LedgerWriteError:
        logger.warning("Ledger write failed — interaction continues.")

Design notes
------------
- Events are stored at ``data/ledger/<world_id>.jsonl``.
- One file per world; events are interleaved by append order (timestamp order).
- Each line embeds a SHA-256 checksum of its own body for corruption detection.
- Concurrent writes are serialised with an exclusive POSIX file lock (``fcntl``).
- A ledger write failure is **never fatal** to the caller.  The game interaction
  completes; only the audit record is lost.  This is an explicit PoC trade-off;
  mark with ``TODO(ledger-hardening)`` when upgrading to production durability.
"""

from mud_server.ledger.writer import (
    LedgerVerifyResult,
    LedgerWriteError,
    append_event,
    verify_world_ledger,
)

__all__ = [
    "LedgerWriteError",
    "LedgerVerifyResult",
    "append_event",
    "verify_world_ledger",
]
