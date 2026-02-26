"""Unit tests for CharacterProfileBuilder."""

import pytest

from mud_server.translation.profile_builder import CharacterProfileBuilder

WORLD_ID = "test_world"


@pytest.fixture
def builder():
    return CharacterProfileBuilder(
        world_id=WORLD_ID,
        active_axes=["demeanor", "health"],
    )


def _make_axis_state(axes: list[dict]) -> dict:
    """Build a minimal axis_state dict as returned by get_character_axis_state."""
    return {
        "world_id": WORLD_ID,
        "axes": axes,
        "base_state": None,
        "current_state": None,
    }


class TestConstructorValidation:
    def test_empty_world_id_raises(self):
        with pytest.raises(ValueError, match="world_id"):
            CharacterProfileBuilder(world_id="", active_axes=[])

    def test_blank_world_id_raises(self):
        with pytest.raises(ValueError, match="world_id"):
            CharacterProfileBuilder(world_id="   ", active_axes=[])

    def test_valid_world_id_does_not_raise(self):
        CharacterProfileBuilder(world_id="some_world", active_axes=[])


class TestBuildSuccess:
    def test_returns_profile_with_expected_keys(self, builder, monkeypatch):
        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_by_name_in_world",
            lambda name, world_id: {"id": 7, "name": name, "world_id": world_id},
        )
        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_axis_state",
            lambda cid: _make_axis_state([
                {"axis_name": "demeanor", "axis_score": 0.87, "axis_label": "proud"},
                {"axis_name": "health", "axis_score": 0.72, "axis_label": "hale"},
            ]),
        )
        profile = builder.build("Mira Voss")
        assert profile is not None
        assert profile["character_name"] == "Mira Voss"
        assert profile["demeanor_label"] == "proud"
        assert profile["demeanor_score"] == pytest.approx(0.87)
        assert profile["health_label"] == "hale"
        assert profile["health_score"] == pytest.approx(0.72)

    def test_missing_active_axis_defaults_to_unknown(self, builder, monkeypatch):
        """An axis in active_axes that has no DB score defaults to unknown/0.0."""
        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_by_name_in_world",
            lambda name, world_id: {"id": 7, "name": name, "world_id": world_id},
        )
        # Only "demeanor" is present; "health" is missing from the axis state.
        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_axis_state",
            lambda cid: _make_axis_state([
                {"axis_name": "demeanor", "axis_score": 0.87, "axis_label": "proud"},
            ]),
        )
        profile = builder.build("Mira Voss")
        assert profile["health_label"] == "unknown"
        assert profile["health_score"] == pytest.approx(0.0)

    def test_empty_active_axes_includes_all_character_axes(self, monkeypatch):
        """When active_axes=[], all axes present for the character are included."""
        all_axes_builder = CharacterProfileBuilder(world_id=WORLD_ID, active_axes=[])
        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_by_name_in_world",
            lambda name, world_id: {"id": 1, "name": name, "world_id": world_id},
        )
        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_axis_state",
            lambda cid: _make_axis_state([
                {"axis_name": "demeanor", "axis_score": 0.5, "axis_label": "neutral"},
                {"axis_name": "wealth", "axis_score": 0.1, "axis_label": "destitute"},
            ]),
        )
        profile = all_axes_builder.build("Someone")
        assert "demeanor_label" in profile
        assert "wealth_label" in profile


class TestBuildFailures:
    def test_character_not_found_returns_none(self, builder, monkeypatch):
        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_by_name_in_world",
            lambda name, world_id: None,
        )
        assert builder.build("Ghost") is None

    def test_no_axis_state_returns_none(self, builder, monkeypatch):
        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_by_name_in_world",
            lambda name, world_id: {"id": 5, "name": name, "world_id": world_id},
        )
        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_axis_state",
            lambda cid: None,
        )
        assert builder.build("SomeCharacter") is None

    def test_world_scope_is_passed_to_db(self, builder, monkeypatch):
        """Verifies that the world-scoped lookup is called (not the bare name lookup)."""
        calls = []

        def scoped_lookup(name, world_id):
            calls.append((name, world_id))
            return None

        monkeypatch.setattr(
            "mud_server.translation.profile_builder.database.get_character_by_name_in_world",
            scoped_lookup,
        )
        builder.build("SomeCharacter")
        assert len(calls) == 1
        assert calls[0] == ("SomeCharacter", WORLD_ID)
