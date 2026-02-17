"""Typed database/domain exceptions for the DB package.

This module defines a small, explicit exception hierarchy used by repository
modules to signal infrastructure failures (for example SQLite connection/query
errors) without collapsing all failures into boolean return values.

Design intent:
    - Domain outcomes like "row not found" can still be represented by
      ``None``/``False`` where contracts already use those values.
    - Infrastructure failures should raise typed exceptions so API boundaries
      can map them to deterministic HTTP 5xx responses and logs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DatabaseOperationContext:
    """Structured operation metadata carried by repository exceptions.

    Attributes:
        operation: Stable operation identifier (for example
            ``"sessions.create_session"``).
        details: Optional human-readable context for logs and debugging.
    """

    operation: str
    details: str | None = None


class DatabaseError(RuntimeError):
    """Base exception for DB-layer failures."""


class DatabaseOperationError(DatabaseError):
    """Base exception for repository operation failures.

    Args:
        context: Structured operation metadata.
        cause: Optional underlying exception.
    """

    def __init__(
        self,
        *,
        context: DatabaseOperationContext,
        cause: Exception | None = None,
    ) -> None:
        message = context.operation
        if context.details:
            message = f"{message}: {context.details}"
        super().__init__(message)
        self.context = context
        self.cause = cause


class DatabaseReadError(DatabaseOperationError):
    """Repository read/query failure."""


class DatabaseWriteError(DatabaseOperationError):
    """Repository mutation/transaction failure."""
