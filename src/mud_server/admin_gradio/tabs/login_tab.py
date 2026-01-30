"""
Login Tab for MUD Client.

This module provides the login interface for user authentication.
Always visible, provides username/password input and login button.
"""

import gradio as gr


def create():
    """
    Create the Login tab with authentication form.

    Returns:
        tuple: (login_tab, login_btn, login_username_input, login_password_input,
                login_output) - Components needed for event wiring in main app
    """
    with gr.Tab("Login", visible=True) as login_tab:
        with gr.Column():
            gr.Markdown("### Login to your account")

            login_username_input = gr.Textbox(
                label="Username",
                placeholder="Enter your username",
                max_lines=1,
            )
            login_password_input = gr.Textbox(
                label="Password",
                placeholder="Enter your password",
                type="password",
                max_lines=1,
            )
            login_btn = gr.Button("Login", variant="primary")
            login_output = gr.Textbox(label="Login Status", interactive=False, lines=10)

    return (
        login_tab,
        login_btn,
        login_username_input,
        login_password_input,
        login_output,
    )
