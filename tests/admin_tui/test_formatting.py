"""Unit tests for shared admin TUI formatting helpers."""

from mud_server.admin_tui.screens import formatting


def test_format_timestamp_handles_none() -> None:
    """format_timestamp returns a placeholder for None values."""
    assert formatting.format_timestamp(None) == "-"


def test_format_timestamp_strips_microseconds() -> None:
    """format_timestamp removes microseconds when present."""
    assert formatting.format_timestamp("2024-01-01 10:11:12.123456") == "2024-01-01 10:11:12"


def test_truncate_short_text_no_change() -> None:
    """truncate leaves short text unchanged."""
    assert formatting.truncate("hello", 10) == "hello"


def test_truncate_long_text_adds_ellipsis() -> None:
    """truncate shortens text and appends ellipsis."""
    assert formatting.truncate("hello world", 8) == "hello..."


def test_format_cell_handles_none() -> None:
    """format_cell converts None to a placeholder string."""
    assert formatting.format_cell(None) == "-"


def test_format_duration_handles_invalid() -> None:
    """format_duration returns placeholder for invalid inputs."""
    assert formatting.format_duration(None) == "-"
    assert formatting.format_duration("nope") == "-"


def test_format_duration_formats_seconds() -> None:
    """format_duration provides readable output for seconds and minutes."""
    assert formatting.format_duration(45) == "45s"
    assert formatting.format_duration(75) == "1m 15s"
    assert formatting.format_duration(3605) == "1h 0m"
