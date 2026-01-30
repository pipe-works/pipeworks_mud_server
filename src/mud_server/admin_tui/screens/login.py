"""
Login screen for PipeWorks Admin TUI.

This module provides the login form where administrators enter their
credentials to authenticate with the MUD server.

The LoginScreen uses Textual's Screen class to provide a full-window
login form with username and password inputs.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static


class LoginScreen(Screen):
    """
    Login screen with username/password form.

    This screen displays a centered login form. On successful authentication,
    it posts a LoginSuccess message that the main app handles to transition
    to the dashboard.

    CSS Classes:
        .login-box: The container for the login form.
        .login-title: The "Admin Login" heading.
        .login-label: Labels for input fields.
        .login-input: The input fields.
        .login-button: The submit button.
        .login-error: Error message display.

    Messages:
        LoginSuccess: Posted when login succeeds, contains username and role.
    """

    # CSS styling for the login form
    CSS = """
    LoginScreen {
        align: center middle;
    }

    .login-box {
        width: 60;
        height: auto;
        border: solid green;
        padding: 1 2;
    }

    .login-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    .login-label {
        padding-top: 1;
    }

    .login-input {
        margin-bottom: 1;
    }

    .login-button {
        width: 100%;
        margin-top: 1;
    }

    .login-error {
        color: $error;
        text-align: center;
        padding-top: 1;
    }

    .login-status {
        color: $text-muted;
        text-align: center;
        padding-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """
        Create the login form layout.

        The form consists of:
        - Title
        - Username input
        - Password input
        - Login button
        - Status/error message area
        """
        with Center():
            with Vertical(classes="login-box"):
                yield Static("PipeWorks Admin Login", classes="login-title")
                yield Label("Username:", classes="login-label")
                yield Input(placeholder="Enter username", id="username", classes="login-input")
                yield Label("Password:", classes="login-label")
                yield Input(
                    placeholder="Enter password",
                    password=True,
                    id="password",
                    classes="login-input",
                )
                yield Button("Login", variant="primary", id="login-btn", classes="login-button")
                yield Static("", id="status", classes="login-status")

    def on_mount(self) -> None:
        """Focus the username field when the screen mounts."""
        self.query_one("#username", Input).focus()

    @on(Button.Pressed, "#login-btn")
    async def handle_login_button(self) -> None:
        """Handle the login button press."""
        await self._attempt_login()

    @on(Input.Submitted)
    async def handle_input_submitted(self, event: Input.Submitted) -> None:
        """
        Handle Enter key in input fields.

        If Enter is pressed in the username field, move to password.
        If Enter is pressed in the password field, attempt login.
        """
        if event.input.id == "username":
            # Move focus to password field
            self.query_one("#password", Input).focus()
        elif event.input.id == "password":
            # Attempt login
            await self._attempt_login()

    async def _attempt_login(self) -> None:
        """
        Attempt to log in with the entered credentials.

        Updates the status message during the attempt and shows
        any errors that occur.
        """
        # Get input values
        username_input = self.query_one("#username", Input)
        password_input = self.query_one("#password", Input)
        status = self.query_one("#status", Static)

        username = username_input.value.strip()
        password = password_input.value

        # Validate inputs
        if not username:
            status.update("[red]Please enter a username[/red]")
            username_input.focus()
            return

        if not password:
            status.update("[red]Please enter a password[/red]")
            password_input.focus()
            return

        # Show logging in status
        status.update("[yellow]Logging in...[/yellow]")

        # Attempt login through the app
        # The app's api_client handles the actual HTTP request
        try:
            await self.app.do_login(username, password)  # type: ignore
            status.update("[green]Login successful![/green]")
        except Exception as e:
            # Show error message
            error_msg = str(e)
            if "401" in error_msg or "Invalid" in error_msg.lower():
                status.update("[red]Invalid username or password[/red]")
            elif "connect" in error_msg.lower():
                status.update("[red]Cannot connect to server[/red]")
            else:
                status.update(f"[red]Login failed: {error_msg}[/red]")
            password_input.value = ""
            password_input.focus()
