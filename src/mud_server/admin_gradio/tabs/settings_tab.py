"""
Settings Tab for MUD Client.

This module provides the settings interface for password changes and server control.
Visible only when logged in. Server control section is admin/superuser only.

Migration Notes:
    - Migrated from old api_client.py to new modular structure
    - Uses SettingsAPIClient for password change and server control
    - Wrapper functions extract session_id and role from session_state
    - Returns message string for Gradio display
"""

import gradio as gr

from mud_server.admin_gradio.api.settings import SettingsAPIClient

# Create module-level API client instance for reuse
_settings_client = SettingsAPIClient()


def change_password(
    old_password: str, new_password: str, confirm_password: str, session_state: dict
) -> str:
    """
    Change the current user's password.

    Validates passwords, sends change request to backend via SettingsAPIClient,
    and returns status message.

    This function wraps the new SettingsAPIClient.change_password() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Args:
        old_password: Current password (for verification)
        new_password: Desired new password
        confirm_password: New password confirmation
        session_state: User's session state dictionary containing session_id

    Returns:
        Status message string indicating success or failure

    Examples:
        >>> session = {"session_id": "abc123", "logged_in": True}
        >>> result = change_password("old123", "newpass123", "newpass123", session)
        >>> "successfully" in result.lower() or "failed" in result.lower()
        True
    """
    # Extract session_id from session state
    session_id = session_state.get("session_id")

    # Call the new API client
    api_result = _settings_client.change_password(
        session_id=session_id,
        old_password=old_password,
        new_password=new_password,
        confirm_password=confirm_password,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def stop_server(session_state: dict) -> str:
    """
    Stop the backend server (Admin/Superuser only).

    Sends stop request to backend via SettingsAPIClient and returns status message.

    This function wraps the new SettingsAPIClient.stop_server() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Args:
        session_state: User's session state dictionary containing session_id and role

    Returns:
        Status message string indicating success or error

    Examples:
        >>> session = {"session_id": "abc123", "role": "admin", "logged_in": True}
        >>> result = stop_server(session)
        >>> isinstance(result, str)
        True
    """
    # Extract session_id and role from session state
    session_id = session_state.get("session_id")
    role = session_state.get("role", "player")

    # Call the new API client
    api_result = _settings_client.stop_server(
        session_id=session_id,
        role=role,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def create(session_state):
    """
    Create the Settings tab with password change and server control.

    Args:
        session_state: Gradio State component for session tracking

    Returns:
        gr.Tab: Configured Settings tab component
    """
    with gr.Tab("Settings", visible=False) as settings_tab:
        with gr.Column():
            # Password Change Section (Collapsible)
            with gr.Accordion("Change Password", open=False):
                gr.Markdown("Update your account password")

                current_password_input = gr.Textbox(
                    label="Current Password",
                    placeholder="Enter your current password",
                    type="password",
                    max_lines=1,
                )
                new_password_input = gr.Textbox(
                    label="New Password",
                    placeholder="Enter new password (min 8 characters)",
                    type="password",
                    max_lines=1,
                )
                confirm_new_password_input = gr.Textbox(
                    label="Confirm New Password",
                    placeholder="Re-enter new password",
                    type="password",
                    max_lines=1,
                )
                change_password_btn = gr.Button("Change Password", variant="primary")
                change_password_output = gr.Textbox(label="Status", interactive=False, lines=5)

                change_password_btn.click(
                    change_password,
                    inputs=[
                        current_password_input,
                        new_password_input,
                        confirm_new_password_input,
                        session_state,
                    ],
                    outputs=[change_password_output],
                )

            # Server Control Section (Admin/Superuser only)
            gr.Markdown("---")
            with gr.Accordion("Server Control (Admin/Superuser)", open=False):
                gr.Markdown("**Warning:** This will stop the entire server!")

                stop_server_btn = gr.Button("Stop Server", variant="stop")
                stop_server_output = gr.Textbox(label="Status", interactive=False, lines=3)

                stop_server_btn.click(
                    stop_server,
                    inputs=[session_state],
                    outputs=[stop_server_output],
                )

    return settings_tab
