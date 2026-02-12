"""Modal dialogs used by the admin database screen."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmKickScreen(ModalScreen[bool]):
    """Modal confirmation prompt for kicking a session."""

    DEFAULT_CSS = """
    ConfirmKickScreen {
        align: center middle;
    }

    .confirm-dialog {
        width: 60;
        border: solid $primary;
        padding: 1 2;
        background: $surface;
    }

    .confirm-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    .confirm-actions {
        height: 3;
        padding-top: 1;
    }

    .confirm-button {
        margin-right: 1;
    }
    """

    def __init__(self, username: str, session_id: str) -> None:
        super().__init__()
        self._username = username
        self._session_id = session_id

    def compose(self) -> ComposeResult:
        with Vertical(classes="confirm-dialog"):
            yield Static("Kick Session", classes="confirm-title")
            yield Static(
                f"Kick {self._username}?\nSession: {self._session_id}",
                id="confirm-message",
            )
            with Horizontal(classes="confirm-actions"):
                yield Button(
                    "Cancel", variant="default", id="confirm-cancel", classes="confirm-button"
                )
                yield Button(
                    "Kick", variant="warning", id="confirm-accept", classes="confirm-button"
                )

    @on(Button.Pressed, "#confirm-cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-accept")
    def _accept(self) -> None:
        self.dismiss(True)


class ConfirmUserRemovalScreen(ModalScreen[str | None]):
    """Modal confirmation prompt for user deactivation or deletion."""

    DEFAULT_CSS = """
    ConfirmUserRemovalScreen {
        align: center middle;
    }

    .confirm-dialog {
        width: 70;
        border: solid $primary;
        padding: 1 2;
        background: $surface;
    }

    .confirm-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    .confirm-actions {
        height: 3;
        padding-top: 1;
    }

    .confirm-button {
        margin-right: 1;
    }
    """

    def __init__(self, username: str, role: str) -> None:
        super().__init__()
        self._username = username
        self._role = role

    def compose(self) -> ComposeResult:
        with Vertical(classes="confirm-dialog"):
            yield Static("Remove User", classes="confirm-title")
            yield Static(
                "\n".join(
                    [
                        f"User: {self._username} ({self._role})",
                        "",
                        "Deactivate: disables login and removes active sessions.",
                        "Delete: permanently removes the user and related data.",
                    ]
                ),
                id="confirm-message",
            )
            with Horizontal(classes="confirm-actions"):
                yield Button(
                    "Cancel", variant="default", id="confirm-cancel", classes="confirm-button"
                )
                yield Button(
                    "Deactivate",
                    variant="warning",
                    id="confirm-deactivate",
                    classes="confirm-button",
                )
                yield Button(
                    "Delete",
                    variant="error",
                    id="confirm-delete",
                    classes="confirm-button",
                )

    @on(Button.Pressed, "#confirm-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-deactivate")
    def _deactivate(self) -> None:
        self.dismiss("deactivate")

    @on(Button.Pressed, "#confirm-delete")
    def _delete(self) -> None:
        self.dismiss("delete")
