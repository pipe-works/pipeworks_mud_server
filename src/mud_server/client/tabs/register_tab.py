"""
Register Tab for MUD Client.

This module provides the registration interface for creating new user accounts.
Visible only when not logged in.
"""

import gradio as gr
from mud_server.client.api_client import register


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
            register_output = gr.Textbox(
                label="Registration Status", interactive=False, lines=10
            )

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
