"""Unit tests for admin TUI database action helpers."""

from textual.widget import SkipAction

from mud_server.admin_tui.screens.database_actions import DatabaseActions


class _FakeTable:
    """Table stub that can raise SkipAction for cursor moves."""

    def __init__(self, raise_skip: bool = False) -> None:
        self.raise_skip = raise_skip
        self.left_called = False
        self.right_called = False

    def action_cursor_left(self) -> None:
        self.left_called = True
        if self.raise_skip:
            raise SkipAction()

    def action_cursor_right(self) -> None:
        self.right_called = True
        if self.raise_skip:
            raise SkipAction()


class _FakeScreen:
    """Minimal screen stub for cursor safety tests."""

    def __init__(self, table: _FakeTable) -> None:
        self._table = table

    def get_active_table(self):
        return self._table


def test_safe_cursor_left_handles_skip() -> None:
    """safe_cursor_left swallows SkipAction and does not raise."""
    table = _FakeTable(raise_skip=True)
    actions = DatabaseActions(_FakeScreen(table))
    actions.safe_cursor_left()
    assert table.left_called is True


def test_safe_cursor_right_handles_skip() -> None:
    """safe_cursor_right swallows SkipAction and does not raise."""
    table = _FakeTable(raise_skip=True)
    actions = DatabaseActions(_FakeScreen(table))
    actions.safe_cursor_right()
    assert table.right_called is True
