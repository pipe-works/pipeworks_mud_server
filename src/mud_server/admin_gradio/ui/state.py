"""
UI state builders for Gradio interface.

This module provides functions that build Gradio UI state updates based on
application state. It encapsulates the complex tuple structures returned by
various UI operations.

By separating UI state management from API logic, we:
- Make API functions testable without Gradio dependencies
- Centralize UI update patterns for consistency
- Make it easier to modify the UI layout without changing API code

State Building Pattern:
    UI state builders return tuples in a fixed order matching the Gradio
    component structure. Each builder documents its return tuple structure.
"""

import gradio as gr


def build_logged_in_state(
    session_state: dict,
    message: str,
    has_admin_access: bool = False,
) -> tuple:
    """
    Build UI state for successful login.

    When a user logs in successfully, we:
    - Clear password fields for security
    - Show game-related tabs
    - Show admin tabs if user has admin/superuser role
    - Keep login tab visible to show success message

    Args:
        session_state: Updated session state dictionary
        message: Success message to display
        has_admin_access: Whether user has admin or superuser role

    Returns:
        Tuple of (session_state, message, clear_username, clear_password,
                  login_tab, register_tab, game_tab, settings_tab, db_tab,
                  ollama_tab, help_tab)
    """
    return (
        session_state,
        message,
        "",  # clear username field
        "",  # clear password field
        gr.update(visible=True),  # login tab (keep visible for message)
        gr.update(visible=False),  # register tab (hide after login)
        gr.update(visible=True),  # game tab (show)
        gr.update(visible=True),  # settings tab (show)
        gr.update(visible=has_admin_access),  # database tab (admin only)
        gr.update(visible=has_admin_access),  # ollama tab (admin only)
        gr.update(visible=True),  # help tab (show)
    )


def build_logged_out_state(
    session_state: dict,
    message: str,
) -> tuple:
    """
    Build UI state for logged out user.

    When a user is logged out (or logout fails), we:
    - Clear sensitive fields
    - Hide all game and admin tabs
    - Show only login and register tabs

    Args:
        session_state: Updated session state dictionary
        message: Message to display (success or error)

    Returns:
        Tuple of (session_state, message, blank, login_tab, register_tab,
                  game_tab, settings_tab, db_tab, ollama_tab, help_tab)
    """
    return (
        session_state,
        message,
        "",  # blank field for consistency with some functions
        gr.update(visible=True),  # login tab (show)
        gr.update(visible=True),  # register tab (show)
        gr.update(visible=False),  # game tab (hide)
        gr.update(visible=False),  # settings tab (hide)
        gr.update(visible=False),  # database tab (hide)
        gr.update(visible=False),  # ollama tab (hide)
        gr.update(visible=False),  # help tab (hide)
    )


def build_login_failed_state(
    session_state: dict,
    error_message: str,
) -> tuple:
    """
    Build UI state for failed login attempt.

    When login fails, we:
    - Clear password field for security (but preserve username)
    - Keep login/register tabs visible
    - Keep all other tabs hidden
    - Display error message

    Args:
        session_state: Current session state (unchanged)
        error_message: Error message to display

    Returns:
        Tuple of (session_state, error_message, preserve_username, clear_password,
                  login_tab, register_tab, game_tab, settings_tab, db_tab,
                  ollama_tab, help_tab)
    """
    return (
        session_state,
        error_message,
        "",  # preserve username (don't clear)
        "",  # clear password field
        gr.update(visible=True),  # login tab (show)
        gr.update(visible=True),  # register tab (show)
        gr.update(visible=False),  # game tab (hide)
        gr.update(visible=False),  # settings tab (hide)
        gr.update(visible=False),  # database tab (hide)
        gr.update(visible=False),  # ollama tab (hide)
        gr.update(visible=False),  # help tab (hide)
    )


def is_admin_role(role: str) -> bool:
    """
    Check if a role has admin access.

    Args:
        role: User role string

    Returns:
        True if role is admin or superuser, False otherwise

    Examples:
        >>> is_admin_role("admin")
        True
        >>> is_admin_role("superuser")
        True
        >>> is_admin_role("player")
        False
        >>> is_admin_role("worldbuilder")
        False
    """
    return role in ["admin", "superuser"]


def update_session_state(
    session_state: dict,
    session_id: str,
    username: str,
    role: str,
    logged_in: bool = True,
) -> dict:
    """
    Update session state with login information.

    This is a pure function that creates a new session state dictionary
    with updated values.

    Args:
        session_state: Current session state dictionary
        session_id: New session ID from backend
        username: Username that logged in
        role: User's role (player/worldbuilder/admin/superuser)
        logged_in: Login status (default: True)

    Returns:
        Updated session state dictionary

    Examples:
        >>> state = {}
        >>> new_state = update_session_state(state, "abc123", "alice", "player")
        >>> new_state["session_id"]
        'abc123'
        >>> new_state["username"]
        'alice'
        >>> new_state["logged_in"]
        True
    """
    session_state["session_id"] = session_id
    session_state["username"] = username
    session_state["role"] = role
    session_state["logged_in"] = logged_in
    return session_state


def clear_session_state(session_state: dict) -> dict:
    """
    Clear session state on logout.

    This is a pure function that resets all session fields to None/False.

    Args:
        session_state: Current session state dictionary

    Returns:
        Cleared session state dictionary

    Examples:
        >>> state = {"session_id": "abc", "username": "alice", "role": "player", "logged_in": True}
        >>> cleared = clear_session_state(state)
        >>> cleared["logged_in"]
        False
        >>> cleared["session_id"] is None
        True
    """
    session_state["session_id"] = None
    session_state["username"] = None
    session_state["role"] = None
    session_state["logged_in"] = False
    return session_state
