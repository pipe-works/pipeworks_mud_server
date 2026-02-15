"""Tests for the admin character provisioning endpoint."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from mud_server.api.routes import admin
from mud_server.config import use_test_database
from mud_server.db import database
from tests.constants import TEST_PASSWORD


@pytest.mark.unit
def test_fetch_generated_name_returns_none_when_integration_disabled(monkeypatch):
    """Name helper should short-circuit when namegen integration is disabled."""
    monkeypatch.setattr(admin.config.integrations, "namegen_enabled", False)

    name, error = admin._fetch_generated_name(seed=101)

    assert name is None
    assert error == "Name generation integration is disabled."


@pytest.mark.unit
def test_fetch_generated_name_returns_payload_for_valid_response(monkeypatch):
    """Name helper should parse the first generated name from upstream payload."""
    monkeypatch.setattr(admin.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(admin.config.integrations, "namegen_base_url", "https://name.example.org/")
    monkeypatch.setattr(admin.config.integrations, "namegen_timeout_seconds", 4.5)

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {"names": ["Sera"]}
    post_mock = Mock(return_value=fake_response)
    monkeypatch.setattr(admin.requests, "post", post_mock)

    name, error = admin._fetch_generated_name(seed=303)

    assert error is None
    assert name == "Sera"
    post_mock.assert_called_once_with(
        "https://name.example.org/api/generate",
        json={
            "class_key": "first_name",
            "package_id": 1,
            "syllable_key": "all",
            "generation_count": 1,
            "unique_only": True,
            "output_format": "json",
            "render_style": "title",
            "seed": 303,
        },
        timeout=4.5,
    )


@pytest.mark.unit
def test_fetch_generated_full_name_uses_first_and_last_name_keys(monkeypatch):
    """Full-name helper should combine deterministic first + last lookups."""
    call_payloads = []

    def _fake_post(_url, *, json, timeout):  # noqa: ANN001 - test double
        _ = timeout
        call_payloads.append(dict(json))
        response = Mock(status_code=200)
        if json["class_key"] == "first_name":
            response.json.return_value = {"names": ["Elira"]}
        else:
            response.json.return_value = {"names": ["Varyn"]}
        return response

    monkeypatch.setattr(admin.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(admin.config.integrations, "namegen_base_url", "https://name.example.org")
    monkeypatch.setattr(admin.requests, "post", _fake_post)

    full_name, error = admin._fetch_generated_full_name(seed=441)

    assert error is None
    assert full_name == "Elira Varyn"
    assert [entry["class_key"] for entry in call_payloads] == ["first_name", "last_name"]
    assert [entry["seed"] for entry in call_payloads] == [441, 442]


@pytest.mark.api
def test_admin_create_character_endpoint_success(test_client, test_db, temp_db_path, db_with_users):
    """Admin should provision a character with generated name and entity axis payload."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        payload = {
            "character": {"wealth": "poor"},
            "occupation": {"legitimacy": "illicit"},
        }
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(admin, "_generate_provisioning_seed", lambda: 98765)
            mp.setattr(admin, "_fetch_generated_full_name", lambda _seed: ("Admin Generated", None))
            mp.setattr(admin, "_fetch_entity_state_for_seed", lambda _seed: (payload, None))

            response = test_client.post(
                "/admin/user/create-character",
                json={
                    "session_id": session_id,
                    "target_username": "testplayer",
                    "world_id": "pipeworks_web",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["character_name"] == "Admin Generated"
        assert body["seed"] == 98765
        assert body["entity_state_error"] is None

        created = database.get_character_by_name("Admin Generated")
        assert created is not None
        axis_state = database.get_character_axis_state(int(created["id"]))
        assert axis_state is not None
        labels = {axis["axis_name"]: axis["axis_label"] for axis in axis_state["axes"]}
        assert labels["wealth"] == "poor"
        assert labels["legitimacy"] == "illicit"


@pytest.mark.api
def test_admin_create_character_endpoint_rejects_namegen_failure(
    test_client, test_db, temp_db_path, db_with_users
):
    """Endpoint should return 502 when name generation integration fails."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(admin, "_generate_provisioning_seed", lambda: 123)
            mp.setattr(
                admin,
                "_fetch_generated_full_name",
                lambda _seed: (None, "Name generation API unavailable."),
            )

            response = test_client.post(
                "/admin/user/create-character",
                json={
                    "session_id": session_id,
                    "target_username": "testplayer",
                    "world_id": "pipeworks_web",
                },
            )

        assert response.status_code == 502
        assert "name generation api unavailable" in response.json()["detail"].lower()


@pytest.mark.api
def test_player_cannot_create_character_for_user(test_client, test_db, temp_db_path, db_with_users):
    """Regular players should be denied access to admin character provisioning."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        response = test_client.post(
            "/admin/user/create-character",
            json={
                "session_id": session_id,
                "target_username": "testplayer",
                "world_id": "pipeworks_web",
            },
        )

    assert response.status_code == 403


@pytest.mark.api
def test_superuser_can_tombstone_character(test_client, test_db, temp_db_path, db_with_users):
    """Superuser should be able to tombstone a character via admin endpoint."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        assert database.create_character_for_user(
            user_id, "Disposable Hero", world_id="pipeworks_web"
        )
        character = database.get_character_by_name("Disposable Hero")
        assert character is not None

        response = test_client.post(
            "/admin/character/manage",
            json={
                "session_id": session_id,
                "character_id": int(character["id"]),
                "action": "tombstone",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["action"] == "tombstone"
    updated = database.get_character_by_id(int(character["id"]))
    assert updated is not None
    assert updated["user_id"] is None
    assert updated["name"].startswith(f"tombstone_{character['id']}_")


@pytest.mark.api
def test_superuser_can_permanently_delete_character(
    test_client, test_db, temp_db_path, db_with_users
):
    """Superuser should be able to hard-delete a character."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        assert database.create_character_for_user(
            user_id, "Delete Target", world_id="pipeworks_web"
        )
        character = database.get_character_by_name("Delete Target")
        assert character is not None

        response = test_client.post(
            "/admin/character/manage",
            json={
                "session_id": session_id,
                "character_id": int(character["id"]),
                "action": "delete",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["action"] == "delete"
    assert database.get_character_by_id(int(character["id"])) is None


@pytest.mark.api
def test_admin_cannot_remove_character(test_client, test_db, temp_db_path, db_with_users):
    """Admins must be denied because character removal is superuser-only."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]
        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "Admin Denied", world_id="pipeworks_web")
        character = database.get_character_by_name("Admin Denied")
        assert character is not None

        response = test_client.post(
            "/admin/character/manage",
            json={
                "session_id": session_id,
                "character_id": int(character["id"]),
                "action": "tombstone",
            },
        )

    assert response.status_code == 403


@pytest.mark.api
def test_manage_character_validates_action_and_missing_character(
    test_client, test_db, temp_db_path, db_with_users
):
    """Superuser endpoint should reject invalid actions and missing ids."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        invalid_action = test_client.post(
            "/admin/character/manage",
            json={
                "session_id": session_id,
                "character_id": 1,
                "action": "archive",
            },
        )
        assert invalid_action.status_code == 400

        missing_character = test_client.post(
            "/admin/character/manage",
            json={
                "session_id": session_id,
                "character_id": 999999,
                "action": "delete",
            },
        )
        assert missing_character.status_code == 404
