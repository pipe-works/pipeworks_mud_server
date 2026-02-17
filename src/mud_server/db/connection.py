"""SQLite connection primitives for the MUD server DB layer.

This module owns connection creation and low-level SQLite runtime pragmas so
repository code can stay focused on queries and transaction intent.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def get_db_path() -> Path:
    """Resolve the absolute SQLite database path from runtime configuration."""
    from mud_server.config import config

    return config.database.absolute_path


def configure_connection(connection: sqlite3.Connection) -> sqlite3.Connection:
    """Apply connection-level SQLite pragmas required by the application.

    Notes:
        - ``foreign_keys=ON`` is required because SQLite does not enforce
          foreign-key constraints by default.
        - ``busy_timeout`` reduces transient lock failures during short-lived
          concurrent writes in tests and local multi-process development.
    """
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def get_connection() -> sqlite3.Connection:
    """Create and configure a new SQLite connection."""
    connection = sqlite3.connect(str(get_db_path()))
    return configure_connection(connection)


@contextmanager
def connection_scope(*, write: bool = False) -> Iterator[sqlite3.Connection]:
    """Yield a configured connection with guaranteed cleanup semantics.

    Args:
        write: When True, commit on success and rollback on exceptions.

    Yields:
        Configured SQLite connection ready for cursor operations.

    Behavior:
        - Always closes the connection in ``finally``.
        - For write scopes, commits at the end of a successful block.
        - For write scopes, attempts rollback before re-raising failures.
    """
    connection = get_connection()
    try:
        yield connection
        if write:
            connection.commit()
    except Exception:
        if write:
            try:
                connection.rollback()
            except sqlite3.Error:
                # Preserve the original exception while best-effort rolling back.
                pass
        raise
    finally:
        connection.close()
