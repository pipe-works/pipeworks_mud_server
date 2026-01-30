"""
Register Tab for MUD Client.

This module provides the registration interface for creating new user accounts.
Visible only when not logged in.

Migration Notes:
    - Migrated from old api_client.py to new modular structure
    - Uses AuthAPIClient for registration API calls
    - Extracts message from API response dict for Gradio display
"""

import gradio as gr

from mud_server.admin_gradio.api.auth import AuthAPIClient

# Create module-level API client instance for reuse
_auth_client = AuthAPIClient()


def register(username: str, password: str, password_confirm: str) -> str:
    """
    Handle new user account registration.

    Validates input, sends registration request to backend API via AuthAPIClient,
    and returns status message indicating success or failure.

    This function wraps the new AuthAPIClient.register() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Args:
        username: Desired username for new account
        password: Plain text password for new account
        password_confirm: Password confirmation (must match password)

    Returns:
        String message indicating registration success or failure

    Examples:
        >>> result = register("alice", "password123", "password123")
        >>> "You can now login" in result
        True
    """
    # Call the new API client
    api_result = _auth_client.register(username, password, password_confirm)

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def create():
    """
    Create the Register tab with account creation form.

    Returns:
        tuple: (register_tab, register_btn) - Tab component and register button for event wiring
    """
    with gr.Tab("Register", visible=True) as register_tab:
        with gr.Column():
            gr.Markdown("### Create a new account")
            gr.Markdown("*Default role: Player*")

            register_username_input = gr.Textbox(
                label="Username",
                placeholder="Choose a username (2-20 characters)",
                max_lines=1,
            )
            register_password_input = gr.Textbox(
                label="Password",
                placeholder="Enter password (min 8 characters)",
                type="password",
                max_lines=1,
            )
            register_password_confirm_input = gr.Textbox(
                label="Confirm Password",
                placeholder="Re-enter your password",
                type="password",
                max_lines=1,
            )
            register_btn = gr.Button("Register", variant="primary")
            register_output = gr.Textbox(label="Registration Status", interactive=False, lines=10)

            # Wire up register button
            register_btn.click(
                register,
                inputs=[
                    register_username_input,
                    register_password_input,
                    register_password_confirm_input,
                ],
                outputs=[register_output],
            )

    return register_tab
