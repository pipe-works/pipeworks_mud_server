"""
Database Tab for MUD Client.

This module provides the database viewer and user management interface.
Visible only for admin and superuser roles.

Migration Notes:
    - Migrated from old api_client.py to new modular structure
    - Uses AdminAPIClient for all database operations
    - Wrapper functions extract session_id and role from session_state
    - Returns message string for Gradio display
    - Parameter order changed: session_id and role now come first
"""

import gradio as gr

from mud_server.admin_gradio.api.admin import AdminAPIClient

# Create module-level API client instance for reuse
_admin_client = AdminAPIClient()


def get_database_players(session_state: dict) -> str:
    """
    Fetch and format all players from database (Admin/Superuser only).

    Sends request to backend via AdminAPIClient and returns formatted player table.

    This function wraps the new AdminAPIClient.get_database_players() method to
    maintain compatibility with the Gradio interface while using the new modular API.

    Args:
        session_state: User's session state dictionary containing session_id and role

    Returns:
        Formatted multi-line string with player database contents

    Examples:
        >>> session = {"session_id": "admin123", "role": "admin", "logged_in": True}
        >>> result = get_database_players(session)
        >>> isinstance(result, str)
        True
    """
    # Extract session_id and role from session state
    session_id = session_state.get("session_id")
    role = session_state.get("role", "player")

    # Call the new API client
    api_result = _admin_client.get_database_players(
        session_id=session_id,
        role=role,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def get_database_sessions(session_state: dict) -> str:
    """
    Fetch and format all active sessions from database (Admin/Superuser only).

    Sends request to backend via AdminAPIClient and returns formatted sessions table.

    This function wraps the new AdminAPIClient.get_database_sessions() method to
    maintain compatibility with the Gradio interface while using the new modular API.

    Args:
        session_state: User's session state dictionary containing session_id and role

    Returns:
        Formatted multi-line string with sessions database contents

    Examples:
        >>> session = {"session_id": "admin123", "role": "admin", "logged_in": True}
        >>> result = get_database_sessions(session)
        >>> isinstance(result, str)
        True
    """
    # Extract session_id and role from session state
    session_id = session_state.get("session_id")
    role = session_state.get("role", "player")

    # Call the new API client
    api_result = _admin_client.get_database_sessions(
        session_id=session_id,
        role=role,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def get_database_chat(limit: int, session_state: dict) -> str:
    """
    Fetch and format recent chat messages from database (Admin/Superuser only).

    Sends request to backend via AdminAPIClient and returns formatted chat history.

    This function wraps the new AdminAPIClient.get_database_chat() method to
    maintain compatibility with the Gradio interface while using the new modular API.

    Note: Parameter order is maintained from old API (limit, session_state) for
    compatibility with existing Gradio event handlers.

    Args:
        limit: Maximum number of messages to retrieve
        session_state: User's session state dictionary containing session_id and role

    Returns:
        Formatted multi-line string with recent chat messages

    Examples:
        >>> session = {"session_id": "admin123", "role": "admin", "logged_in": True}
        >>> result = get_database_chat(100, session)
        >>> isinstance(result, str)
        True
    """
    # Extract session_id and role from session state
    session_id = session_state.get("session_id")
    role = session_state.get("role", "player")

    # Call the new API client
    # Note: New API has different parameter order (session_id, role, limit)
    api_result = _admin_client.get_database_chat(
        session_id=session_id,
        role=role,
        limit=limit,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def manage_user(target_username: str, action: str, new_role: str, session_state: dict) -> str:
    """
    Perform user management actions (Admin/Superuser only).

    Supported actions:
    - change_role: Change user's role (requires new_role parameter)
    - ban: Ban/deactivate user account
    - unban: Unban/reactivate user account

    Sends request to backend via AdminAPIClient and returns result message.

    This function wraps the new AdminAPIClient.manage_user() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Note: Parameter order is maintained from old API for compatibility with
    existing Gradio event handlers.

    Args:
        target_username: Username of user to manage
        action: Action to perform (change_role, ban, unban)
        new_role: New role for change_role action (empty string if not applicable)
        session_state: User's session state dictionary containing session_id and role

    Returns:
        Status message string indicating success or failure

    Examples:
        >>> session = {"session_id": "admin123", "role": "admin", "logged_in": True}
        >>> result = manage_user("alice", "change_role", "worldbuilder", session)
        >>> isinstance(result, str)
        True
    """
    # Extract session_id and role from session state
    session_id = session_state.get("session_id")
    role = session_state.get("role", "player")

    # Call the new API client
    # Note: New API has different parameter order (session_id, role, target, action, new_role)
    api_result = _admin_client.manage_user(
        session_id=session_id,
        role=role,
        target_username=target_username,
        action=action,
        new_role=new_role,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


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
