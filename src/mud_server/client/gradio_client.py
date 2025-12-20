"""Gradio frontend client for the MUD."""

import gradio as gr
import requests
import json
from typing import Optional, Tuple
import os

# Configuration
SERVER_URL = os.getenv("MUD_SERVER_URL", "http://localhost:8000")

# Global state
session_data = {"session_id": None, "username": None, "logged_in": False}


def login(username: str) -> Tuple[str, str, bool]:
    """Handle login."""
    if not username or len(username.strip()) < 2:
        return "Username must be at least 2 characters.", "", False

    try:
        response = requests.post(
            f"{SERVER_URL}/login", json={"username": username.strip()}
        )

        if response.status_code == 200:
            data = response.json()
            session_data["session_id"] = data["session_id"]
            session_data["username"] = username.strip()
            session_data["logged_in"] = True

            return data["message"], "", True
        else:
            error = response.json().get("detail", "Login failed")
            return f"Login failed: {error}", "", False

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}", "", False
    except Exception as e:
        return f"Error: {str(e)}", "", False


def logout() -> Tuple[str, str, bool]:
    """Handle logout."""
    if not session_data["logged_in"]:
        return "Not logged in.", "", False

    try:
        response = requests.post(
            f"{SERVER_URL}/logout",
            json={"session_id": session_data["session_id"], "command": "logout"},
        )

        session_data["session_id"] = None
        session_data["username"] = None
        session_data["logged_in"] = False

        return "You have been logged out.", "", False

    except Exception as e:
        return f"Error: {str(e)}", "", False


def send_command(command: str) -> str:
    """Send a command to the server."""
    if not session_data["logged_in"]:
        return "You are not logged in."

    if not command or not command.strip():
        return "Enter a command."

    try:
        response = requests.post(
            f"{SERVER_URL}/command",
            json={"session_id": session_data["session_id"], "command": command},
        )

        if response.status_code == 200:
            data = response.json()
            return data["message"]
        elif response.status_code == 401:
            session_data["logged_in"] = False
            return "Session expired. Please log in again."
        else:
            error = response.json().get("detail", "Command failed")
            return f"Error: {error}"

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}"
    except Exception as e:
        return f"Error: {str(e)}"


def get_chat() -> str:
    """Get recent chat messages."""
    if not session_data["logged_in"]:
        return "You are not logged in."

    try:
        response = requests.get(
            f"{SERVER_URL}/chat/{session_data['session_id']}"
        )

        if response.status_code == 200:
            data = response.json()
            return data["chat"]
        else:
            return "Failed to retrieve chat."

    except Exception as e:
        return f"Error: {str(e)}"


def get_status() -> str:
    """Get player status."""
    if not session_data["logged_in"]:
        return "You are not logged in."

    try:
        response = requests.get(
            f"{SERVER_URL}/status/{session_data['session_id']}"
        )

        if response.status_code == 200:
            data = response.json()
            status = f"""
[Player Status]
Username: {session_data['username']}
Current Room: {data['current_room']}
Active Players: {', '.join(data['active_players']) if data['active_players'] else 'None'}

{data['inventory']}
            """
            return status.strip()
        else:
            return "Failed to retrieve status."

    except Exception as e:
        return f"Error: {str(e)}"


def refresh_display() -> Tuple[str, str]:
    """Refresh the display with current room and chat."""
    if not session_data["logged_in"]:
        return "Not logged in.", ""

    room_info = send_command("look")
    chat_info = get_chat()

    return room_info, chat_info


# Create Gradio interface
def create_interface():
    """Create the Gradio interface."""

    with gr.Blocks(title="MUD Client", theme=gr.themes.Soft()) as interface:
        gr.Markdown("# MUD Client")
        gr.Markdown("A simple Multi-User Dungeon client")

        with gr.Tabs():
            # Login Tab
            with gr.Tab("Login"):
                with gr.Column():
                    username_input = gr.Textbox(
                        label="Username",
                        placeholder="Enter your username",
                        max_lines=1,
                    )
                    login_btn = gr.Button("Login", variant="primary")
                    login_output = gr.Textbox(
                        label="Login Status", interactive=False, lines=10
                    )

                    login_btn.click(
                        login,
                        inputs=[username_input],
                        outputs=[login_output, username_input, gr.State(False)],
                    )

            # Game Tab
            with gr.Tab("Game"):
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
                        placeholder="Type 'say <message>' or 'chat <message>'",
                        max_lines=1,
                    )

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
                        placeholder="Enter a command (or use buttons above)",
                        max_lines=1,
                    )
                    command_btn = gr.Button("Execute", variant="primary")

                with gr.Row():
                    refresh_btn = gr.Button("Refresh Display", variant="secondary")
                    logout_btn = gr.Button("Logout", variant="stop")

                # Command handlers
                def handle_command(cmd: str):
                    result = send_command(cmd)
                    room, chat = refresh_display()
                    return result, room, chat, get_status(), ""

                def handle_direction(direction: str):
                    result = send_command(direction)
                    room, chat = refresh_display()
                    return result, room, chat, get_status(), ""

                def handle_refresh():
                    room, chat = refresh_display()
                    return room, chat, get_status()

                def handle_logout():
                    logout()
                    return "Logged out.", "", "", "", ""

                # Button click handlers
                north_btn.click(
                    handle_direction,
                    inputs=[gr.State("north")],
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )
                south_btn.click(
                    handle_direction,
                    inputs=[gr.State("south")],
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )
                east_btn.click(
                    handle_direction,
                    inputs=[gr.State("east")],
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )
                west_btn.click(
                    handle_direction,
                    inputs=[gr.State("west")],
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )

                look_btn.click(
                    handle_command,
                    inputs=[gr.State("look")],
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )
                inventory_btn.click(
                    handle_command,
                    inputs=[gr.State("inventory")],
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )
                who_btn.click(
                    handle_command,
                    inputs=[gr.State("who")],
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )
                help_btn.click(
                    handle_command,
                    inputs=[gr.State("help")],
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )

                command_btn.click(
                    handle_command,
                    inputs=[command_input],
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )

                refresh_btn.click(
                    handle_refresh,
                    outputs=[room_display, chat_display, status_display],
                )

                logout_btn.click(
                    handle_logout,
                    outputs=[command_input, room_display, chat_display, status_display, chat_input],
                )

            # Help Tab
            with gr.Tab("Help"):
                gr.Markdown("""
# MUD Client Help

## Getting Started
1. Enter your username in the Login tab
2. Click Login to create an account or log in
3. Navigate to the Game tab to start playing

## Commands
- **Movement**: Use the arrow buttons or type `north`, `south`, `east`, `west` (or `n`, `s`, `e`, `w`)
- **Look**: View your current location
- **Inventory**: Check your items
- **Get/Take**: Pick up an item (`get torch`)
- **Drop**: Drop an item from your inventory
- **Say/Chat**: Send a message to the room
- **Who**: See who else is online
- **Help**: Display help information

## World
The world consists of a central spawn zone with 4 cardinal directions:
- **North**: Enchanted Forest
- **South**: Golden Desert
- **East**: Snow-Capped Mountain
- **West**: Crystalline Lake

Each zone contains items you can collect.

## Tips
- Use the Refresh Display button to update your view
- Chat messages are visible to all players in the same room
- You can pick up items and carry them in your inventory
                """)

    return interface


if __name__ == "__main__":
    interface = create_interface()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )
