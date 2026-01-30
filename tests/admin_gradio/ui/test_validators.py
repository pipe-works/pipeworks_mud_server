"""
Tests for input validation utilities.

This module tests all validation functions to ensure:
- Correct validation of valid inputs
- Proper error messages for invalid inputs
- Edge cases are handled correctly
"""

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
from tests.constants import TEST_PASSWORD


class TestValidateUsername:
    """Tests for username validation."""

    def test_valid_username(self):
        """Test that valid usernames pass validation."""
        is_valid, error = validate_username("alice")
        assert is_valid is True
        assert error == ""

    def test_valid_long_username(self):
        """Test that long usernames are valid."""
        is_valid, error = validate_username("a" * 50)
        assert is_valid is True
        assert error == ""

    def test_valid_username_with_spaces(self):
        """Test username with leading/trailing spaces (should be valid if stripped length >= 2)."""
        is_valid, error = validate_username("  alice  ")
        assert is_valid is True
        assert error == ""

    def test_single_character_username(self):
        """Test that single character username is invalid."""
        is_valid, error = validate_username("a")
        assert is_valid is False
        assert error == "Username must be at least 2 characters."

    def test_empty_username(self):
        """Test that empty username is invalid."""
        is_valid, error = validate_username("")
        assert is_valid is False
        assert error == "Username must be at least 2 characters."

    def test_whitespace_only_username(self):
        """Test that whitespace-only username is invalid."""
        is_valid, error = validate_username("   ")
        assert is_valid is False
        assert error == "Username must be at least 2 characters."

    def test_none_username(self):
        """Test that None username is invalid."""
        is_valid, error = validate_username(None)
        assert is_valid is False
        assert error == "Username must be at least 2 characters."


class TestValidatePassword:
    """Tests for password validation."""

    def test_valid_password(self):
        """Test that valid password passes validation."""
        is_valid, error = validate_password(TEST_PASSWORD)
        assert is_valid is True
        assert error == ""

    def test_minimum_length_password(self):
        """Test password exactly at minimum length."""
        is_valid, error = validate_password("12345678")
        assert is_valid is True
        assert error == ""

    def test_custom_min_length(self):
        """Test password validation with custom minimum length."""
        is_valid, error = validate_password("short", min_length=10)
        assert is_valid is False
        assert error == "Password must be at least 10 characters."

    def test_short_password(self):
        """Test that password below minimum length is invalid."""
        is_valid, error = validate_password("short")
        assert is_valid is False
        assert error == "Password must be at least 8 characters."

    def test_empty_password(self):
        """Test that empty password is invalid."""
        is_valid, error = validate_password("")
        assert is_valid is False
        assert error == "Password is required."

    def test_none_password(self):
        """Test that None password is invalid."""
        is_valid, error = validate_password(None)
        assert is_valid is False
        assert error == "Password is required."


class TestValidatePasswordConfirmation:
    """Tests for password confirmation validation."""

    def test_matching_passwords(self):
        """Test that matching passwords pass validation."""
        is_valid, error = validate_password_confirmation(TEST_PASSWORD, TEST_PASSWORD)
        assert is_valid is True
        assert error == ""

    def test_mismatched_passwords(self):
        """Test that mismatched passwords fail validation."""
        is_valid, error = validate_password_confirmation(TEST_PASSWORD, "different")
        assert is_valid is False
        assert error == "Passwords do not match."

    def test_empty_confirmation(self):
        """Test password with empty confirmation."""
        is_valid, error = validate_password_confirmation(TEST_PASSWORD, "")
        assert is_valid is False
        assert error == "Passwords do not match."

    def test_none_confirmation(self):
        """Test password with None confirmation."""
        is_valid, error = validate_password_confirmation(TEST_PASSWORD, None)
        assert is_valid is False
        assert error == "Passwords do not match."


class TestValidatePasswordDifferent:
    """Tests for password difference validation."""

    def test_different_passwords(self):
        """Test that different passwords pass validation."""
        is_valid, error = validate_password_different("old123", "new456")
        assert is_valid is True
        assert error == ""

    def test_same_passwords(self):
        """Test that same old and new password fails validation."""
        is_valid, error = validate_password_different("same123", "same123")
        assert is_valid is False
        assert error == "New password must be different from current password."

    def test_empty_old_password(self):
        """Test with empty old password but different new password."""
        is_valid, error = validate_password_different("", "new123")
        assert is_valid is True
        assert error == ""


class TestValidateRequiredField:
    """Tests for required field validation."""

    def test_valid_field(self):
        """Test that field with value passes validation."""
        is_valid, error = validate_required_field("something", "username")
        assert is_valid is True
        assert error == ""

    def test_field_with_spaces(self):
        """Test field with leading/trailing spaces."""
        is_valid, error = validate_required_field("  value  ", "email")
        assert is_valid is True
        assert error == ""

    def test_empty_field(self):
        """Test that empty field fails validation."""
        is_valid, error = validate_required_field("", "password")
        assert is_valid is False
        assert error == "Password is required."

    def test_whitespace_only_field(self):
        """Test that whitespace-only field fails validation."""
        is_valid, error = validate_required_field("   ", "username")
        assert is_valid is False
        assert error == "Username is required."

    def test_none_field(self):
        """Test that None field fails validation."""
        is_valid, error = validate_required_field(None, "email")
        assert is_valid is False
        assert error == "Email is required."

    def test_field_name_capitalization(self):
        """Test that field name is properly capitalized in error message."""
        is_valid, error = validate_required_field("", "custom_field")
        assert is_valid is False
        assert error == "Custom_field is required."


class TestValidateSessionState:
    """Tests for session state validation."""

    def test_logged_in_session(self):
        """Test that logged in session passes validation."""
        is_valid, error = validate_session_state({"logged_in": True})
        assert is_valid is True
        assert error == ""

    def test_logged_out_session(self):
        """Test that logged out session fails validation."""
        is_valid, error = validate_session_state({"logged_in": False})
        assert is_valid is False
        assert error == "You are not logged in."

    def test_missing_logged_in_key(self):
        """Test session without logged_in key fails validation."""
        is_valid, error = validate_session_state({})
        assert is_valid is False
        assert error == "You are not logged in."

    def test_session_with_other_data(self):
        """Test that logged in session with other data passes."""
        is_valid, error = validate_session_state(
            {
                "logged_in": True,
                "username": "alice",
                "session_id": "abc123",
            }
        )
        assert is_valid is True
        assert error == ""


class TestValidateAdminRole:
    """Tests for admin role validation."""

    def test_admin_role(self):
        """Test that admin role passes validation."""
        is_valid, error = validate_admin_role({"role": "admin"})
        assert is_valid is True
        assert error == ""

    def test_superuser_role(self):
        """Test that superuser role passes validation."""
        is_valid, error = validate_admin_role({"role": "superuser"})
        assert is_valid is True
        assert error == ""

    def test_player_role(self):
        """Test that player role fails validation."""
        is_valid, error = validate_admin_role({"role": "player"})
        assert is_valid is False
        assert error == "Access Denied: Admin or Superuser role required."

    def test_worldbuilder_role(self):
        """Test that worldbuilder role fails validation."""
        is_valid, error = validate_admin_role({"role": "worldbuilder"})
        assert is_valid is False
        assert error == "Access Denied: Admin or Superuser role required."

    def test_missing_role_key(self):
        """Test session without role key defaults to player and fails."""
        is_valid, error = validate_admin_role({})
        assert is_valid is False
        assert error == "Access Denied: Admin or Superuser role required."


class TestValidateCommandInput:
    """Tests for command input validation."""

    def test_valid_command(self):
        """Test that valid command passes validation."""
        is_valid, error = validate_command_input("look")
        assert is_valid is True
        assert error == ""

    def test_command_with_spaces(self):
        """Test command with leading/trailing spaces."""
        is_valid, error = validate_command_input("  go north  ")
        assert is_valid is True
        assert error == ""

    def test_empty_command(self):
        """Test that empty command fails validation."""
        is_valid, error = validate_command_input("")
        assert is_valid is False
        assert error == "Enter a command."

    def test_whitespace_only_command(self):
        """Test that whitespace-only command fails validation."""
        is_valid, error = validate_command_input("   ")
        assert is_valid is False
        assert error == "Enter a command."

    def test_none_command(self):
        """Test that None command fails validation."""
        is_valid, error = validate_command_input(None)
        assert is_valid is False
        assert error == "Enter a command."
