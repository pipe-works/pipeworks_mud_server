"""
API Client for MUD Server.

This module handles all HTTP communication with the FastAPI backend server.
It provides functions for authentication, game commands, admin operations,
and Ollama management.

All functions follow a consistent pattern:
    - Accept session_state dict for authentication
    - Return appropriate data or error messages
    - Handle connection errors gracefully

Configuration:
    SERVER_URL: Backend API server URL (can be overridden with MUD_SERVER_URL env var)
"""

import os
import gradio as gr
import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

# Backend API server URL (can be overridden with MUD_SERVER_URL env var)
SERVER_URL = os.getenv("MUD_SERVER_URL", "http://localhost:8000")


# ============================================================================
# AUTHENTICATION FUNCTIONS
# ============================================================================


def login(username: str, password: str, session_state: dict):
    """
    Handle user login with password authentication.

    Sends credentials to backend, stores session data on success, and returns
    updated UI state for tab visibility and user info display.

    Args:
        username: Username to login with
        password: Plain text password
        session_state: User's session state dictionary

    Returns:
        Tuple of (session_state, login_result, clear_username, clear_password,
                  login_tab, register_tab, game_tab, settings_tab, db_tab, ollama_tab, help_tab)
    """
    if not username or len(username.strip()) < 2:
        return (
            session_state,
            "Username must be at least 2 characters.",
            "",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # ollama tab
            gr.update(visible=False),  # help tab
        )

    if not password:
        return (
            session_state,
            "Password is required.",
            "",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # ollama tab
            gr.update(visible=False),  # help tab
        )

    try:
        response = requests.post(
            f"{SERVER_URL}/login",
            json={"username": username.strip(), "password": password},
        )

        if response.status_code == 200:
            data = response.json()
            session_state["session_id"] = data["session_id"]
            session_state["username"] = username.strip()
            session_state["role"] = data.get("role", "player")
            session_state["logged_in"] = True

            # Determine if user has admin/superuser access
            has_admin_access = session_state["role"] in ["admin", "superuser"]

            return (
                session_state,
                data["message"],
                "",
                "",
                gr.update(visible=True),  # login tab (keep visible for logout message)
                gr.update(visible=False),  # register tab (hide after login)
                gr.update(visible=True),  # game tab
                gr.update(visible=True),  # settings tab
                gr.update(visible=has_admin_access),  # database tab (admin/superuser only)
                gr.update(visible=has_admin_access),  # ollama tab (admin/superuser only)
                gr.update(visible=True),  # help tab
            )
        else:
            error = response.json().get("detail", "Login failed")
            return (
                session_state,
                f"Login failed: {error}",
                "",
                "",
                gr.update(visible=True),  # login tab
                gr.update(visible=True),  # register tab
                gr.update(visible=False),  # game tab
                gr.update(visible=False),  # settings tab
                gr.update(visible=False),  # database tab
                gr.update(visible=False),  # ollama tab
                gr.update(visible=False),  # help tab
            )

    except requests.exceptions.ConnectionError:
        return (
            session_state,
            f"Cannot connect to server at {SERVER_URL}",
            "",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # ollama tab
            gr.update(visible=False),  # help tab
        )
    except Exception as e:
        return (
            session_state,
            f"Error: {str(e)}",
            "",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # ollama tab
            gr.update(visible=False),  # help tab
        )


def register(username: str, password: str, password_confirm: str) -> str:
    """
    Handle new user account registration.

    Validates input, sends registration request to backend API, and returns
    status message indicating success or failure.

    Args:
        username: Desired username for new account
        password: Plain text password for new account
        password_confirm: Password confirmation (must match password)

    Returns:
        String message indicating registration success or failure
    """
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


def logout(session_state: dict):
    """
    Handle user logout and clean up session state.

    Sends logout request to backend API, clears session data from memory,
    and returns updated UI state with tabs hidden.

    Args:
        session_state: User's session state dictionary

    Returns:
        Tuple of (session_state, message, blank, login_tab_visible,
                  register_tab_visible, game_tab_hidden, settings_tab_hidden,
                  db_tab_hidden, ollama_tab_hidden, help_tab_hidden)
    """
    if not session_state.get("logged_in"):
        return (
            session_state,
            "Not logged in.",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # ollama tab
            gr.update(visible=False),  # help tab
        )

    try:
        requests.post(
            f"{SERVER_URL}/logout",
            json={"session_id": session_state.get("session_id"), "command": "logout"},
        )

        session_state["session_id"] = None
        session_state["username"] = None
        session_state["role"] = None
        session_state["logged_in"] = False

        return (
            session_state,
            "You have been logged out.",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # ollama tab
            gr.update(visible=False),  # help tab
        )

    except Exception as e:
        return (
            session_state,
            f"Error: {str(e)}",
            "",
            gr.update(visible=True),  # login tab
            gr.update(visible=True),  # register tab
            gr.update(visible=False),  # game tab
            gr.update(visible=False),  # settings tab
            gr.update(visible=False),  # database tab
            gr.update(visible=False),  # ollama tab
            gr.update(visible=False),  # help tab
        )


# ============================================================================
# GAME FUNCTIONS
# ============================================================================


def send_command(command: str, session_state: dict) -> str:
    """
    Send a game command to the backend API for execution.

    Args:
        command: Command string to execute
        session_state: User's session state dictionary

    Returns:
        String message with command result
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    if not command or not command.strip():
        return "Enter a command."

    try:
        response = requests.post(
            f"{SERVER_URL}/command",
            json={"session_id": session_state.get("session_id"), "command": command},
        )

        if response.status_code == 200:
            data = response.json()
            return str(data["message"])
        elif response.status_code == 401:
            session_state["logged_in"] = False
            return "Session expired. Please log in again."
        else:
            error = response.json().get("detail", "Command failed")
            return f"Error: {error}"

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}"
    except Exception as e:
        return f"Error: {str(e)}"


def get_chat(session_state: dict) -> str:
    """
    Retrieve recent chat messages from the current room.

    Args:
        session_state: User's session state dictionary

    Returns:
        String with formatted chat messages
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    try:
        response = requests.get(f"{SERVER_URL}/chat/{session_state.get('session_id')}")

        if response.status_code == 200:
            data = response.json()
            return str(data["chat"])
        else:
            return "Failed to retrieve chat."

    except Exception as e:
        return f"Error: {str(e)}"


def get_status(session_state: dict) -> str:
    """
    Retrieve and format player status information.

    Args:
        session_state: User's session state dictionary

    Returns:
        Formatted multi-line string with complete player status
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    try:
        response = requests.get(f"{SERVER_URL}/status/{session_state.get('session_id')}")

        if response.status_code == 200:
            data = response.json()
            role_display = session_state.get("role", "player").capitalize()
            status = f"""
[Player Status]
Username: {session_state.get('username')}
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


def refresh_display(session_state: dict) -> tuple[str, str]:
    """
    Refresh both room and chat displays by fetching current data.

    Args:
        session_state: User's session state dictionary

    Returns:
        Tuple of (room_description, chat_messages)
    """
    if not session_state.get("logged_in"):
        return "Not logged in.", ""

    room_info = send_command("look", session_state)
    chat_info = get_chat(session_state)

    return room_info, chat_info


# ============================================================================
# SETTINGS FUNCTIONS
# ============================================================================


def change_password(
    old_password: str, new_password: str, confirm_password: str, session_state: dict
) -> str:
    """
    Change the current user's password.

    Args:
        old_password: Current password (for verification)
        new_password: Desired new password
        confirm_password: New password confirmation
        session_state: User's session state dictionary

    Returns:
        Status message string
    """
    if not session_state.get("logged_in"):
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
                "session_id": session_state.get("session_id"),
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


def stop_server(session_state: dict) -> str:
    """
    Stop the backend server (Admin/Superuser only).

    Args:
        session_state: User's session state dictionary

    Returns:
        Status message string
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    role = session_state.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    try:
        response = requests.post(
            f"{SERVER_URL}/admin/server/stop",
            json={"session_id": session_state.get("session_id")},
        )

        if response.status_code == 200:
            data = response.json()
            return f"✅ {data['message']}"
        elif response.status_code == 403:
            return "Access Denied: Insufficient permissions."
        else:
            error = response.json().get("detail", "Failed to stop server")
            return f"❌ {error}"

    except requests.exceptions.ConnectionError:
        return f"Server stopped or cannot connect to {SERVER_URL}"
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================================================
# ADMIN DATABASE FUNCTIONS
# ============================================================================


def get_database_players(session_state: dict) -> str:
    """
    Fetch and format all players from database (Admin/Superuser only).

    Args:
        session_state: User's session state dictionary

    Returns:
        Formatted multi-line string with all player records
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    role = session_state.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    try:
        response = requests.get(
            f"{SERVER_URL}/admin/database/players",
            params={"session_id": session_state.get("session_id")},
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


def get_database_sessions(session_state: dict) -> str:
    """
    Fetch and format all active sessions from database (Admin/Superuser only).

    Args:
        session_state: User's session state dictionary

    Returns:
        Formatted multi-line string with all session records
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    role = session_state.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    try:
        response = requests.get(
            f"{SERVER_URL}/admin/database/sessions",
            params={"session_id": session_state.get("session_id")},
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


def get_database_chat(limit: int, session_state: dict) -> str:
    """
    Fetch and format recent chat messages from database (Admin/Superuser only).

    Args:
        limit: Maximum number of messages to retrieve
        session_state: User's session state dictionary

    Returns:
        Formatted multi-line string with recent chat messages
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    role = session_state.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    try:
        response = requests.get(
            f"{SERVER_URL}/admin/database/chat-messages",
            params={"session_id": session_state.get("session_id"), "limit": limit},
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


def manage_user(target_username: str, action: str, new_role: str, session_state: dict) -> str:
    """
    Perform user management actions (Admin/Superuser only).

    Args:
        target_username: Username of user to manage
        action: Action to perform (change_role, ban, unban)
        new_role: New role for change_role action
        session_state: User's session state dictionary

    Returns:
        Status message string
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    role = session_state.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    if not target_username or not target_username.strip():
        return "Target username is required."

    if not action:
        return "Action is required."

    try:
        request_data = {
            "session_id": session_state.get("session_id"),
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


# ============================================================================
# OLLAMA MANAGEMENT FUNCTIONS
# ============================================================================


def execute_ollama_command(server_url: str, command: str, session_state: dict) -> str:
    """
    Execute an Ollama command on the specified server (Admin/Superuser only).

    Args:
        server_url: URL of the Ollama server
        command: Ollama command to execute
        session_state: User's session state dictionary

    Returns:
        Command output or error message
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    role = session_state.get("role", "player")
    if role not in ["admin", "superuser"]:
        return "Access Denied: Admin or Superuser role required."

    if not server_url or not server_url.strip():
        return "Server URL is required."

    if not command or not command.strip():
        return "Command is required."

    try:
        response = requests.post(
            f"{SERVER_URL}/admin/ollama/command",
            json={
                "session_id": session_state.get("session_id"),
                "server_url": server_url.strip(),
                "command": command.strip(),
            },
            timeout=300,  # 5 minute timeout for long operations like pull
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("output", "No output returned")
        elif response.status_code == 403:
            return "Access Denied: Insufficient permissions."
        else:
            error = response.json().get("detail", "Command execution failed")
            return f"Error: {error}"

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to server at {SERVER_URL}"
    except requests.exceptions.Timeout:
        return "Request timed out. Long operations like 'pull' may still be running. Check 'ps' to verify."
    except Exception as e:
        return f"Error: {str(e)}"
