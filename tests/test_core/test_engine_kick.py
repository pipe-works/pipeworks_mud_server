"""Unit tests for GameEngine kick moderation behavior."""

from __future__ import annotations

import pytest

from mud_server.config import use_test_database
from mud_server.db import database


@pytest.mark.unit
@pytest.mark.game
def test_kick_character_disconnects_target_sessions(
    mock_engine, test_db, temp_db_path, db_with_users
):
    """Kick should remove all active sessions bound to the target character."""
    with use_test_database(temp_db_path):
        database.create_session("testplayer", "target-session")
        database.create_session("testadmin", "admin-session")

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
        database.create_session("testadmin", "admin-session")

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
        database.create_session("testadmin", "admin-session")

        success, message = mock_engine.kick_character(
            "testadmin", "testadmin_char", world_id="pipeworks_web"
        )

        assert success is False
        assert "cannot kick your own session" in message.lower()
