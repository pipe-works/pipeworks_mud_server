"""
Game Tab for MUD Client.

This module provides the main gameplay interface with room view, chat,
status panel, movement controls, and auto-refresh functionality.
Visible only when logged in.

Migration Notes:
    - Migrated from old api_client.py to new modular structure
    - Uses GameAPIClient for game operations (send_command, get_chat, get_status, refresh_display)
    - Uses AuthAPIClient for logout
    - Wrapper functions extract session_id, username, and role from session_state
    - refresh_display returns dict with {"room": str, "chat": str} instead of tuple
    - All other functions return strings for Gradio display
"""

import gradio as gr

from mud_server.admin_gradio.api.auth import AuthAPIClient
from mud_server.admin_gradio.api.game import GameAPIClient

# Create module-level API client instances for reuse
_game_client = GameAPIClient()
_auth_client = AuthAPIClient()


def send_command(command: str, session_state: dict) -> str:
    """
    Send a game command to the backend for execution.

    Sends request to backend via GameAPIClient and returns command result.

    This function wraps the new GameAPIClient.send_command() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Args:
        command: Command string to execute
        session_state: User's session state dictionary containing session_id

    Returns:
        Command result string or error message

    Examples:
        >>> session = {"session_id": "abc123", "logged_in": True}
        >>> result = send_command("look", session)
        >>> isinstance(result, str)
        True
    """
    # Extract session_id from session state
    session_id = session_state.get("session_id")

    # Call the new API client
    api_result = _game_client.send_command(
        command=command,
        session_id=session_id,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def refresh_display(session_state: dict) -> tuple[str, str]:
    """
    Refresh both room and chat displays by fetching current data.

    Sends request to backend via GameAPIClient and returns room and chat data.

    This function wraps the new GameAPIClient.refresh_display() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Args:
        session_state: User's session state dictionary containing session_id

    Returns:
        Tuple of (room_description, chat_messages) both as strings

    Examples:
        >>> session = {"session_id": "abc123", "logged_in": True}
        >>> room, chat = refresh_display(session)
        >>> isinstance(room, str) and isinstance(chat, str)
        True
    """
    # Extract session_id from session state
    session_id = session_state.get("session_id")

    # Call the new API client
    api_result = _game_client.refresh_display(session_id=session_id)

    # Extract room and chat from data dict and return as tuple
    # New API returns dict with data["room"] and data["chat"]
    if api_result["success"] and api_result["data"]:
        room = api_result["data"]["room"]
        chat = api_result["data"]["chat"]
        return room, chat
    else:
        # Return error message if failed
        error_msg = api_result.get("message", "Failed to refresh display")
        return error_msg, ""


def get_status(session_state: dict) -> str:
    """
    Retrieve and format player status information.

    Sends request to backend via GameAPIClient and returns formatted status.

    This function wraps the new GameAPIClient.get_status() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Args:
        session_state: User's session state dictionary containing session_id, username, role

    Returns:
        Formatted status string

    Examples:
        >>> session = {"session_id": "abc123", "username": "alice", "role": "player", "logged_in": True}
        >>> result = get_status(session)
        >>> isinstance(result, str)
        True
    """
    # Extract session_id, username, and role from session state
    session_id = session_state.get("session_id")
    username = session_state.get("username", "Unknown")
    role = session_state.get("role", "player")

    # Call the new API client
    api_result = _game_client.get_status(
        session_id=session_id,
        username=username,
        role=role,
    )

    # Extract and return the message string for Gradio display
    return str(api_result["message"])


def logout(session_state: dict) -> tuple:
    """
    Handle user logout and return result tuple for Gradio.

    Sends logout request to backend via AuthAPIClient and returns result tuple
    matching the expected format from old api_client.

    This function wraps the new AuthAPIClient.logout() method to maintain
    compatibility with the Gradio interface while using the new modular API.

    Note: This function is called from game_tab but the full logout flow with
    tab visibility updates is handled in app.py's logout_and_hide_tabs() function.

    Args:
        session_state: User's session state dictionary containing session_id

    Returns:
        Tuple matching old API format for compatibility with app.py logout handler
        Format: (session_state, message, blank, ...)
        The app.py handler extracts result[1] for the message

    Examples:
        >>> session = {"session_id": "abc123", "logged_in": True}
        >>> result = logout(session)
        >>> isinstance(result, tuple) and len(result) >= 2
        True
    """
    # Extract session_id from session state
    session_id = session_state.get("session_id")

    # Call the new API client
    api_result = _auth_client.logout(session_id=session_id)

    # Clear session state (mimicking old behavior)
    session_state["session_id"] = None
    session_state["username"] = None
    session_state["role"] = None
    session_state["logged_in"] = False

    # Return tuple matching old format for compatibility
    # app.py's logout_and_hide_tabs() extracts result[1] (message)
    # and result[3:] for tab visibility updates
    # We return a simple tuple with session_state and message
    # The full tuple building is done in app.py using build_logged_out_state
    message = api_result["message"]

    # Return tuple in format expected by app.py: (session_state, message, blank, tabs...)
    # The tabs part is filled in by app.py's logout_and_hide_tabs function
    return (
        session_state,  # [0]
        message,  # [1]
        "",  # [2] blank field
        gr.update(visible=True),  # [3] login tab
        gr.update(visible=True),  # [4] register tab
        gr.update(visible=False),  # [5] game tab
        gr.update(visible=False),  # [6] settings tab
        gr.update(visible=False),  # [7] database tab
        gr.update(visible=False),  # [8] ollama tab
        gr.update(visible=False),  # [9] help tab
    )


def create(session_state):
    """
    Create the Game tab with full gameplay interface.

    Args:
        session_state: Gradio State component for session tracking

    Returns:
        tuple: (game_tab, logout_btn) - Tab component and logout button for top-level event wiring
    """
    with gr.Tab("Game", visible=False) as game_tab:
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### World")
                room_display = gr.Textbox(
                    label="Current Location",
                    interactive=False,
                    lines=15,
                    max_lines=20,
                )

            with gr.Column(scale=1):
                gr.Markdown("### Info")
                status_display = gr.Textbox(
                    label="Status", interactive=False, lines=15, max_lines=20
                )

        with gr.Row():
            gr.Markdown("### Chat")

        with gr.Row():
            chat_display = gr.Textbox(
                label="Room Chat",
                interactive=False,
                lines=8,
                max_lines=10,
            )

        with gr.Row():
            chat_input = gr.Textbox(
                label="Send Message",
                placeholder="Type: /say <message> (room only) or /yell <message> (adjoining rooms)",
                max_lines=1,
                scale=4,
            )
            send_btn = gr.Button("Send", variant="primary", scale=1)

        with gr.Row():
            gr.Markdown("### Movement & Actions")

        with gr.Row():
            north_btn = gr.Button("⬆️ North", scale=1)
            south_btn = gr.Button("⬇️ South", scale=1)
            east_btn = gr.Button("➡️ East", scale=1)
            west_btn = gr.Button("⬅️ West", scale=1)

        with gr.Row():
            look_btn = gr.Button("Look", scale=1)
            inventory_btn = gr.Button("Inventory", scale=1)
            who_btn = gr.Button("Who", scale=1)
            help_btn = gr.Button("Help", scale=1)

        with gr.Row():
            command_input = gr.Textbox(
                label="Command",
                placeholder="Type: /look, /get <item>, /north, /help (or use buttons above)",
                max_lines=1,
            )
            command_btn = gr.Button("Execute", variant="primary")

        with gr.Row():
            refresh_btn = gr.Button("Refresh Display", variant="secondary")
            logout_btn = gr.Button("Logout", variant="stop")

        # Auto-refresh timer (game clock)
        game_timer = gr.Timer(value=3.0, active=True)  # Refresh every 3 seconds

        # Command handlers
        def handle_command(cmd: str, session_st: dict):
            """
            Execute a command and refresh all displays.

            Used by action buttons (look, inventory, who, help) and
            the command input field. Sends command to backend, then
            refreshes room, chat, and status displays.

            Returns tuple for Gradio outputs: (command_result, room,
            chat, status, clear_chat_input)
            """
            result = send_command(cmd, session_st)
            room, chat = refresh_display(session_st)
            return result, room, chat, get_status(session_st), ""

        def handle_direction(direction: str, session_st: dict):
            """
            Handle directional movement and refresh displays.

            Used by directional buttons (North, South, East, West).
            Sends movement command to backend, then refreshes all displays.

            Returns tuple for Gradio outputs: (command_result, room,
            chat, status, clear_chat_input)
            """
            result = send_command(direction, session_st)
            room, chat = refresh_display(session_st)
            return result, room, chat, get_status(session_st), ""

        def handle_refresh(session_st: dict):
            """
            Manually refresh all game displays.

            Used by the "Refresh Display" button to force an immediate
            update of room, chat, and status without executing a command.

            Returns tuple for Gradio outputs: (room, chat, status)
            """
            room, chat = refresh_display(session_st)
            return room, chat, get_status(session_st)

        def handle_logout(session_st: dict):
            """
            Handle logout button click from game tab.

            Calls logout() and extracts message for display, clearing
            all game displays. Tab visibility changes are handled by
            separate logout_and_hide_tabs() function in main app.

            Returns tuple for Gradio outputs: (message, clear_room,
            clear_chat, clear_status, clear_chat_input)
            """
            result = logout(session_st)
            return result[1], "", "", "", ""  # return message only

        def auto_refresh(session_st: dict):
            """
            Auto-refresh game state on timer tick (every 3 seconds).

            Called automatically by the game_timer gr.Timer component.
            Only performs refresh if user is logged in to reduce server load.

            Returns:
                If logged in: tuple of (room, chat, status) with updated data
                If not logged in: tuple of gr.update() (no changes to UI)

            Note:
                This provides real-time visibility of other players' actions,
                chat messages, and world state changes.
            """
            if session_st.get("logged_in"):
                room, chat = refresh_display(session_st)
                return room, chat, get_status(session_st)
            return gr.update(), gr.update(), gr.update()  # No updates if not logged in

        def handle_send(msg: str, session_st: dict):
            """
            Handle sending a chat message or command from chat input.

            Used by the chat input field and "Send" button. Supports both
            chat commands (/say, /yell, /whisper) and regular game commands.
            Appends [SYSTEM] result to chat display for visibility.

            Args:
                msg: Message or command entered by user
                session_st: Session state dictionary

            Returns:
                Tuple for Gradio outputs: (clear_chat_input, command_result,
                room, chat_with_system_msg, status)

            Note:
                Empty messages are ignored (no updates sent to UI).
            """
            if not msg or not msg.strip():
                return (
                    "",
                    "",
                    gr.update(),
                    gr.update(),
                    gr.update(),
                )  # Don't update if empty
            result = send_command(msg, session_st)
            room, chat_msgs = refresh_display(session_st)

            # Append command result to chat for visibility
            chat_with_result = chat_msgs + f"\n[SYSTEM] {result}"

            return (
                "",
                result,
                room,
                chat_with_result,
                get_status(session_st),
            )  # Clear chat input, show result

        # Button click handlers
        north_btn.click(
            handle_direction,
            inputs=[gr.State("north"), session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )
        south_btn.click(
            handle_direction,
            inputs=[gr.State("south"), session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )
        east_btn.click(
            handle_direction,
            inputs=[gr.State("east"), session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )
        west_btn.click(
            handle_direction,
            inputs=[gr.State("west"), session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )

        look_btn.click(
            handle_command,
            inputs=[gr.State("look"), session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )
        inventory_btn.click(
            handle_command,
            inputs=[gr.State("inventory"), session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )
        who_btn.click(
            handle_command,
            inputs=[gr.State("who"), session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )
        help_btn.click(
            handle_command,
            inputs=[gr.State("help"), session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )

        command_btn.click(
            handle_command,
            inputs=[command_input, session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )

        send_btn.click(
            handle_send,
            inputs=[chat_input, session_state],
            outputs=[chat_input, command_input, room_display, chat_display, status_display],
        )

        # Also submit on Enter key in chat input
        chat_input.submit(
            handle_send,
            inputs=[chat_input, session_state],
            outputs=[chat_input, command_input, room_display, chat_display, status_display],
        )

        refresh_btn.click(
            handle_refresh,
            inputs=[session_state],
            outputs=[room_display, chat_display, status_display],
        )

        logout_btn.click(
            handle_logout,
            inputs=[session_state],
            outputs=[command_input, room_display, chat_display, status_display, chat_input],
        )

        # Wire up auto-refresh timer
        game_timer.tick(
            auto_refresh,
            inputs=[session_state],
            outputs=[room_display, chat_display, status_display],
        )

    return game_tab, logout_btn
