"""Residual compatibility tests for ``mud_server.db.database``.

The main compatibility surface has been decomposed into dedicated
``test_database_*_surface.py`` modules; this file retains mixed-surface
guards that still intentionally exercise cross-domain behavior.
"""

from unittest.mock import patch

import pytest

from mud_server.db import connection as db_connection
from mud_server.db import database
from mud_server.db.errors import DatabaseReadError, DatabaseWriteError
from tests.constants import TEST_PASSWORD


@pytest.mark.unit
@pytest.mark.db
def test_database_helpers_raise_typed_errors_on_db_error():
    """
    Verify repository-backed helpers map DB failures to typed exceptions.
    """
    with patch.object(db_connection, "get_connection", side_effect=Exception("db error")):
        with pytest.raises(DatabaseWriteError):
            database.set_user_role("testplayer", "admin")
        with pytest.raises(DatabaseWriteError):
            database.deactivate_user("testplayer")
        with pytest.raises(DatabaseWriteError):
            database.activate_user("testplayer")
        with pytest.raises(DatabaseWriteError):
            database.change_password_for_user("testplayer", TEST_PASSWORD)
        with pytest.raises(DatabaseReadError):
            database.user_exists("testplayer")
        with pytest.raises(DatabaseReadError):
            database.get_user_id("testplayer")
        with pytest.raises(DatabaseReadError):
            database.get_user_role("testplayer")

        with pytest.raises(DatabaseWriteError):
            database.set_character_room(
                "testplayer_char", "spawn", world_id=database.DEFAULT_WORLD_ID
            )
        with pytest.raises(DatabaseWriteError):
            database.set_character_inventory(
                "testplayer_char", [], world_id=database.DEFAULT_WORLD_ID
            )
        with pytest.raises(DatabaseWriteError):
            database.add_chat_message(
                "testplayer_char",
                "hi",
                "spawn",
                world_id=database.DEFAULT_WORLD_ID,
            )
        with pytest.raises(DatabaseWriteError):
            database.create_session(1, "session-x")
        with pytest.raises(DatabaseWriteError):
            database.set_session_character("session-x", 1, world_id=database.DEFAULT_WORLD_ID)
        with pytest.raises(DatabaseWriteError):
            database.remove_session_by_id("session-x")
        with pytest.raises(DatabaseWriteError):
            database.remove_sessions_for_user(1)
        with pytest.raises(DatabaseWriteError):
            database.update_session_activity("session-x")
        with pytest.raises(DatabaseWriteError):
            database.cleanup_expired_sessions()
        with pytest.raises(DatabaseWriteError):
            database.clear_all_sessions()
