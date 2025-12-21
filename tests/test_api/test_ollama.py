"""
Tests for Ollama API endpoints and conversation context management.

Tests cover:
- Ollama command execution
- Conversation context storage and retrieval
- Clear context endpoint
- Permission checks for Ollama operations
- Context isolation between sessions

All tests verify proper permission checking and conversation history management.
"""

from unittest.mock import Mock, patch

import pytest


# ============================================================================
# OLLAMA CONVERSATION CONTEXT TESTS
# ============================================================================


@pytest.mark.api
@pytest.mark.admin
def test_ollama_context_stored_per_session(test_client, test_db, temp_db_path, db_with_users):
    """Test that conversation context is stored per session."""
    with patch("mud_server.db.database.DB_PATH", temp_db_path):
        # Login as admin
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": "password123"}
        )
        admin_session = login_response.json()["session_id"]

        # Mock the Ollama API response
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {"role": "assistant", "content": "Hello! How can I help you?"}
            }
            mock_post.return_value = mock_response

            # Execute first command
            response1 = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": admin_session,
                    "server_url": "http://localhost:11434",
                    "command": "run llama2 Hello",
                },
            )

            assert response1.status_code == 200
            assert "Context: 2 messages" in response1.json()["output"]

            # Execute second command (should have context)
            response2 = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": admin_session,
                    "server_url": "http://localhost:11434",
                    "command": "run llama2 What's your name?",
                },
            )

            assert response2.status_code == 200
            assert "Context: 4 messages" in response2.json()["output"]

            # Verify that the mock was called with conversation history
            call_args = mock_post.call_args_list[-1]
            messages = call_args[1]["json"]["messages"]
            # Should have full history: user1, assistant1, user2, assistant2
            assert len(messages) == 4


@pytest.mark.api
@pytest.mark.admin
def test_ollama_context_isolated_between_sessions(
    test_client, test_db, temp_db_path, db_with_users
):
    """Test that conversation context is isolated between different sessions."""
    with patch("mud_server.db.database.DB_PATH", temp_db_path):
        # Login as admin
        login_response1 = test_client.post(
            "/login", json={"username": "testadmin", "password": "password123"}
        )
        admin_session = login_response1.json()["session_id"]

        # Login as superuser
        login_response2 = test_client.post(
            "/login", json={"username": "testsuperuser", "password": "password123"}
        )
        superuser_session = login_response2.json()["session_id"]

        # Mock the Ollama API response
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {"role": "assistant", "content": "Response"}
            }
            mock_post.return_value = mock_response

            # Admin sends a message
            test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": admin_session,
                    "server_url": "http://localhost:11434",
                    "command": "run llama2 Admin message",
                },
            )

            # Superuser sends a message (should start fresh)
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": superuser_session,
                    "server_url": "http://localhost:11434",
                    "command": "run llama2 Superuser message",
                },
            )

            assert response.status_code == 200
            # Should show only 2 messages (user + assistant), not 4
            assert "Context: 2 messages" in response.json()["output"]


@pytest.mark.api
@pytest.mark.admin
def test_clear_context_removes_history(test_client, test_db, temp_db_path, db_with_users):
    """Test that clear context endpoint removes conversation history."""
    with patch("mud_server.db.database.DB_PATH", temp_db_path):
        # Login as admin
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": "password123"}
        )
        admin_session = login_response.json()["session_id"]

        # Mock the Ollama API response
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {"role": "assistant", "content": "Response"}
            }
            mock_post.return_value = mock_response

            # Execute command to build context
            test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": admin_session,
                    "server_url": "http://localhost:11434",
                    "command": "run llama2 First message",
                },
            )

            # Clear context
            clear_response = test_client.post(
                "/admin/ollama/clear-context", json={"session_id": admin_session}
            )

            assert clear_response.status_code == 200
            assert clear_response.json()["success"] is True
            assert "2 messages removed" in clear_response.json()["message"]

            # Execute another command (should start fresh)
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": admin_session,
                    "server_url": "http://localhost:11434",
                    "command": "run llama2 Second message",
                },
            )

            assert response.status_code == 200
            # Should show only 2 messages (fresh start)
            assert "Context: 2 messages" in response.json()["output"]


@pytest.mark.api
@pytest.mark.admin
def test_clear_context_when_no_context(test_client, test_db, temp_db_path, db_with_users):
    """Test clearing context when there is no context."""
    with patch("mud_server.db.database.DB_PATH", temp_db_path):
        # Login as admin
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": "password123"}
        )
        admin_session = login_response.json()["session_id"]

        # Clear context when there's nothing to clear
        clear_response = test_client.post(
            "/admin/ollama/clear-context", json={"session_id": admin_session}
        )

        assert clear_response.status_code == 200
        assert clear_response.json()["success"] is True
        assert "No conversation context to clear" in clear_response.json()["message"]


@pytest.mark.api
@pytest.mark.admin
def test_ollama_context_survives_error(test_client, test_db, temp_db_path, db_with_users):
    """Test that context is preserved even if an Ollama API call fails."""
    with patch("mud_server.db.database.DB_PATH", temp_db_path):
        # Login as admin
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": "password123"}
        )
        admin_session = login_response.json()["session_id"]

        with patch("requests.post") as mock_post:
            # First successful call
            mock_response_success = Mock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {
                "message": {"role": "assistant", "content": "Response"}
            }

            # Second call fails
            mock_response_fail = Mock()
            mock_response_fail.status_code = 500
            mock_response_fail.text = "Internal error"

            # Third call succeeds
            mock_response_success2 = Mock()
            mock_response_success2.status_code = 200
            mock_response_success2.json.return_value = {
                "message": {"role": "assistant", "content": "Response 2"}
            }

            mock_post.side_effect = [
                mock_response_success,
                mock_response_fail,
                mock_response_success2,
            ]

            # First successful command
            test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": admin_session,
                    "server_url": "http://localhost:11434",
                    "command": "run llama2 First",
                },
            )

            # Second command fails
            test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": admin_session,
                    "server_url": "http://localhost:11434",
                    "command": "run llama2 Second",
                },
            )

            # Third command succeeds - should have context from first only
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": admin_session,
                    "server_url": "http://localhost:11434",
                    "command": "run llama2 Third",
                },
            )

            assert response.status_code == 200
            # Should have 2 messages from first call + 2 from third = 4 total
            assert "Context: 4 messages" in response.json()["output"]


# ============================================================================
# PERMISSION TESTS
# ============================================================================


@pytest.mark.api
@pytest.mark.auth
def test_player_cannot_access_ollama(test_client, test_db, temp_db_path, db_with_users):
    """Test that regular players cannot access Ollama endpoints."""
    with patch("mud_server.db.database.DB_PATH", temp_db_path):
        # Login as player
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": "password123"}
        )
        player_session = login_response.json()["session_id"]

        # Try to execute Ollama command
        response = test_client.post(
            "/admin/ollama/command",
            json={
                "session_id": player_session,
                "server_url": "http://localhost:11434",
                "command": "list",
            },
        )

        assert response.status_code == 403


@pytest.mark.api
@pytest.mark.auth
def test_player_cannot_clear_ollama_context(test_client, test_db, temp_db_path, db_with_users):
    """Test that regular players cannot clear Ollama context."""
    with patch("mud_server.db.database.DB_PATH", temp_db_path):
        # Login as player
        login_response = test_client.post(
            "/login", json={"username": "testplayer", "password": "password123"}
        )
        player_session = login_response.json()["session_id"]

        # Try to clear context
        response = test_client.post(
            "/admin/ollama/clear-context", json={"session_id": player_session}
        )

        assert response.status_code == 403


@pytest.mark.api
@pytest.mark.auth
def test_admin_can_access_ollama(test_client, test_db, temp_db_path, db_with_users):
    """Test that admins can access Ollama endpoints."""
    with patch("mud_server.db.database.DB_PATH", temp_db_path):
        # Login as admin
        login_response = test_client.post(
            "/login", json={"username": "testadmin", "password": "password123"}
        )
        admin_session = login_response.json()["session_id"]

        # Mock the Ollama API to avoid actual network calls
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"models": []}
            mock_get.return_value = mock_response

            # Execute Ollama command
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": admin_session,
                    "server_url": "http://localhost:11434",
                    "command": "list",
                },
            )

            assert response.status_code == 200


@pytest.mark.api
@pytest.mark.auth
def test_superuser_can_access_ollama(test_client, test_db, temp_db_path, db_with_users):
    """Test that superusers can access Ollama endpoints."""
    with patch("mud_server.db.database.DB_PATH", temp_db_path):
        # Login as superuser
        login_response = test_client.post(
            "/login", json={"username": "testsuperuser", "password": "password123"}
        )
        superuser_session = login_response.json()["session_id"]

        # Mock the Ollama API
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"models": []}
            mock_get.return_value = mock_response

            # Execute Ollama command
            response = test_client.post(
                "/admin/ollama/command",
                json={
                    "session_id": superuser_session,
                    "server_url": "http://localhost:11434",
                    "command": "list",
                },
            )

            assert response.status_code == 200
