"""Unit tests for admin TUI database tab helpers."""

from mud_server.admin_tui.screens.database_tabs import UsersTab


class _DummyScreen:
    """Minimal screen stub for UsersTab sorting tests."""

    def __init__(self) -> None:
        self.last_rows: list[dict[str, str]] = []

    def query_one(self, *_args, **_kwargs):  # pragma: no cover - not used
        raise AssertionError("query_one should not be called in this test")


def test_users_tab_sort_toggles_direction() -> None:
    """UsersTab.sort_by_column toggles sorting direction on repeated calls."""
    screen = _DummyScreen()
    tab = UsersTab(screen)

    # Inject users and a render hook that records order.
    tab._users_cache = [
        {"id": 1, "username": "delta"},
        {"id": 2, "username": "alpha"},
        {"id": 3, "username": "charlie"},
    ]

    def _record(users):
        screen.last_rows = users

    tab._render_users_table = _record  # type: ignore[method-assign]

    # Sort by username column (index 1).
    tab.sort_by_column(1)
    assert [u["username"] for u in screen.last_rows] == ["alpha", "charlie", "delta"]

    # Sort again on same column should reverse.
    tab.sort_by_column(1)
    assert [u["username"] for u in screen.last_rows] == ["delta", "charlie", "alpha"]
