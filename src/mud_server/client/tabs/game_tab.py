"""
Game Tab for MUD Client.

This module provides the main gameplay interface with room view, chat,
status panel, movement controls, and auto-refresh functionality.
Visible only when logged in.
"""

import gradio as gr
from mud_server.client.api_client import send_command, refresh_display, get_status, logout


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
