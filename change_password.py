#!/usr/bin/env python3
"""Change a user's password."""

import sys

from mud_server.db import database


def change_password(username: str, new_password: str):
    """Change password for a user."""
    if not database.player_exists(username):
        print(f"❌ User '{username}' does not exist.")
        return False

    if len(new_password) < 8:
        print("❌ Password must be at least 8 characters.")
        return False

    success = database.change_password_for_user(username, new_password)

    if success:
        print(f"✅ Password changed successfully for user '{username}'!")
        return True
    else:
        print(f"❌ Failed to change password for user '{username}'.")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 change_password.py <username> <new_password>")
        print("\nExample:")
        print("  PYTHONPATH=src python3 change_password.py admin MyNewSecurePass123")
        sys.exit(1)

    username = sys.argv[1]
    new_password = sys.argv[2]

    print(f"Changing password for user: {username}")
    change_password(username, new_password)
