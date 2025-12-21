"""
Settings Tab for MUD Client.

This module provides the settings interface for password changes and server control.
Visible only when logged in. Server control section is admin/superuser only.
"""

import gradio as gr
from mud_server.client.api_client import change_password, stop_server


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
