#!/usr/bin/env python3
"""Test authentication system."""

import json

import requests

SERVER_URL = "http://localhost:8000"


def test_registration():
    """Test user registration."""
    print("\n" + "=" * 50)
    print("Testing Registration")
    print("=" * 50)

    response = requests.post(
        f"{SERVER_URL}/register",
        json={
            "username": "testplayer",
            "password": "testpass123",
            "password_confirm": "testpass123",
        },
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200


def test_login(username, password):
    """Test user login."""
    print("\n" + "=" * 50)
    print(f"Testing Login: {username}")
    print("=" * 50)

    response = requests.post(
        f"{SERVER_URL}/login", json={"username": username, "password": password}
    )

    print(f"Status Code: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")

    if response.status_code == 200:
        return data.get("session_id"), data.get("role")
    return None, None


def test_failed_login():
    """Test login with wrong password."""
    print("\n" + "=" * 50)
    print("Testing Failed Login (wrong password)")
    print("=" * 50)

    response = requests.post(
        f"{SERVER_URL}/login", json={"username": "testplayer", "password": "wrongpassword"}
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 401


def test_game_command(session_id, command):
    """Test a game command."""
    print(f"\nTesting command: {command}")

    response = requests.post(
        f"{SERVER_URL}/command", json={"session_id": session_id, "command": command}
    )

    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Message: {data['message'][:100]}...")
    else:
        print(f"Error: {response.json()}")


def test_status(session_id):
    """Test status endpoint."""
    print("\nTesting status endpoint")

    response = requests.get(f"{SERVER_URL}/status/{session_id}")

    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Current Room: {data['current_room']}")
        print(f"Active Players: {data['active_players']}")
        print(f"Inventory: {data['inventory']}")


if __name__ == "__main__":
    print("\n🔐 AUTHENTICATION SYSTEM TEST")
    print("=" * 50)

    # Test 1: Register new player
    success = test_registration()
    if not success:
        print("\n❌ Registration failed!")
    else:
        print("\n✅ Registration successful!")

    # Test 2: Login with new player
    session_id, role = test_login("testplayer", "testpass123")
    if session_id:
        print(f"\n✅ Login successful! Role: {role}")

        # Test game commands
        test_status(session_id)
        test_game_command(session_id, "look")
        test_game_command(session_id, "inventory")
    else:
        print("\n❌ Login failed!")

    # Test 3: Login with admin superuser
    admin_session, admin_role = test_login("admin", "admin123")
    if admin_session:
        print(f"\n✅ Admin login successful! Role: {admin_role}")
        test_status(admin_session)
    else:
        print("\n❌ Admin login failed!")

    # Test 4: Failed login
    failed = test_failed_login()
    if failed:
        print("\n✅ Failed login handled correctly!")
    else:
        print("\n❌ Failed login test didn't work as expected!")

    print("\n" + "=" * 50)
    print("🎉 AUTHENTICATION TESTS COMPLETE")
    print("=" * 50)
