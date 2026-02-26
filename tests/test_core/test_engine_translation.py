"""Integration tests for GameEngine chat methods with the translation layer.

These tests verify that ``engine.chat``, ``engine.yell``, and
``engine.whisper`` correctly:
- Use the IC text when translation succeeds.
- Fall back to the OOC text when the service returns ``None``.
- Skip translation entirely when no service is configured.

The translation service itself is mocked — its unit tests live in
``tests/test_translation/``.  Here we only test the *wiring* between the
engine and the service.
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from mud_server.config import use_test_database
from mud_server.core.bus import MudBus
from mud_server.core.engine import GameEngine

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_bus():
    MudBus.reset_for_testing()
    yield
    MudBus.reset_for_testing()


def _make_world(translation_service=None):
    """Build a minimal world stub with a controllable translation service."""
    world = MagicMock()
    world.get_translation_service.return_value = translation_service
    world.get_room.return_value = SimpleNamespace(
        id="spawn",
        exits={"north": "forest"},
        items=[],
    )
    return world


def _make_engine(world_stub) -> GameEngine:
    """Build a GameEngine whose _get_world returns the given stub."""
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
        cast(Any, engine)._get_world = lambda _world_id: world_stub
        return engine


def _make_translation_service(return_value: str | None):
    """Build a mock translation service that returns a fixed value."""
    svc = MagicMock()
    svc.translate.return_value = return_value
    return svc


# ── chat ──────────────────────────────────────────────────────────────────────


class TestEngineChatTranslation:
    def test_stores_ic_text_when_translation_succeeds(self, test_db, temp_db_path):
        svc = _make_translation_service("Hand over the ledger.")
        world = _make_world(svc)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            stored = []
            with patch("mud_server.core.engine.database") as mock_db:
                mock_db.get_character_room.return_value = "spawn"
                mock_db.add_chat_message.side_effect = lambda u, m, r, **kw: stored.append(m) or True
                engine.chat("Mira", "give me the ledger", world_id="daily_undertaking")

        # The stored message should be the IC text (sanitised), not the OOC input.
        assert stored == ["Hand over the ledger."]

    def test_falls_back_to_ooc_when_translation_returns_none(self, test_db, temp_db_path):
        svc = _make_translation_service(None)
        world = _make_world(svc)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            stored = []
            with patch("mud_server.core.engine.database") as mock_db:
                mock_db.get_character_room.return_value = "spawn"
                mock_db.add_chat_message.side_effect = lambda u, m, r, **kw: stored.append(m) or True
                engine.chat("Mira", "give me the ledger", world_id="daily_undertaking")

        assert stored == ["give me the ledger"]

    def test_skips_translation_when_no_service(self, test_db, temp_db_path):
        """When get_translation_service() returns None, translation is bypassed."""
        world = _make_world(translation_service=None)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            stored = []
            with patch("mud_server.core.engine.database") as mock_db:
                mock_db.get_character_room.return_value = "spawn"
                mock_db.add_chat_message.side_effect = lambda u, m, r, **kw: stored.append(m) or True
                engine.chat("Mira", "hello", world_id="daily_undertaking")

        assert stored == ["hello"]

    def test_translation_called_with_say_channel(self, test_db, temp_db_path):
        svc = _make_translation_service("IC text")
        world = _make_world(svc)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            with patch("mud_server.core.engine.database") as mock_db:
                mock_db.get_character_room.return_value = "spawn"
                mock_db.add_chat_message.return_value = True
                engine.chat("Mira", "hello", world_id="daily_undertaking")

        svc.translate.assert_called_once_with(
            character_name="Mira",
            ooc_message="hello",
            channel="say",
        )

    def test_returns_false_when_no_room(self, test_db, temp_db_path):
        world = _make_world(_make_translation_service("IC"))
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            with patch("mud_server.core.engine.database") as mock_db:
                mock_db.get_character_room.return_value = None
                success, msg = engine.chat("Mira", "hello", world_id="daily_undertaking")

        assert success is False


# ── yell ──────────────────────────────────────────────────────────────────────


class TestEngineYellTranslation:
    def test_stores_ic_text_with_yell_prefix(self, test_db, temp_db_path):
        svc = _make_translation_service("Can you hear me?!")
        world = _make_world(svc)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            stored = []
            with patch("mud_server.core.engine.database") as mock_db:
                mock_db.get_character_room.return_value = "spawn"
                mock_db.add_chat_message.side_effect = lambda u, m, r, **kw: stored.append(m) or True
                engine.yell("Mira", "can you hear me?!", world_id="daily_undertaking")

        # [YELL] prefix wraps the IC text (after sanitise)
        assert stored[0] == "[YELL] Can you hear me?!"

    def test_falls_back_to_ooc_with_yell_prefix_on_failure(self, test_db, temp_db_path):
        svc = _make_translation_service(None)
        world = _make_world(svc)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            stored = []
            with patch("mud_server.core.engine.database") as mock_db:
                mock_db.get_character_room.return_value = "spawn"
                mock_db.add_chat_message.side_effect = lambda u, m, r, **kw: stored.append(m) or True
                engine.yell("Mira", "can you hear me?!", world_id="daily_undertaking")

        assert stored[0] == "[YELL] can you hear me?!"

    def test_translation_called_with_yell_channel(self, test_db, temp_db_path):
        svc = _make_translation_service("IC yell")
        world = _make_world(svc)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            with patch("mud_server.core.engine.database") as mock_db:
                mock_db.get_character_room.return_value = "spawn"
                mock_db.add_chat_message.return_value = True
                engine.yell("Mira", "hello", world_id="daily_undertaking")

        svc.translate.assert_called_once_with(
            character_name="Mira",
            ooc_message="hello",
            channel="yell",
        )


# ── whisper ───────────────────────────────────────────────────────────────────


class TestEngineWhisperTranslation:
    def _patch_whisper_db(self, mock_db, sender="Mira", target="Kael", room="spawn"):
        """Set up standard DB mock responses for a successful whisper."""
        mock_db.resolve_character_name.side_effect = lambda name, **kw: name
        mock_db.get_character_room.side_effect = lambda name, **kw: room
        mock_db.character_exists.return_value = True
        mock_db.get_active_characters.return_value = [target]
        mock_db.add_chat_message.return_value = True

    def test_stores_ic_text_with_whisper_prefix(self, test_db, temp_db_path):
        svc = _make_translation_service("I have information.")
        world = _make_world(svc)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            stored = []
            with patch("mud_server.core.engine.database") as mock_db:
                self._patch_whisper_db(mock_db)
                mock_db.add_chat_message.side_effect = lambda u, m, r, **kw: stored.append(m) or True
                engine.whisper("Mira", "Kael", "i have information", world_id="daily_undertaking")

        # Prefix uses resolved sender name and target
        assert stored[0] == "[WHISPER: Mira → Kael] I have information."

    def test_falls_back_to_ooc_with_whisper_prefix(self, test_db, temp_db_path):
        svc = _make_translation_service(None)
        world = _make_world(svc)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            stored = []
            with patch("mud_server.core.engine.database") as mock_db:
                self._patch_whisper_db(mock_db)
                mock_db.add_chat_message.side_effect = lambda u, m, r, **kw: stored.append(m) or True
                engine.whisper("Mira", "Kael", "i have information", world_id="daily_undertaking")

        assert stored[0] == "[WHISPER: Mira → Kael] i have information"

    def test_translation_called_with_whisper_channel(self, test_db, temp_db_path):
        svc = _make_translation_service("IC whisper")
        world = _make_world(svc)
        engine = _make_engine(world)

        with use_test_database(temp_db_path):
            with patch("mud_server.core.engine.database") as mock_db:
                self._patch_whisper_db(mock_db)
                engine.whisper("Mira", "Kael", "hello", world_id="daily_undertaking")

        svc.translate.assert_called_once_with(
            character_name="Mira",
            ooc_message="hello",
            channel="whisper",
        )


# ── World loading ─────────────────────────────────────────────────────────────


class TestWorldTranslationEnabled:
    """Integration-level smoke tests for translation_layer_enabled()."""

    def test_world_translation_disabled_by_default(self, tmp_path):
        """A world.json without a translation_layer block → disabled."""
        import json

        from mud_server.core.world import World

        world_json = tmp_path / "world.json"
        world_json.write_text(json.dumps({
            "name": "Test World",
            "default_spawn": {"zone": "test_zone", "room": "spawn"},
            "zones": [],
            "global_items": {},
        }))
        (tmp_path / "zones").mkdir()
        world = World(world_root=tmp_path)
        assert world.translation_layer_enabled() is False
        assert world.get_translation_service() is None

    def test_world_translation_disabled_when_enabled_is_false(self, tmp_path):
        """A translation_layer block with enabled=false → disabled."""
        import json

        from mud_server.core.world import World

        world_json = tmp_path / "world.json"
        world_json.write_text(json.dumps({
            "name": "Test World",
            "default_spawn": {"zone": "test_zone", "room": "spawn"},
            "zones": [],
            "global_items": {},
            "translation_layer": {"enabled": False},
        }))
        (tmp_path / "zones").mkdir()
        world = World(world_root=tmp_path)
        assert world.translation_layer_enabled() is False
