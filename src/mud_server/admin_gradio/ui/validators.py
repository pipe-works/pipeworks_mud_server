"""
Input validation utilities for MUD client.

This module provides validation functions for user input across all client
operations. All validators return a tuple of (is_valid: bool, error_message: str).

Validation is separated from API logic to enable:
- Reusability across different UI contexts
- Easy testing of validation rules
- Consistent error messages
- Client-side validation before API calls

Password Validation:
    This module integrates with the password_policy module for comprehensive
    password strength validation. The validate_password_strength() function
    provides detailed feedback including:
    - Policy compliance checking (length, character classes)
    - Common password rejection
    - Sequential/repeated character detection
    - Strength scoring and entropy estimation

Common Patterns:
    All validators return (bool, str) tuples:
    - (True, "") for valid input
    - (False, "Error message") for invalid input

See Also:
    mud_server.api.password_policy: Comprehensive password policy enforcement.
"""

from mud_server.api.password_policy import (
    PolicyLevel,
    ValidationResult,
    get_password_requirements,
)
from mud_server.api.password_policy import (
    validate_password_strength as _validate_strength,
)


def validate_username(username: str | None) -> tuple[bool, str]:
    """
    Validate username meets requirements.

    Requirements:
    - Must not be None or empty
    - Must be at least 2 characters after stripping whitespace

    Args:
        username: Username to validate

    Returns:
        Tuple of (is_valid, error_message)
        - (True, "") if valid
        - (False, error_message) if invalid

    Examples:
        >>> validate_username("alice")
        (True, "")
        >>> validate_username("a")
        (False, "Username must be at least 2 characters.")
        >>> validate_username("  ")
        (False, "Username must be at least 2 characters.")
        >>> validate_username(None)
        (False, "Username must be at least 2 characters.")
    """
    if not username or len(username.strip()) < 2:
        return False, "Username must be at least 2 characters."
    return True, ""


def validate_password(password: str | None, min_length: int = 8) -> tuple[bool, str]:
    """
    Validate password meets basic length requirements.

    This is a simple length-only validator for backward compatibility.
    For comprehensive password strength validation including common password
    checking, sequential/repeated character detection, and strength scoring,
    use validate_password_with_policy() instead.

    Requirements:
    - Must not be None or empty
    - Must be at least min_length characters (default: 8)

    Args:
        password: Password to validate
        min_length: Minimum required length (default: 8)

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_password("password123")
        (True, "")
        >>> validate_password("short")
        (False, "Password must be at least 8 characters.")
        >>> validate_password(None)
        (False, "Password is required.")

    See Also:
        validate_password_with_policy: Comprehensive password validation.
    """
    if password is None or password == "":
        return False, "Password is required."

    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters."

    return True, ""


def validate_password_with_policy(
    password: str | None,
    level: PolicyLevel = PolicyLevel.STANDARD,
) -> tuple[bool, str, ValidationResult | None]:
    """
    Validate password against comprehensive security policy.

    This function performs thorough password validation using the password
    policy module. It checks for:
    - Minimum length requirements (12 chars for STANDARD policy)
    - Common/compromised password rejection
    - Sequential character patterns (abc, 123)
    - Repeated character patterns (aaa, 111)
    - Character class diversity (uppercase, lowercase, digits, special)

    The function returns detailed feedback including a strength score and
    specific error messages to help users create stronger passwords.

    Args:
        password: Password to validate. Must not be None or empty.
        level: Security policy level to enforce. Options:
            - PolicyLevel.BASIC: 8 char minimum, basic checks
            - PolicyLevel.STANDARD: 12 char minimum, comprehensive checks (default)
            - PolicyLevel.STRICT: 16 char minimum, all character classes required

    Returns:
        Tuple of (is_valid, error_message, validation_result):
        - is_valid: True if password meets all policy requirements
        - error_message: Combined error messages or empty string if valid
        - validation_result: Full ValidationResult object with score, warnings, etc.
                            None if password was None/empty.

    Examples:
        >>> is_valid, msg, result = validate_password_with_policy("MyStr0ng!Pass#2024")
        >>> is_valid
        True
        >>> result.score > 70
        True

        >>> is_valid, msg, result = validate_password_with_policy("password123")
        >>> is_valid
        False
        >>> "common" in msg.lower()
        True

        >>> is_valid, msg, result = validate_password_with_policy("short")
        >>> is_valid
        False
        >>> "12 characters" in msg
        True

    See Also:
        mud_server.api.password_policy: Full policy configuration options.
        get_password_requirements_text: Get human-readable requirements.
    """
    if password is None or password == "":
        return False, "Password is required.", None

    result = _validate_strength(password, level=level)

    if result.is_valid:
        return True, "", result

    # Combine all errors into a single message
    error_message = " ".join(result.errors)
    return False, error_message, result


def get_password_requirements_text(
    level: PolicyLevel = PolicyLevel.STANDARD,
) -> str:
    """
    Get human-readable password requirements for display to users.

    This function returns a formatted string describing all password
    requirements for the specified policy level. Useful for displaying
    in registration forms, password change dialogs, or help text.

    Args:
        level: Policy level to describe. Options:
            - PolicyLevel.BASIC: Minimal requirements
            - PolicyLevel.STANDARD: Recommended requirements (default)
            - PolicyLevel.STRICT: Maximum security requirements

    Returns:
        Multi-line string describing all password requirements.

    Examples:
        >>> requirements = get_password_requirements_text()
        >>> "12 characters" in requirements
        True
        >>> "common" in requirements.lower()
        True

        >>> strict_req = get_password_requirements_text(PolicyLevel.STRICT)
        >>> "16 characters" in strict_req
        True
        >>> "uppercase" in strict_req.lower()
        True
    """
    return get_password_requirements(level)


def validate_password_confirmation(
    password: str | None,
    password_confirm: str | None,
) -> tuple[bool, str]:
    """
    Validate that password and confirmation match.

    This should be called AFTER validate_password() has confirmed the
    password meets basic requirements.

    Args:
        password: Original password
        password_confirm: Confirmation password

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_password_confirmation("password123", "password123")
        (True, "")
        >>> validate_password_confirmation("password123", "different")
        (False, "Passwords do not match.")
    """
    if password != password_confirm:
        return False, "Passwords do not match."
    return True, ""


def validate_password_different(
    old_password: str | None,
    new_password: str | None,
) -> tuple[bool, str]:
    """
    Validate that new password is different from old password.

    Args:
        old_password: Current/old password
        new_password: New password to set

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_password_different("old123", "new456")
        (True, "")
        >>> validate_password_different("same123", "same123")
        (False, "New password must be different from current password.")
    """
    if old_password == new_password:
        return False, "New password must be different from current password."
    return True, ""


def validate_required_field(value: str | None, field_name: str) -> tuple[bool, str]:
    """
    Validate that a required field has a value.

    Args:
        value: Field value to check
        field_name: Name of field (for error message)

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_required_field("something", "username")
        (True, "")
        >>> validate_required_field("", "password")
        (False, "Password is required.")
        >>> validate_required_field(None, "email")
        (False, "Email is required.")
    """
    if not value or not value.strip():
        return False, f"{field_name.capitalize()} is required."
    return True, ""


def validate_session_state(session_state: dict) -> tuple[bool, str]:
    """
    Validate that user has an active session.

    Args:
        session_state: Session state dictionary from Gradio

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_session_state({"logged_in": True})
        (True, "")
        >>> validate_session_state({"logged_in": False})
        (False, "You are not logged in.")
        >>> validate_session_state({})
        (False, "You are not logged in.")
    """
    if not session_state.get("logged_in"):
        return False, "You are not logged in."
    return True, ""


def validate_admin_role(session_state: dict) -> tuple[bool, str]:
    """
    Validate that user has admin or superuser role.

    This should be called AFTER validate_session_state() has confirmed
    the user is logged in.

    Args:
        session_state: Session state dictionary from Gradio

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_admin_role({"role": "admin"})
        (True, "")
        >>> validate_admin_role({"role": "superuser"})
        (True, "")
        >>> validate_admin_role({"role": "player"})
        (False, "Access Denied: Admin or Superuser role required.")
    """
    role = session_state.get("role", "player")
    if role not in ["admin", "superuser"]:
        return False, "Access Denied: Admin or Superuser role required."
    return True, ""


def validate_command_input(command: str | None) -> tuple[bool, str]:
    """
    Validate that a command has been entered.

    Args:
        command: Command string to validate

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_command_input("look")
        (True, "")
        >>> validate_command_input("   ")
        (False, "Enter a command.")
        >>> validate_command_input("")
        (False, "Enter a command.")
    """
    if not command or not command.strip():
        return False, "Enter a command."
    return True, ""
