"""
Database Tab for MUD Client.

This module provides the database viewer and user management interface.
Visible only for admin and superuser roles.
"""

import gradio as gr
from mud_server.client.api_client import (
    get_database_players,
    get_database_sessions,
    get_database_chat,
    manage_user,
)


def create(session_state):
    """
    Create the Database tab with viewer and management interface.

    Args:
        session_state: Gradio State component for session tracking

    Returns:
        gr.Tab: Configured Database tab component
    """
    with gr.Tab("Database", visible=False) as database_tab:
        with gr.Column():
            gr.Markdown("### Database Viewer & User Management")
            gr.Markdown("*Admin and Superuser only*")

            # Players Table Section
            gr.Markdown("#### Players Table")
            with gr.Row():
                refresh_players_btn = gr.Button("Refresh Players", variant="secondary")
            players_display = gr.Textbox(
                label="Players Database",
                interactive=False,
                lines=20,
                max_lines=30,
            )

            # Sessions Table Section
            gr.Markdown("#### Active Sessions")
            with gr.Row():
                refresh_sessions_btn = gr.Button("Refresh Sessions", variant="secondary")
            sessions_display = gr.Textbox(
                label="Sessions Database",
                interactive=False,
                lines=15,
                max_lines=25,
            )

            # Chat Messages Section
            gr.Markdown("#### Chat Messages")
            with gr.Row():
                chat_limit_dropdown = gr.Dropdown(
                    choices=[50, 100, 200, 500],
                    value=100,
                    label="Message Limit",
                    scale=1,
                )
                refresh_chat_btn = gr.Button("Refresh Chat", variant="secondary", scale=1)
            chat_db_display = gr.Textbox(
                label="Chat Messages Database",
                interactive=False,
                lines=15,
                max_lines=25,
            )

            # User Management Section
            gr.Markdown("---")
            gr.Markdown("#### User Management")
            with gr.Row():
                target_username_input = gr.Textbox(
                    label="Target Username",
                    placeholder="Enter username to manage",
                    scale=2,
                )
                action_dropdown = gr.Dropdown(
                    choices=["change_role", "ban", "unban"],
                    label="Action",
                    scale=1,
                )
            with gr.Row():
                new_role_input = gr.Textbox(
                    label="New Role (for change_role only)",
                    placeholder="player, worldbuilder, admin, or superuser",
                    scale=2,
                )
                manage_user_btn = gr.Button("Execute Action", variant="primary", scale=1)

            management_output = gr.Textbox(
                label="Management Result",
                interactive=False,
                lines=5,
            )

            # Event handlers for Database tab
            refresh_players_btn.click(
                get_database_players,
                inputs=[session_state],
                outputs=[players_display],
            )

            refresh_sessions_btn.click(
                get_database_sessions,
                inputs=[session_state],
                outputs=[sessions_display],
            )

            def refresh_chat_with_limit(limit, session_st):
                """
                Refresh chat database view with configurable limit.

                Wrapper function that passes the limit dropdown value to
                get_database_chat(). Allows admin to view different amounts
                of chat history (50, 100, 200, or 500 messages).
                """
                return get_database_chat(limit, session_st)

            refresh_chat_btn.click(
                refresh_chat_with_limit,
                inputs=[chat_limit_dropdown, session_state],
                outputs=[chat_db_display],
            )

            def execute_manage_user(target, action, new_role, session_st):
                """
                Execute user management action and refresh displays.

                Calls manage_user() to perform the action (change_role, ban,
                unban), then automatically refreshes the players table to show
                the updated state. Also clears the input fields after execution.

                Returns:
                    Tuple for Gradio outputs: (result_message, refreshed_players,
                    clear_target_input, clear_role_input)
                """
                result = manage_user(target, action, new_role, session_st)
                # Also refresh players table after management action
                players = get_database_players(session_st)
                return result, players, "", ""

            manage_user_btn.click(
                execute_manage_user,
                inputs=[
                    target_username_input,
                    action_dropdown,
                    new_role_input,
                    session_state,
                ],
                outputs=[
                    management_output,
                    players_display,
                    target_username_input,
                    new_role_input,
                ],
            )

    return database_tab
