"""Formatting helpers shared across admin TUI screens."""

from __future__ import annotations

from typing import Any


def format_timestamp(timestamp: str | None) -> str:
    """Format a timestamp for display."""
    if not timestamp:
        return "-"
    if "." in timestamp:
        timestamp = timestamp.split(".")[0]
    return timestamp


def truncate(text: str, max_length: int) -> str:
    """Truncate text to a maximum length."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def format_cell(value: Any) -> str:
    """Format arbitrary values for generic table cells."""
    if value is None:
        return "-"
    return str(value)


def format_duration(seconds: int | float | str | None) -> str:
    """Format a duration (seconds) into a human readable string."""
    if seconds is None:
        return "-"
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "-"

    if total < 60:
        return f"{total}s"
    minutes, sec = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
