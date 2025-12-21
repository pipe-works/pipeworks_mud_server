"""
Gradio-based web client for the MUD server.

This module provides the web-based user interface for the MUD game using Gradio.
It creates a multi-tab interface with separate views for login, registration,
gameplay, settings, and admin functions.

Interface Structure:
    Tab 1: Login - User authentication
    Tab 2: Register - New account creation
    Tab 3: Game - Main gameplay interface with auto-refresh
    Tab 4: Settings - Password change and server control (admin only)
    Tab 5: Database - Admin database viewer (admin only)
    Tab 6: Help - Game instructions and command reference

Key Features:
    - Per-user session state using gr.State (prevents cross-user contamination)
    - Auto-refresh timer (3 seconds) for real-time game updates
    - Role-based UI elements (admin features hidden for regular players)
    - Chat system with support for say, yell, and whisper commands
    - Inventory and player status display
    - Admin database viewer for players, sessions, and chat logs

State Management:
    Each user has their own gr.State dictionary containing:
    - session_id: UUID from successful login
    - username: Player's username
    - role: User role (player, worldbuilder, admin, superuser)
    - logged_in: Boolean login status

    IMPORTANT: All functions must accept and return session_state to maintain
    per-user state isolation. Never use global variables for session data.

API Communication:
    All game operations communicate with the FastAPI backend via HTTP requests
    to SERVER_URL (default: http://localhost:8000).

Design Notes:
    - Gradio runs on port 7860 by default
    - Auto-refresh only active when logged in (to reduce server load)
    - Chat messages prepended with [SYSTEM] prefix for command results
    - Database viewer shows truncated password hashes for security
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
        Tuple of (login_result, game_tab_visible, settings_tab_visible,
                  db_tab_visible, user_info, session_state)
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
            gr.update(visible=False),  # help tab
        )


def register(username: str, password: str, password_confirm: str) -> str:
    """
    Handle new user account registration.

    Validates input, sends registration request to backend API, and returns
    status message indicating success or failure.

    Validation Checks:
        - Username must be at least 2 characters
        - Password must be at least 8 characters
        - Password and confirmation must match

    Args:
        username: Desired username for new account
        password: Plain text password for new account
        password_confirm: Password confirmation (must match password)

    Returns:
        String message indicating registration success or failure
        Success: "✅ Account created successfully! You can now login as {username}."
        Failure: Error message with specific reason (validation or server error)

    Note:
        New accounts are created with default 'player' role. Admins can
        change roles via the Database tab after account creation.
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

    Session Cleanup:
        - session_id set to None
        - username set to None
        - role set to None
        - logged_in set to False

    Args:
        session_state: User's session state dictionary

    Returns:
        Tuple of (session_state, message, blank, login_tab_visible,
                  register_tab_visible, game_tab_hidden, settings_tab_hidden,
                  db_tab_hidden, help_tab_hidden)

    Side Effects:
        - Backend removes session from database and memory
        - UI returns to login/register view
        - Game, settings, database, and help tabs become hidden
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
            gr.update(visible=False),  # help tab
        )


def send_command(command: str, session_state: dict) -> str:
    """
    Send a game command to the backend API for execution.

    Forwards the command string to the backend /command endpoint, which
    parses and executes it via the game engine.

    Supported Commands:
        - Movement: north/n, south/s, east/e, west/w
        - Actions: look/l, inventory/inv/i, get/take <item>, drop <item>
        - Chat: say <message>, yell <message>, whisper/w <player> <message>
        - Info: who, help/?

    Args:
        command: Command string to execute (e.g., "look", "north", "say hello")
        session_state: User's session state dictionary

    Returns:
        String message with command result (success or error message)

    Error Handling:
        - Returns "You are not logged in." if session invalid
        - Returns "Session expired. Please log in again." on 401
        - Returns connection error if backend unreachable
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
            return data["message"]
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

    Fetches chat messages from the backend /chat endpoint. Messages are
    filtered by current room (only messages from player's location are shown).

    Message Types Shown:
        - say: Messages from players in the same room
        - yell: Yells sent to current room or from adjoining rooms
        - whisper: Private messages sent to or from this player

    Args:
        session_state: User's session state dictionary

    Returns:
        String with formatted chat messages (newline-separated)
        Returns "You are not logged in." if session invalid
        Returns "Failed to retrieve chat." on backend error

    Note:
        Chat messages are limited to 20 most recent by default in backend.
    """
    if not session_state.get("logged_in"):
        return "You are not logged in."

    try:
        response = requests.get(f"{SERVER_URL}/chat/{session_state.get('session_id')}")

        if response.status_code == 200:
            data = response.json()
            return data["chat"]
        else:
            return "Failed to retrieve chat."

    except Exception as e:
        return f"Error: {str(e)}"


def get_status(session_state: dict) -> str:
    """
    Retrieve and format player status information.

    Fetches comprehensive player status from backend /status endpoint and
    formats it for display in the status panel.

    Status Information Includes:
        - Username and role
        - Current room location
        - List of active players online
        - Complete inventory listing

    Args:
        session_state: User's session state dictionary

    Returns:
        Formatted multi-line string with complete player status
        Returns "You are not logged in." if session invalid
        Returns "Failed to retrieve status." on backend error

    Display Format:
        [Player Status]
        Username: player1
        Role: Player
        Current Room: spawn
        Active Players: player2, admin

        [Inventory]
        ...
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

    Convenience function that calls both send_command("look") and get_chat()
    to update both displays simultaneously. Used by auto-refresh timer and
    refresh button.

    Args:
        session_state: User's session state dictionary

    Returns:
        Tuple of (room_description, chat_messages)
        - room_description: Formatted room info with items, players, exits
        - chat_messages: Recent chat messages from current room

    Note:
        Returns ("Not logged in.", "") if user not authenticated.
    """
    if not session_state.get("logged_in"):
        return "Not logged in.", ""

    room_info = send_command("look", session_state)
    chat_info = get_chat(session_state)

    return room_info, chat_info


def change_password(
    old_password: str, new_password: str, confirm_password: str, session_state: dict
) -> str:
    """
    Change the current user's password.

    Sends password change request to backend /change-password endpoint.
    Requires verification of current password for security.

    Validation Checks:
        - Current password must be provided and correct
        - New password must be at least 8 characters
        - New password and confirmation must match
        - New password must be different from old password

    Args:
        old_password: Current password (for verification)
        new_password: Desired new password
        confirm_password: New password confirmation (must match new_password)
        session_state: User's session state dictionary

    Returns:
        Status message string:
        - "✅ Password changed successfully!" on success
        - "❌ <error>" on failure with specific reason

    Security Note:
        Backend verifies old password against bcrypt hash before allowing change.
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

    Sends server shutdown request to backend /admin/server/stop endpoint.
    Only users with admin or superuser role can execute this command.

    Permission Check:
        - Requires role in ["admin", "superuser"]
        - Regular players and worldbuilders will receive "Access Denied"

    Args:
        session_state: User's session state dictionary

    Returns:
        Status message string:
        - "✅ Server shutdown initiated..." on success
        - "Access Denied: Admin or Superuser role required." if insufficient perms
        - "Access Denied: Insufficient permissions." if backend rejects (403)
        - Connection error if server already stopped

    Warning:
        This stops the entire backend server, disconnecting all players.
        Server must be manually restarted to restore service.
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
# ADMIN DATABASE VIEWER FUNCTIONS
# ============================================================================


def get_database_players(session_state: dict) -> str:
    """
    Fetch and format all players from database (Admin/Superuser only).

    Retrieves complete player table from backend admin endpoint and formats
    it as human-readable text for the Database tab.

    Permission Check:
        - Requires role in ["admin", "superuser"]
        - Regular players will receive "Access Denied"

    Args:
        session_state: User's session state dictionary

    Returns:
        Formatted multi-line string with all player records:
        === PLAYERS TABLE (N records) ===

        ID: 1
          Username: player1
          Role: player
          Status: ACTIVE/BANNED
          Room: spawn
          Inventory: ["torch", "rope"]
          Created: 2025-01-15 10:30:00
          Last Login: 2025-01-15 12:45:00
          Password Hash: $2b$12$...

    Security Note:
        Password hashes are shown in full for debugging. Hashes cannot be
        reversed to obtain plaintext passwords (bcrypt is one-way).
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

    Retrieves complete sessions table from backend admin endpoint and formats
    it as human-readable text for the Database tab. Shows all currently
    logged-in users with their session details.

    Permission Check:
        - Requires role in ["admin", "superuser"]
        - Regular players will receive "Access Denied"

    Args:
        session_state: User's session state dictionary

    Returns:
        Formatted multi-line string with all session records:
        === SESSIONS TABLE (N records) ===

        ID: 1
          Username: player1
          Session ID: 550e8400-e29b-41d4-a716-446655440000
          Connected: 2025-01-15 10:30:00
          Last Activity: 2025-01-15 12:45:00

    Note:
        Session IDs are UUIDs that serve as authentication tokens. If exposed,
        they could be used to impersonate users until session expires.
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

    Retrieves chat message history from backend admin endpoint with configurable
    limit. Shows all messages across all rooms for monitoring/debugging.

    Permission Check:
        - Requires role in ["admin", "superuser"]
        - Regular players will receive "Access Denied"

    Args:
        limit: Maximum number of messages to retrieve (50, 100, 200, or 500)
        session_state: User's session state dictionary

    Returns:
        Formatted multi-line string with recent chat messages:
        === CHAT MESSAGES (N recent messages) ===

        ID: 42 | Room: spawn | Time: 2025-01-15 12:45:00
          [player1]: Hello everyone!

        ID: 43 | Room: forest | Time: 2025-01-15 12:46:00
          [player2]: Anyone here?

    Note:
        Messages shown in reverse chronological order (newest first).
        Includes all message types (say, yell, whisper) from all rooms.
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

    Allows admins to manage user accounts: change roles, ban users, or
    unban previously banned users.

    Permission Check:
        - Requires role in ["admin", "superuser"]
        - Cannot manage your own account
        - Cannot manage users with higher or equal privilege level

    Supported Actions:
        - change_role: Modify user's role (requires new_role parameter)
          Valid roles: player, worldbuilder, admin, superuser
        - ban: Deactivate account (user cannot login, active sessions terminated)
        - unban: Reactivate previously banned account

    Args:
        target_username: Username of user to manage
        action: Action to perform (change_role, ban, unban)
        new_role: New role for change_role action (ignored for ban/unban)
        session_state: User's session state dictionary

    Returns:
        Status message string:
        - "✅ Successfully changed {user}'s role to {role}" on role change
        - "✅ Successfully banned {user}" on ban
        - "✅ Successfully unbanned {user}" on unban
        - "❌ <error>" on failure with specific reason

    Security Note:
        Role hierarchy prevents privilege escalation. Admins cannot create
        superusers or modify other admin/superuser accounts.
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
# GRADIO INTERFACE CREATION
# ============================================================================


def create_interface():
    """
    Create and configure the complete Gradio web interface.

    Builds the entire multi-tab UI with all components, event handlers, and
    per-user state management. This is the main entry point for UI creation.

    Interface Tabs:
        1. Login - Username/password authentication
        2. Register - New account creation
        3. Game - Main gameplay interface with:
           - Room display (world view)
           - Status panel (player info, inventory)
           - Chat display (room messages)
           - Movement buttons (N/S/E/W)
           - Action buttons (look, inventory, who, help)
           - Command input field
           - Auto-refresh timer (3 seconds)
        4. Settings - Password change, server control (admin)
        5. Database - Admin database viewer (admin/superuser only)
        6. Help - Game instructions and command reference

    Tab Visibility:
        - Login/Register: Always visible (hidden after successful login)
        - Game/Settings/Help: Visible only when logged in
        - Database: Visible only for admin/superuser roles

    State Management:
        - Uses gr.State for per-user session isolation
        - Session state dict contains: session_id, username, role, logged_in
        - All functions accept/return session_state to maintain isolation

    Auto-Refresh:
        - Timer ticks every 3 seconds when logged in
        - Updates room, chat, and status displays automatically
        - Only active when user is authenticated (reduces server load)

    Returns:
        gr.Blocks: Configured Gradio interface ready to launch

    Note:
        Nested handler functions (handle_command, handle_direction, etc.)
        are defined inline to capture the session_state from the closure.
    """

    with gr.Blocks(title="MUD Client", theme=gr.themes.Soft()) as interface:
        gr.Markdown("# MUD Client")
        gr.Markdown("A simple Multi-User Dungeon client")

        # Session state (per-user)
        session_state = gr.State(
            {"session_id": None, "username": None, "role": None, "logged_in": False}
        )

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
                    login_output = gr.Textbox(label="Login Status", interactive=False, lines=10)

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
                    separate logout_and_hide_tabs() function below.

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

            # Settings Tab (visible only when logged in)
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
                        change_password_output = gr.Textbox(
                            label="Status", interactive=False, lines=5
                        )

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

            # Help Tab (visible only when logged in)
            with gr.Tab("Help", visible=False) as help_tab:
                gr.Markdown(
                    """
# MUD Client Help

## Getting Started
1. Enter your username in the Login tab
2. Click Login to create an account or log in
3. Navigate to the Game tab to start playing

## Commands
All commands can use the `/` prefix (e.g., `/look`) but it's optional.

### Movement
- `/north`, `/n` - Move north
- `/south`, `/s` - Move south
- `/east`, `/e` - Move east
- `/west`, `/w` - Move west

### Actions
- `/look`, `/l` - View your current location
- `/inventory`, `/inv`, `/i` - Check your items
- `/get <item>`, `/take <item>` - Pick up an item (e.g., `/get torch`)
- `/drop <item>` - Drop an item from your inventory

### Communication
- `/say <message>` - Send a message to players in your current room
- `/yell <message>` - Yell to current room and adjoining rooms
- `/whisper <player> <message>` - Send private message (only you and target see it)

### Other
- `/who` - See who else is online
- `/help`, `/?` - Display help information

## World
The world consists of a central spawn zone with 4 cardinal directions:
- **North**: Enchanted Forest
- **South**: Golden Desert
- **East**: Snow-Capped Mountain
- **West**: Crystalline Lake

Each zone contains items you can collect.

## Tips
- The game auto-refreshes every 3 seconds
- Chat messages are visible to all players in the same room
- Yells can be heard from any room
- You can pick up items and carry them in your inventory
                """
                )

        # Wire up login event handler
        login_btn.click(
            login,
            inputs=[login_username_input, login_password_input, session_state],
            outputs=[
                session_state,
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
        def logout_and_hide_tabs(session_st):
            """
            Handle logout button click and update tab visibility.

            This is a separate handler from the one in the Game tab because
            tab visibility components need to be wired at the top level after
            all tabs are defined. Calls logout() and extracts the relevant
            outputs for session state, message, and tab visibility updates.

            Returns:
                Tuple for Gradio outputs: (session_state, message, login_tab,
                register_tab, game_tab, settings_tab, database_tab, help_tab)
                - login_tab, register_tab: Made visible
                - game_tab, settings_tab, database_tab, help_tab: Hidden

            Note:
                The result indices [0], [1], [3]-[8] correspond to the return
                tuple structure from logout() function.
            """
            result = logout(session_st)
            return (
                result[0],
                result[1],
                result[3],
                result[4],
                result[5],
                result[6],
                result[7],
                result[8],
            )

        logout_btn.click(
            logout_and_hide_tabs,
            inputs=[session_state],
            outputs=[
                session_state,
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
