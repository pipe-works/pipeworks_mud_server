"""
Utility functions for the MUD Client.

This module provides shared helper functions used across multiple tabs and
components in the Gradio interface.
"""

import os


def load_css(filename: str) -> str:
    """
    Load CSS from a file in the static directory.

    Args:
        filename: Name of the CSS file (e.g., 'styles.css')

    Returns:
        String containing the CSS content

    Raises:
        FileNotFoundError: If CSS file doesn't exist
    """
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    css_path = os.path.join(static_dir, filename)

    with open(css_path) as f:
        return f.read()


def create_session_state() -> dict:
    """
    Create a new session state dictionary with default values.

    Returns:
        Dictionary with session state keys initialized
    """
    return {
        "session_id": None,
        "username": None,
        "role": None,
        "logged_in": False,
    }
