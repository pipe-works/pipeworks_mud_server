"""
UI utilities for Gradio interface.

This package provides UI-related utilities separated from API logic:
- Input validation
- UI state building (Gradio update tuples)
- Session state management

Modules:
    validators: Input validation functions
    state: UI state builders for Gradio components
"""

from mud_server.admin_gradio.ui.state import (
    build_logged_in_state,
    build_logged_out_state,
    build_login_failed_state,
    clear_session_state,
    is_admin_role,
    update_session_state,
)
from mud_server.admin_gradio.ui.validators import (
    validate_admin_role,
    validate_command_input,
    validate_password,
    validate_password_confirmation,
    validate_password_different,
    validate_required_field,
    validate_session_state,
    validate_username,
)

__all__ = [
    # State builders
    "build_logged_in_state",
    "build_logged_out_state",
    "build_login_failed_state",
    "clear_session_state",
    "is_admin_role",
    "update_session_state",
    # Validators
    "validate_admin_role",
    "validate_command_input",
    "validate_password",
    "validate_password_confirmation",
    "validate_password_different",
    "validate_required_field",
    "validate_session_state",
    "validate_username",
]
