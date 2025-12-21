"""Gradio frontend client for the MUD."""

import gradio as gr
import requests
import json
from typing import Optional, Tuple
import os

# Configuration
SERVER_URL = os.getenv("MUD_SERVER_URL", "http://localhost:8000")

# Global state
session_data = {"session_id": None, "username": None, "role": None, "logged_in": False}


def login(username: str, password: str):
    """Handle login with password and update tab visibility."""
    if not username or len(username.strip()) < 2:
        return (
            "Username must be at least 2 characters.",
            "",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # help tab
        )

    if not password:
        return (
            "Password is required.",
            "",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # help tab
        )

    try:
        response = requests.post(
            f"{SERVER_URL}/login",
            json={"username": username.strip(), "password": password},
        )

        if response.status_code == 200:
            data = response.json()
            session_data["session_id"] = data["session_id"]
            session_data["username"] = username.strip()
            session_data["role"] = data.get("role", "player")
            session_data["logged_in"] = True

            # Determine if user has admin/superuser access
            has_admin_access = session_data["role"] in ["admin", "superuser"]

            return (
                data["message"],
                "",
                "",
                gr.update(visible=True),  # login tab (keep visible for logout message)
                gr.update(visible=False),  # register tab (hide after login)
                gr.update(visible=True),  # game tab
                gr.update(visible=True),  # settings tab
                gr.update(visible=has_admin_access),  # database tab (admin/superuser only)
                gr.update(visible=True),  # help tab
            )
        else:
            error = response.json().get("detail", "Login failed")
            return (
                f"Login failed: {error}",
                "",
                "",
                gr.update(visible=True),  # login tab
                gr.update(visible=True),  # register tab
                gr.update(visible=False),  # game tab
                gr.update(visible=False),  # settings tab
                gr.update(visible=False),  # database tab
                gr.update(visible=False),  # help tab
            )

    except requests.exceptions.ConnectionError:
        return (
            f"Cannot connect to server at {SERVER_URL}",
            "",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # help tab
        )
    except Exception as e:
        return (
            f"Error: {str(e)}",
            "",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # help tab
        )


def register(username: str, password: str, password_confirm: str) -> str:
    """Handle user registration."""
    if not username or len(username.strip()) < 2:
        return "Username must be at least 2 characters."

    if len(password) < 8:
        return "Password must be at least 8 characters."

    if password != password_confirm:
        return "Passwords do not match."

    try:
        response = requests.post(
            f"{SERVER_URL}/register",
            json={
                "username": username.strip(),
                "password": password,
                "password_confirm": password_confirm,
            },
        )

        if response.status_code == 200:
            data = response.json()
            return f"✅ {data['message']}\n\nYou can now login with your credentials."
        else:
            error = response.json().get("detail", "Registration failed")
            return f"Registration failed: {error}"

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}"
    except Exception as e:
        return f"Error: {str(e)}"


def logout():
    """Handle logout and reset tab visibility."""
    if not session_data["logged_in"]:
        return (
            "Not logged in.",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # help tab
        )

    try:
        response = requests.post(
            f"{SERVER_URL}/logout",
            json={"session_id": session_data["session_id"], "command": "logout"},
        )

        session_data["session_id"] = None
        session_data["username"] = None
        session_data["role"] = None
        session_data["logged_in"] = False

        return (
            "You have been logged out.",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # help tab
        )

    except Exception as e:
        return (
            f"Error: {str(e)}",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # help tab
        )


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
            role_display = session_data.get('role', 'player').capitalize()
            status = f"""
[Player Status]
Username: {session_data['username']}
Role: {role_display}
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


def change_password(old_password: str, new_password: str, confirm_password: str) -> str:
    """Change user password."""
    if not session_data["logged_in"]:
        return "You are not logged in."

    if not old_password:
        return "Current password is required."

    if not new_password or len(new_password) < 8:
        return "New password must be at least 8 characters."

    if new_password != confirm_password:
        return "New passwords do not match."

    if old_password == new_password:
        return "New password must be different from current password."

    try:
        response = requests.post(
            f"{SERVER_URL}/change-password",
            json={
                "session_id": session_data["session_id"],
                "old_password": old_password,
                "new_password": new_password,
            },
        )

        if response.status_code == 200:
            data = response.json()
            return f"✅ {data['message']}"
        else:
            error = response.json().get("detail", "Failed to change password")
            return f"❌ {error}"

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}"
    except Exception as e:
        return f"Error: {str(e)}"


def get_database_players() -> str:
    """Fetch and format players table for display (Admin only)."""
    if not session_data["logged_in"]:
        return "You are not logged in."

    role = session_data.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    try:
        response = requests.get(
            f"{SERVER_URL}/admin/database/players",
            params={"session_id": session_data["session_id"]},
        )

        if response.status_code == 200:
            data = response.json()
            players = data["players"]

            if not players:
                return "No players found in database."

            # Format as text table
            output = [f"=== PLAYERS TABLE ({len(players)} records) ===\n"]
            for player in players:
                status = "ACTIVE" if player["is_active"] else "BANNED"
                output.append(f"ID: {player['id']}")
                output.append(f"  Username: {player['username']}")
                output.append(f"  Role: {player['role']}")
                output.append(f"  Status: {status}")
                output.append(f"  Room: {player['current_room']}")
                output.append(f"  Inventory: {player['inventory']}")
                output.append(f"  Created: {player['created_at']}")
                output.append(f"  Last Login: {player['last_login']}")
                output.append(f"  Password Hash: {player['password_hash']}")
                output.append("")

            return "\n".join(output)

        elif response.status_code == 403:
            return "Access Denied: Insufficient permissions."
        else:
            error = response.json().get("detail", "Failed to fetch players")
            return f"Error: {error}"

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}"
    except Exception as e:
        return f"Error: {str(e)}"


def get_database_sessions() -> str:
    """Fetch and format sessions table for display (Admin only)."""
    if not session_data["logged_in"]:
        return "You are not logged in."

    role = session_data.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    try:
        response = requests.get(
            f"{SERVER_URL}/admin/database/sessions",
            params={"session_id": session_data["session_id"]},
        )

        if response.status_code == 200:
            data = response.json()
            sessions = data["sessions"]

            if not sessions:
                return "No active sessions in database."

            # Format as text table
            output = [f"=== SESSIONS TABLE ({len(sessions)} records) ===\n"]
            for session in sessions:
                output.append(f"ID: {session['id']}")
                output.append(f"  Username: {session['username']}")
                output.append(f"  Session ID: {session['session_id']}")
                output.append(f"  Connected: {session['connected_at']}")
                output.append(f"  Last Activity: {session['last_activity']}")
                output.append("")

            return "\n".join(output)

        elif response.status_code == 403:
            return "Access Denied: Insufficient permissions."
        else:
            error = response.json().get("detail", "Failed to fetch sessions")
            return f"Error: {error}"

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}"
    except Exception as e:
        return f"Error: {str(e)}"


def get_database_chat(limit: int = 100) -> str:
    """Fetch and format chat messages for display (Admin only)."""
    if not session_data["logged_in"]:
        return "You are not logged in."

    role = session_data.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    try:
        response = requests.get(
            f"{SERVER_URL}/admin/database/chat-messages",
            params={"session_id": session_data["session_id"], "limit": limit},
        )

        if response.status_code == 200:
            data = response.json()
            messages = data["messages"]

            if not messages:
                return "No chat messages in database."

            # Format as text table (reverse order to show newest first)
            output = [f"=== CHAT MESSAGES ({len(messages)} recent messages) ===\n"]
            for msg in messages:
                output.append(f"ID: {msg['id']} | Room: {msg['room']} | Time: {msg['timestamp']}")
                output.append(f"  [{msg['username']}]: {msg['message']}")
                output.append("")

            return "\n".join(output)

        elif response.status_code == 403:
            return "Access Denied: Insufficient permissions."
        else:
            error = response.json().get("detail", "Failed to fetch chat messages")
            return f"Error: {error}"

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}"
    except Exception as e:
        return f"Error: {str(e)}"


def manage_user(target_username: str, action: str, new_role: str = "") -> str:
    """Perform user management action (Admin only)."""
    if not session_data["logged_in"]:
        return "You are not logged in."

    role = session_data.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    if not target_username or not target_username.strip():
        return "Target username is required."

    if not action:
        return "Action is required."

    try:
        request_data = {
            "session_id": session_data["session_id"],
            "target_username": target_username.strip(),
            "action": action,
        }

        if action == "change_role":
            if not new_role or not new_role.strip():
                return "New role is required for change_role action."
            request_data["new_role"] = new_role.strip().lower()

        response = requests.post(
            f"{SERVER_URL}/admin/user/manage",
            json=request_data,
        )

        if response.status_code == 200:
            data = response.json()
            return f"✅ {data['message']}"
        else:
            error = response.json().get("detail", "Failed to manage user")
            return f"❌ {error}"

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}"
    except Exception as e:
        return f"Error: {str(e)}"


# Create Gradio interface
def create_interface():
    """Create the Gradio interface."""

    with gr.Blocks(title="MUD Client", theme=gr.themes.Soft()) as interface:
        gr.Markdown("# MUD Client")
        gr.Markdown("A simple Multi-User Dungeon client")

        with gr.Tabs():
            # Login Tab (always visible)
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
                    login_output = gr.Textbox(
                        label="Login Status", interactive=False, lines=10
                    )

            # Register Tab (visible only when not logged in)
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

                    register_btn.click(
                        register,
                        inputs=[
                            register_username_input,
                            register_password_input,
                            register_password_confirm_input,
                        ],
                        outputs=[register_output],
                    )

            # Game Tab (visible only when logged in)
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

            # Settings Tab (visible only when logged in)
            with gr.Tab("Settings", visible=False) as settings_tab:
                with gr.Column():
                    gr.Markdown("### Change Password")
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
                    change_password_output = gr.Textbox(
                        label="Status", interactive=False, lines=5
                    )

                    change_password_btn.click(
                        change_password,
                        inputs=[
                            current_password_input,
                            new_password_input,
                            confirm_new_password_input,
                        ],
                        outputs=[change_password_output],
                    )

            # Database Tab (visible only for admin/superuser)
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
                        outputs=[players_display],
                    )

                    refresh_sessions_btn.click(
                        get_database_sessions,
                        outputs=[sessions_display],
                    )

                    def refresh_chat_with_limit(limit):
                        return get_database_chat(limit)

                    refresh_chat_btn.click(
                        refresh_chat_with_limit,
                        inputs=[chat_limit_dropdown],
                        outputs=[chat_db_display],
                    )

                    def execute_manage_user(target, action, new_role):
                        result = manage_user(target, action, new_role)
                        # Also refresh players table after management action
                        players = get_database_players()
                        return result, players, "", ""

                    manage_user_btn.click(
                        execute_manage_user,
                        inputs=[target_username_input, action_dropdown, new_role_input],
                        outputs=[management_output, players_display, target_username_input, new_role_input],
                    )

            # Help Tab (visible only when logged in)
            with gr.Tab("Help", visible=False) as help_tab:
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

        # Wire up login event handler
        login_btn.click(
            login,
            inputs=[login_username_input, login_password_input],
            outputs=[
                login_output,
                login_username_input,
                login_password_input,
                login_tab,
                register_tab,
                game_tab,
                settings_tab,
                database_tab,
                help_tab,
            ],
        )

        # Wire up logout button to update tab visibility
        # This needs to be separate from the Game tab handler because tabs aren't defined yet there
        def logout_and_hide_tabs():
            result = logout()
            return result[0], result[2], result[3], result[4], result[5], result[6], result[7]

        logout_btn.click(
            logout_and_hide_tabs,
            outputs=[
                login_output,
                login_tab,
                register_tab,
                game_tab,
                settings_tab,
                database_tab,
                help_tab,
            ],
        )

    return interface


if __name__ == "__main__":
    interface = create_interface()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )
