#!/usr/bin/env python3
"""Test password change functionality."""

import json

import requests

SERVER_URL = "http://localhost:8000"


def test_password_change():
    """Test the complete password change flow."""
    print("\n" + "=" * 50)
    print("Testing Password Change Feature")
    print("=" * 50)

    # Step 1: Login with current password
    print("\n1. Logging in with current password (NewSecurePassword123)...")
    response = requests.post(
        f"{SERVER_URL}/login", json={"username": "admin", "password": "NewSecurePassword123"}
    )

    if response.status_code != 200:
        print("❌ Login failed!")
        print(response.json())
        return False

    data = response.json()
    session_id = data["session_id"]
    print(f"✅ Login successful! Session: {session_id[:20]}...")

    # Step 2: Change password
    print("\n2. Changing password to 'AnotherNewPass456'...")
    response = requests.post(
        f"{SERVER_URL}/change-password",
        json={
            "session_id": session_id,
            "old_password": "NewSecurePassword123",
            "new_password": "AnotherNewPass456",
        },
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code != 200:
        print("❌ Password change failed!")
        return False

    print("✅ Password change successful!")

    # Step 3: Try to login with old password (should fail)
    print("\n3. Testing old password (should fail)...")
    response = requests.post(
        f"{SERVER_URL}/login", json={"username": "admin", "password": "NewSecurePassword123"}
    )

    if response.status_code == 401:
        print("✅ Old password correctly rejected!")
    else:
        print("❌ Old password still works (unexpected)!")
        return False

    # Step 4: Login with new password (should work)
    print("\n4. Testing new password (should work)...")
    response = requests.post(
        f"{SERVER_URL}/login", json={"username": "admin", "password": "AnotherNewPass456"}
    )

    if response.status_code == 200:
        print("✅ New password works!")
        print(f"Role: {response.json()['role']}")
    else:
        print("❌ New password doesn't work!")
        return False

    # Step 5: Test validation (wrong old password)
    print("\n5. Testing validation - wrong old password...")
    response = requests.post(
        f"{SERVER_URL}/change-password",
        json={
            "session_id": response.json()["session_id"],
            "old_password": "WrongPassword",
            "new_password": "YetAnotherPass789",
        },
    )

    if response.status_code == 401:
        print("✅ Validation works - wrong old password rejected!")
    else:
        print("❌ Validation failed!")
        return False

    print("\n" + "=" * 50)
    print("🎉 ALL PASSWORD CHANGE TESTS PASSED!")
    print("=" * 50)
    return True


if __name__ == "__main__":
    test_password_change()
