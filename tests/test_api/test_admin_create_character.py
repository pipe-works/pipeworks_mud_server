"""Tests for the admin character provisioning endpoint."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from mud_server.api.routes import admin
from mud_server.config import use_test_database
from mud_server.db import database
from mud_server.db.errors import DatabaseOperationContext, DatabaseWriteError
from mud_server.services import character_provisioning
from mud_server.services.character_provisioning import CharacterProvisioningResult
from tests.constants import TEST_PASSWORD


@pytest.mark.unit
def test_fetch_generated_name_returns_none_when_integration_disabled(monkeypatch):
    """Name helper should short-circuit when namegen integration is disabled."""
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", False)

    name, error = character_provisioning._fetch_generated_name(seed=101)

    assert name is None
    assert error == "Name generation integration is disabled."


@pytest.mark.unit
def test_fetch_generated_name_returns_payload_for_valid_response(monkeypatch):
    """Name helper should parse the first generated name from upstream payload."""
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations, "namegen_base_url", "https://name.example.org/"
    )
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_timeout_seconds", 4.5)

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {"names": ["Sera"]}
    post_mock = Mock(return_value=fake_response)
    monkeypatch.setattr(character_provisioning.requests, "post", post_mock)

    name, error = character_provisioning._fetch_generated_name(seed=303)

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
def test_fetch_generated_name_handles_empty_base_url(monkeypatch):
    """Name helper should fail fast when integration URL is blank."""
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_base_url", "   ")

    name, error = character_provisioning._fetch_generated_name(seed=12)

    assert name is None
    assert error == "Name generation integration is enabled but no base URL is configured."


@pytest.mark.unit
def test_fetch_generated_name_handles_non_200(monkeypatch):
    """Name helper should surface upstream HTTP status failures."""
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations, "namegen_base_url", "https://name.example.org"
    )

    fake_response = Mock(status_code=503)
    fake_response.json.return_value = {}
    monkeypatch.setattr(character_provisioning.requests, "post", Mock(return_value=fake_response))

    name, error = character_provisioning._fetch_generated_name(seed=12)

    assert name is None
    assert error == "Name generation API returned HTTP 503."


@pytest.mark.unit
def test_fetch_generated_name_handles_non_object_payload(monkeypatch):
    """Name helper should reject non-dict JSON payloads."""
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations, "namegen_base_url", "https://name.example.org"
    )

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = ["not", "an", "object"]
    monkeypatch.setattr(character_provisioning.requests, "post", Mock(return_value=fake_response))

    name, error = character_provisioning._fetch_generated_name(seed=88)

    assert name is None
    assert error == "Name generation API returned a non-object payload."


@pytest.mark.unit
def test_fetch_generated_name_handles_invalid_name_list(monkeypatch):
    """Name helper should reject malformed name arrays."""
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations, "namegen_base_url", "https://name.example.org"
    )

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {"names": [123]}
    monkeypatch.setattr(character_provisioning.requests, "post", Mock(return_value=fake_response))

    name, error = character_provisioning._fetch_generated_name(seed=88)

    assert name is None
    assert error == "Name generation API did not return a valid name."


@pytest.mark.unit
def test_fetch_generated_name_handles_blank_name(monkeypatch):
    """Name helper should reject blank first entry values."""
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations, "namegen_base_url", "https://name.example.org"
    )

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {"names": ["   "]}
    monkeypatch.setattr(character_provisioning.requests, "post", Mock(return_value=fake_response))

    name, error = character_provisioning._fetch_generated_name(seed=88)

    assert name is None
    assert error == "Name generation API returned an empty name."


@pytest.mark.unit
def test_fetch_generated_name_handles_request_exception(monkeypatch):
    """Network-layer errors should become an availability message."""
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations, "namegen_base_url", "https://name.example.org"
    )

    def _boom(*_args, **_kwargs):  # noqa: ANN002,ANN003 - test double
        raise character_provisioning.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(character_provisioning.requests, "post", _boom)

    name, error = character_provisioning._fetch_generated_name(seed=12)

    assert name is None
    assert error == "Name generation API unavailable."


@pytest.mark.unit
def test_fetch_generated_name_handles_invalid_json(monkeypatch):
    """JSON parsing errors should return a controlled message."""
    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations, "namegen_base_url", "https://name.example.org"
    )

    fake_response = Mock(status_code=200)
    fake_response.json.side_effect = ValueError("invalid")
    monkeypatch.setattr(character_provisioning.requests, "post", Mock(return_value=fake_response))

    name, error = character_provisioning._fetch_generated_name(seed=12)

    assert name is None
    assert error == "Name generation API returned invalid JSON."


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

    monkeypatch.setattr(character_provisioning.config.integrations, "namegen_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations, "namegen_base_url", "https://name.example.org"
    )
    monkeypatch.setattr(character_provisioning.requests, "post", _fake_post)

    full_name, error = character_provisioning.fetch_generated_full_name(seed=441)

    assert error is None
    assert full_name == "Elira Varyn"
    assert [entry["class_key"] for entry in call_payloads] == ["first_name", "last_name"]
    assert [entry["seed"] for entry in call_payloads] == [441, 442]


@pytest.mark.unit
def test_fetch_generated_full_name_surfaces_first_name_error(monkeypatch):
    """Full-name helper should stop when first-name generation fails."""
    monkeypatch.setattr(
        character_provisioning,
        "_fetch_generated_name",
        lambda _seed, class_key="first_name": (None, f"{class_key} failed"),
    )

    full_name, error = character_provisioning.fetch_generated_full_name(seed=51)

    assert full_name is None
    assert error == "first_name failed"


@pytest.mark.unit
def test_fetch_generated_full_name_surfaces_last_name_error(monkeypatch):
    """Full-name helper should report surname generation failures."""

    def _fake(seed, class_key="first_name"):  # noqa: ANN001 - test helper
        if class_key == "first_name":
            return "Ari", None
        return None, "last_name failed"

    monkeypatch.setattr(character_provisioning, "_fetch_generated_name", _fake)

    full_name, error = character_provisioning.fetch_generated_full_name(seed=51)

    assert full_name is None
    assert error == "last_name failed"


@pytest.mark.unit
def test_generate_provisioning_seed_is_non_zero():
    """Provisioning seed helper should never return zero."""
    seed = character_provisioning.generate_provisioning_seed()
    assert isinstance(seed, int)
    assert seed > 0


@pytest.mark.unit
def test_fetch_generated_full_name_rejects_non_split_name(monkeypatch):
    """Full-name helper should reject outputs without first/last separation."""

    def _fake(seed, class_key="first_name"):  # noqa: ANN001 - test helper
        _ = seed
        _ = class_key
        return " ", None

    monkeypatch.setattr(character_provisioning, "_fetch_generated_name", _fake)

    full_name, error = character_provisioning.fetch_generated_full_name(seed=51)

    assert full_name is None
    assert error == "Name generation API returned an invalid full name."


@pytest.mark.unit
def test_fetch_entity_state_for_seed_disabled_returns_none(monkeypatch):
    """Entity helper should no-op cleanly when integration is disabled."""
    monkeypatch.setattr(character_provisioning.config.integrations, "entity_state_enabled", False)

    payload, error = character_provisioning.fetch_entity_state_for_seed(seed=1001)

    assert payload is None
    assert error is None


@pytest.mark.unit
def test_fetch_entity_state_for_seed_handles_blank_base_url(monkeypatch):
    """Entity helper should fail fast when base URL config is missing."""
    monkeypatch.setattr(character_provisioning.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(character_provisioning.config.integrations, "entity_state_base_url", " ")

    payload, error = character_provisioning.fetch_entity_state_for_seed(seed=1001)

    assert payload is None
    assert error == "Entity state integration is enabled but no base URL is configured."


@pytest.mark.unit
def test_fetch_entity_state_for_seed_handles_non_200(monkeypatch):
    """Entity helper should propagate upstream status failures."""
    monkeypatch.setattr(character_provisioning.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )

    fake_response = Mock(status_code=500)
    fake_response.json.return_value = {}
    monkeypatch.setattr(character_provisioning.requests, "post", Mock(return_value=fake_response))

    payload, error = character_provisioning.fetch_entity_state_for_seed(seed=1001)

    assert payload is None
    assert error == "Entity state API returned HTTP 500."


@pytest.mark.unit
def test_fetch_entity_state_for_seed_handles_non_object(monkeypatch):
    """Entity helper should reject non-dictionary payloads."""
    monkeypatch.setattr(character_provisioning.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = ["bad"]
    monkeypatch.setattr(character_provisioning.requests, "post", Mock(return_value=fake_response))

    payload, error = character_provisioning.fetch_entity_state_for_seed(seed=1001)

    assert payload is None
    assert error == "Entity state API returned a non-object payload."


@pytest.mark.unit
def test_fetch_entity_state_for_seed_handles_request_exception(monkeypatch):
    """Entity helper should map network failures to a stable error message."""
    monkeypatch.setattr(character_provisioning.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )

    def _boom(*_args, **_kwargs):  # noqa: ANN002,ANN003 - test double
        raise character_provisioning.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(character_provisioning.requests, "post", _boom)

    payload, error = character_provisioning.fetch_entity_state_for_seed(seed=1001)

    assert payload is None
    assert error == "Entity state API unavailable."


@pytest.mark.unit
def test_fetch_entity_state_for_seed_handles_invalid_json(monkeypatch):
    """Entity helper should guard against invalid JSON payloads."""
    monkeypatch.setattr(character_provisioning.config.integrations, "entity_state_enabled", True)
    monkeypatch.setattr(
        character_provisioning.config.integrations,
        "entity_state_base_url",
        "https://entity.example.org",
    )

    fake_response = Mock(status_code=200)
    fake_response.json.side_effect = ValueError("invalid")
    monkeypatch.setattr(character_provisioning.requests, "post", Mock(return_value=fake_response))

    payload, error = character_provisioning.fetch_entity_state_for_seed(seed=1001)

    assert payload is None
    assert error == "Entity state API returned invalid JSON."


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

            def _fake_provision(*, user_id: int, world_id: str):
                assert (
                    database.create_character_for_user(
                        user_id,
                        "Admin Generated",
                        world_id=world_id,
                        state_seed=98765,
                    )
                    is True
                )
                created = database.get_character_by_name("Admin Generated")
                assert created is not None
                return CharacterProvisioningResult(
                    success=True,
                    reason="ok",
                    message="Character created successfully.",
                    character_id=int(created["id"]),
                    character_name="Admin Generated",
                    world_id=world_id,
                    seed=98765,
                    entity_state=payload,
                    entity_state_error=None,
                )

            mp.setattr(admin, "provision_generated_character_for_user", _fake_provision)

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
        assert body["entity_state"] == payload
        assert body["entity_state_error"] is None

        created = database.get_character_by_name("Admin Generated")
        assert created is not None
        assert created["world_id"] == "pipeworks_web"


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
            mp.setattr(
                admin,
                "provision_generated_character_for_user",
                lambda **_kwargs: CharacterProvisioningResult(
                    success=False,
                    reason="name_generation_failed",
                    message="Name generation API unavailable.",
                ),
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
def test_admin_create_character_validates_required_fields(
    test_client, test_db, temp_db_path, db_with_users
):
    """Provisioning endpoint should reject blank target username or world id."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        missing_user = test_client.post(
            "/admin/user/create-character",
            json={
                "session_id": session_id,
                "target_username": " ",
                "world_id": "pipeworks_web",
            },
        )
        assert missing_user.status_code == 400

        missing_world = test_client.post(
            "/admin/user/create-character",
            json={
                "session_id": session_id,
                "target_username": "testplayer",
                "world_id": " ",
            },
        )
        assert missing_world.status_code == 400


@pytest.mark.api
def test_admin_create_character_rejects_unknown_user(
    test_client, test_db, temp_db_path, db_with_users
):
    """Provisioning endpoint should return 404 for missing accounts."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        response = test_client.post(
            "/admin/user/create-character",
            json={
                "session_id": session_id,
                "target_username": "no_such_user",
                "world_id": "pipeworks_web",
            },
        )

    assert response.status_code == 404


@pytest.mark.api
def test_admin_create_character_rejects_inactive_world(
    test_client, test_db, temp_db_path, db_with_users
):
    """Provisioning endpoint should reject inactive world targets."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE worlds SET is_active = 0 WHERE id = ?", ("pipeworks_web",))
        conn.commit()
        conn.close()

        response = test_client.post(
            "/admin/user/create-character",
            json={
                "session_id": session_id,
                "target_username": "testplayer",
                "world_id": "pipeworks_web",
            },
        )

    assert response.status_code == 409


@pytest.mark.api
def test_admin_create_character_rejects_hierarchy_violation(
    test_client, test_db, temp_db_path, db_with_users
):
    """Admins should not create characters for higher-role accounts."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        response = test_client.post(
            "/admin/user/create-character",
            json={
                "session_id": session_id,
                "target_username": "testsuperuser",
                "world_id": "pipeworks_web",
            },
        )

    assert response.status_code == 403


@pytest.mark.api
def test_admin_create_character_endpoint_retries_name_collision(
    test_client, test_db, temp_db_path, db_with_users
):
    """Character provisioning should retry with the next seed on name collisions."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testadmin", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        # Force first attempt to collide, second to succeed.
        assert database.character_exists("Collision Name") is False
        player_id = database.get_user_id("testplayer")
        assert player_id is not None
        assert database.create_character_for_user(
            player_id, "Collision Name", world_id="pipeworks_web"
        )

        with pytest.MonkeyPatch.context() as mp:

            def _fake_provision(*, user_id: int, world_id: str):
                assert (
                    database.create_character_for_user(
                        user_id,
                        "Resolved Name",
                        world_id=world_id,
                        state_seed=445,
                    )
                    is True
                )
                created = database.get_character_by_name("Resolved Name")
                assert created is not None
                return CharacterProvisioningResult(
                    success=True,
                    reason="ok",
                    message="Character created successfully.",
                    character_id=int(created["id"]),
                    character_name="Resolved Name",
                    world_id=world_id,
                    seed=445,
                    entity_state=None,
                    entity_state_error=None,
                )

            mp.setattr(admin, "provision_generated_character_for_user", _fake_provision)

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
        assert body["character_name"] == "Resolved Name"
        assert body["seed"] == 445


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


@pytest.mark.api
def test_manage_character_rejects_already_tombstoned_character(
    test_client, test_db, temp_db_path, db_with_users
):
    """Repeated tombstone calls should return a conflict."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        assert database.create_character_for_user(
            user_id, "Already Tombstoned", world_id="pipeworks_web"
        )
        character = database.get_character_by_name("Already Tombstoned")
        assert character is not None
        assert database.tombstone_character(int(character["id"])) is True

        response = test_client.post(
            "/admin/character/manage",
            json={
                "session_id": session_id,
                "character_id": int(character["id"]),
                "action": "tombstone",
            },
        )

    assert response.status_code == 409


@pytest.mark.api
def test_manage_character_handles_backend_not_found_on_delete(
    test_client, test_db, temp_db_path, db_with_users
):
    """Endpoint should return 404 if deletion reports no removed row."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        assert database.create_character_for_user(
            user_id, "Delete Missing", world_id="pipeworks_web"
        )
        character = database.get_character_by_name("Delete Missing")
        assert character is not None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(database, "delete_character", lambda _cid: False)
            response = test_client.post(
                "/admin/character/manage",
                json={
                    "session_id": session_id,
                    "character_id": int(character["id"]),
                    "action": "delete",
                },
            )

    assert response.status_code == 404


@pytest.mark.api
def test_manage_character_handles_backend_not_found_on_tombstone(
    test_client, test_db, temp_db_path, db_with_users
):
    """Endpoint should return 404 if tombstone reports no updated row."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        assert database.create_character_for_user(
            user_id, "Stone Missing", world_id="pipeworks_web"
        )
        character = database.get_character_by_name("Stone Missing")
        assert character is not None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(database, "tombstone_character", lambda _cid: False)
            response = test_client.post(
                "/admin/character/manage",
                json={
                    "session_id": session_id,
                    "character_id": int(character["id"]),
                    "action": "tombstone",
                },
            )

    assert response.status_code == 404


@pytest.mark.api
def test_manage_character_maps_database_error_to_500(
    test_client, test_db, temp_db_path, db_with_users
):
    """Character management should map typed DB exceptions to HTTP 500."""
    with use_test_database(temp_db_path):
        login = test_client.post(
            "/login", json={"username": "testsuperuser", "password": TEST_PASSWORD}
        )
        session_id = login.json()["session_id"]

        user_id = database.get_user_id("testplayer")
        assert user_id is not None
        assert database.create_character_for_user(
            user_id, "Error Tombstone", world_id="pipeworks_web"
        )
        character = database.get_character_by_name("Error Tombstone")
        assert character is not None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                database,
                "remove_sessions_for_character",
                Mock(
                    side_effect=DatabaseWriteError(
                        context=DatabaseOperationContext(
                            operation="sessions.remove_sessions_for_character"
                        )
                    )
                ),
            )
            response = test_client.post(
                "/admin/character/manage",
                json={
                    "session_id": session_id,
                    "character_id": int(character["id"]),
                    "action": "tombstone",
                },
            )

    assert response.status_code == 500
    assert "character management failed" in response.json()["detail"].lower()
