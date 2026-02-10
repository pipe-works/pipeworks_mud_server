"""
Create user screen for PipeWorks Admin TUI.

This screen presents a focused, single-purpose form that allows admins and
superusers to create new accounts. It enforces:
- Role selection constrained by the current user's privileges
- Password confirmation before submission
- Clear inline feedback for validation and API errors
"""

from __future__ import annotations

from collections.abc import Iterable

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from mud_server.admin_tui.api.client import APIError, AuthenticationError

ROLE_LABELS: dict[str, str] = {
    "player": "Player",
    "worldbuilder": "World Builder",
    "admin": "Admin",
    "superuser": "Superuser",
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    "player": "Standard game player with basic gameplay and chat access.",
    "worldbuilder": "Can play and build/edit world content.",
    "admin": "Can manage users and perform administrative actions.",
    "superuser": "Full system access, including all admin capabilities.",
}


class CreateUserScreen(Screen):
    """
    Screen for creating new user accounts.

    Accessible to admins and superusers. The UI is a compact form with:
    - Username input
    - Role dropdown (limited by the caller-provided role list)
    - Role description that updates when the role changes
    - Password + confirmation fields

    The API enforces all security requirements (password policy, uniqueness).
    The screen performs basic client-side checks to guide the user before
    submitting the request.
    """

    BINDINGS = [
        Binding("b", "back", "Back", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
    ]

    CSS = """
    CreateUserScreen {
        layout: vertical;
    }

    .form-container {
        padding: 1 2;
    }

    .form-box {
        width: 70;
        height: auto;
        border: solid $primary;
        padding: 1 2;
    }

    .form-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    .form-label {
        padding-top: 1;
    }

    .form-input {
        margin-bottom: 1;
    }

    .role-description {
        color: $text-muted;
        padding: 0 0 1 0;
    }

    .form-actions {
        height: 3;
        padding-top: 1;
    }

    .action-button {
        margin-right: 1;
    }

    .form-status {
        padding-top: 1;
    }
    """

    def __init__(self, allowed_roles: Iterable[str]) -> None:
        super().__init__()
        # Pre-filter roles to those we know how to label.
        self._allowed_roles = [role for role in allowed_roles if role in ROLE_LABELS]

    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Vertical(classes="form-box"):
                yield Static("Create User", classes="form-title")

                yield Label("Username:", classes="form-label")
                yield Input(
                    placeholder="Choose a username (2-20 characters)",
                    id="username",
                    classes="form-input",
                )

                yield Label("Role:", classes="form-label")
                yield Select(
                    options=self._build_role_options(),
                    value=self._default_role(),
                    id="role",
                    classes="form-input",
                )
                yield Static("", id="role-description", classes="role-description")

                yield Label("Password:", classes="form-label")
                yield Input(
                    placeholder="Enter a strong password",
                    password=True,
                    id="password",
                    classes="form-input",
                )

                yield Label("Confirm Password:", classes="form-label")
                yield Input(
                    placeholder="Re-enter the password",
                    password=True,
                    id="password-confirm",
                    classes="form-input",
                )

                with Horizontal(classes="form-actions"):
                    yield Button(
                        "Create User",
                        variant="primary",
                        id="btn-create",
                        classes="action-button",
                    )
                    yield Button(
                        "Cancel",
                        variant="default",
                        id="btn-cancel",
                        classes="action-button",
                    )

                yield Static("", id="status", classes="form-status")

        yield Footer()

    def on_mount(self) -> None:
        # Apply keybindings and initialize the role description to match the
        # default selection so the user sees the permissions immediately.
        self._apply_keybindings()
        self._update_role_description(self._default_role())
        self.query_one("#username", Input).focus()

    def _apply_keybindings(self) -> None:
        bindings = getattr(self.app, "keybindings", None)
        if not bindings:
            return

        self._keybindings_by_key: dict[str, str] = {}
        for action, keys in bindings.bindings.items():
            if not hasattr(self, f"action_{action}"):
                continue
            for key in keys:
                self._keybindings_by_key.setdefault(key, action)

    def on_key(self, event: events.Key) -> None:
        bindings_map = getattr(self, "_keybindings_by_key", {})
        action = bindings_map.get(event.key)
        if not action:
            return

        handler = getattr(self, f"action_{action}", None)
        if not handler:
            return

        handler()
        event.stop()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()

    def _build_role_options(self) -> list[tuple[str, str]]:
        # Textual Select expects (label, value) tuples.
        return [(ROLE_LABELS[role], role) for role in self._allowed_roles]

    def _default_role(self) -> str:
        # Prefer the first allowed role as the default selection.
        if self._allowed_roles:
            return self._allowed_roles[0]
        return "player"

    def _update_role_description(self, role: str) -> None:
        # Use a simple lookup table to keep descriptions consistent with docs.
        description = ROLE_DESCRIPTIONS.get(role, "")
        self.query_one("#role-description", Static).update(description)

    @on(Select.Changed, "#role")
    def handle_role_changed(self, event: Select.Changed) -> None:
        if event.value is None:
            return
        self._update_role_description(str(event.value))

    @on(Button.Pressed, "#btn-cancel")
    def handle_cancel(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-create")
    async def handle_create(self) -> None:
        await self._attempt_create()

    async def _attempt_create(self) -> None:
        username_input = self.query_one("#username", Input)
        password_input = self.query_one("#password", Input)
        password_confirm_input = self.query_one("#password-confirm", Input)
        role_select = self.query_one("#role", Select)
        status = self.query_one("#status", Static)

        # Normalize inputs before validation.
        username = username_input.value.strip()
        password = password_input.value
        password_confirm = password_confirm_input.value
        role_value = role_select.value or self._default_role()
        role = str(role_value)

        if not username:
            status.update("[red]Please enter a username[/red]")
            username_input.focus()
            return

        if len(username) < 2 or len(username) > 20:
            status.update("[red]Username must be 2-20 characters[/red]")
            username_input.focus()
            return

        if not password:
            status.update("[red]Please enter a password[/red]")
            password_input.focus()
            return

        if password != password_confirm:
            status.update("[red]Passwords do not match[/red]")
            password_confirm_input.focus()
            return

        # Provide immediate feedback before the network request.
        status.update("[yellow]Creating user...[/yellow]")

        try:
            # Delegate full validation to the API so policy stays consistent.
            result = await self.app.api_client.create_user(
                username=username,
                password=password,
                password_confirm=password_confirm,
                role=role,
            )
        except AuthenticationError as exc:
            status.update(f"[red]{exc.detail}[/red]")
            return
        except APIError as exc:
            status.update(f"[red]{exc.detail or exc.message}[/red]")
            return
        except Exception as exc:  # noqa: BLE001
            status.update(f"[red]Failed to create user: {exc}[/red]")
            return

        message = result.get("message", "User created.")
        status.update(f"[green]{message}[/green]")
        username_input.value = ""
        password_input.value = ""
        password_confirm_input.value = ""
        username_input.focus()
