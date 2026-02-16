"""Unit tests for GameEngine kick moderation behavior."""

from __future__ import annotations

import pytest

from mud_server.config import use_test_database
from mud_server.db import database


def _bind_session_to_first_character(username: str, session_id: str) -> None:
    """
    Create an in-world session for tests that validate kick behavior.

    Kick resolves and removes sessions bound to a target character, so tests
    must bind character_id/world_id onto the created sessions explicitly.
    """
    user_id = database.get_user_id(username)
    assert user_id is not None
    characters = database.get_user_characters(user_id)
    assert characters
    assert database.create_session(user_id, session_id)
    assert database.set_session_character(session_id, int(characters[0]["id"]))


@pytest.mark.unit
@pytest.mark.game
def test_kick_character_disconnects_target_sessions(
    mock_engine, test_db, temp_db_path, db_with_users
):
    """Kick should remove all active sessions bound to the target character."""
    with use_test_database(temp_db_path):
        _bind_session_to_first_character("testplayer", "target-session")
        _bind_session_to_first_character("testadmin", "admin-session")

        success, message = mock_engine.kick_character(
            "testadmin", "testplayer_char", world_id="pipeworks_web"
        )

        assert success is True
        assert "Kicked" in message
        assert database.get_session_by_id("target-session") is None
        assert database.get_session_by_id("admin-session") is not None


@pytest.mark.unit
@pytest.mark.game
def test_kick_character_reports_target_offline(mock_engine, test_db, temp_db_path, db_with_users):
    """Kick should report when target character has no active sessions."""
    with use_test_database(temp_db_path):
        _bind_session_to_first_character("testadmin", "admin-session")

        success, message = mock_engine.kick_character(
            "testadmin", "testplayer_char", world_id="pipeworks_web"
        )

        assert success is False
        assert "not online" in message.lower()


@pytest.mark.unit
@pytest.mark.game
def test_kick_character_rejects_self_kick(mock_engine, test_db, temp_db_path, db_with_users):
    """Kick should block a moderator from disconnecting their own session."""
    with use_test_database(temp_db_path):
        _bind_session_to_first_character("testadmin", "admin-session")

        success, message = mock_engine.kick_character(
            "testadmin", "testadmin_char", world_id="pipeworks_web"
        )

        assert success is False
        assert "cannot kick your own session" in message.lower()
