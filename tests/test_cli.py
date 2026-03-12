"""
Unit tests for CLI module (mud_server/cli.py).

Tests cover:
- Command parsing
- init-db command
- create-superuser command (with env vars and interactive)
- Environment variable handling
"""

import argparse
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mud_server import cli
from tests.constants import TEST_PASSWORD

# ============================================================================
# ENVIRONMENT VARIABLE TESTS
# ============================================================================


@pytest.mark.unit
def test_get_superuser_credentials_from_env_both_set():
    """Test getting credentials when both env vars are set."""
    with patch.dict("os.environ", {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": "secret123"}):
        result = cli.get_superuser_credentials_from_env()
        assert result == ("admin", "secret123")


@pytest.mark.unit
def test_get_superuser_credentials_from_env_user_missing():
    """Test getting credentials when MUD_ADMIN_USER is missing."""
    with patch.dict("os.environ", {"MUD_ADMIN_PASSWORD": "secret123"}, clear=True):
        result = cli.get_superuser_credentials_from_env()
        assert result is None


@pytest.mark.unit
def test_get_superuser_credentials_from_env_password_missing():
    """Test getting credentials when MUD_ADMIN_PASSWORD is missing."""
    with patch.dict("os.environ", {"MUD_ADMIN_USER": "admin"}, clear=True):
        result = cli.get_superuser_credentials_from_env()
        assert result is None


@pytest.mark.unit
def test_get_superuser_credentials_from_env_neither_set():
    """Test getting credentials when neither env var is set."""
    with patch.dict("os.environ", {}, clear=True):
        result = cli.get_superuser_credentials_from_env()
        assert result is None


# ============================================================================
# INIT-DB COMMAND TESTS
# ============================================================================


@pytest.mark.unit
def test_cmd_init_db_success():
    """Test init-db command succeeds."""
    with patch("mud_server.db.database.init_database") as mock_init:
        args = argparse.Namespace()
        result = cli.cmd_init_db(args)

        assert result == 0
        mock_init.assert_called_once()


@pytest.mark.unit
def test_cmd_init_db_error():
    """Test init-db command handles errors."""
    with patch("mud_server.db.database.init_database", side_effect=Exception("DB error")):
        args = argparse.Namespace()
        result = cli.cmd_init_db(args)

        assert result == 1


@pytest.mark.unit
def test_cmd_init_db_migrate_success(tmp_path, monkeypatch):
    """Test init-db migrate runs the migration script entry point."""
    db_path = tmp_path / "mud.db"
    db_path.write_text("test")

    monkeypatch.setattr(
        "mud_server.config.config",
        SimpleNamespace(database=SimpleNamespace(absolute_path=db_path)),
    )

    class DummyLoader:
        def exec_module(self, module):
            module.main = lambda: 0

    monkeypatch.setattr(
        "importlib.util.spec_from_file_location",
        lambda name, path: SimpleNamespace(loader=DummyLoader()),
    )
    monkeypatch.setattr("importlib.util.module_from_spec", lambda spec: SimpleNamespace())

    args = argparse.Namespace(migrate=True)
    result = cli.cmd_init_db(args)

    assert result == 0


@pytest.mark.unit
def test_cmd_init_db_migrate_missing_script(tmp_path, monkeypatch):
    """Test init-db migrate fails when script is missing."""
    db_path = tmp_path / "mud.db"
    db_path.write_text("test")

    monkeypatch.setattr(
        "mud_server.config.config",
        SimpleNamespace(database=SimpleNamespace(absolute_path=db_path)),
    )

    from pathlib import Path

    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path.name == "migrate_to_multiworld.py":
            return False
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)

    args = argparse.Namespace(migrate=True)
    result = cli.cmd_init_db(args)

    assert result == 1


# ============================================================================
# CREATE-SUPERUSER COMMAND TESTS
# ============================================================================


@pytest.mark.unit
def test_cmd_create_superuser_from_env_vars():
    """Test create-superuser uses environment variables."""
    with patch("mud_server.db.database.init_database"):
        with patch("mud_server.db.database.user_exists", return_value=False):
            with patch("mud_server.db.database.create_user_with_password", return_value=True):
                # Password must meet STANDARD policy: 12+ chars, no sequences (123, abc)
                with patch.dict(
                    "os.environ",
                    {"MUD_ADMIN_USER": "envadmin", "MUD_ADMIN_PASSWORD": TEST_PASSWORD},
                ):
                    args = argparse.Namespace()
                    result = cli.cmd_create_superuser(args)

                    assert result == 0


@pytest.mark.unit
def test_cmd_create_superuser_user_exists():
    """Test create-superuser fails if user already exists."""
    with patch("mud_server.db.database.init_database"):
        with patch("mud_server.db.database.user_exists", return_value=True):
            # Use valid password to ensure we test the "user exists" failure path
            with patch.dict(
                "os.environ",
                {"MUD_ADMIN_USER": "existing", "MUD_ADMIN_PASSWORD": TEST_PASSWORD},
            ):
                args = argparse.Namespace()
                result = cli.cmd_create_superuser(args)

                assert result == 1


@pytest.mark.unit
def test_cmd_create_superuser_short_password():
    """Test create-superuser fails with short password."""
    with patch("mud_server.db.database.init_database"):
        with patch("mud_server.db.database.user_exists", return_value=False):
            with patch.dict(
                "os.environ", {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": "short"}
            ):
                args = argparse.Namespace()
                result = cli.cmd_create_superuser(args)

                assert result == 1


@pytest.mark.unit
def test_cmd_create_superuser_no_env_not_interactive():
    """Test create-superuser fails when no env vars and not interactive."""
    with patch("mud_server.db.database.init_database"):
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdin.isatty", return_value=False):
                args = argparse.Namespace()
                result = cli.cmd_create_superuser(args)

                assert result == 1


@pytest.mark.unit
def test_cmd_create_superuser_interactive(monkeypatch):
    """Test create-superuser prompts interactively when no env vars."""
    with patch("mud_server.db.database.init_database"):
        with patch("mud_server.db.database.user_exists", return_value=False):
            with patch("mud_server.db.database.create_user_with_password", return_value=True):
                with patch.dict("os.environ", {}, clear=True):
                    with patch("sys.stdin.isatty", return_value=True):
                        # Mock the prompt function with a valid password
                        with patch(
                            "mud_server.cli.prompt_for_credentials",
                            return_value=("interactiveuser", TEST_PASSWORD),
                        ):
                            args = argparse.Namespace()
                            result = cli.cmd_create_superuser(args)

                            assert result == 0


# ============================================================================
# IMPORT-SPECIES-POLICIES COMMAND TESTS
# ============================================================================


@pytest.mark.unit
def test_cmd_import_species_policies_success(monkeypatch) -> None:
    """Import command should return 0 for successful runs without errors."""
    captured_kwargs: dict[str, object] = {}

    def _fake_import(**kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            world_id="pipeworks_web",
            activate=True,
            scanned_files=2,
            imported_count=2,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            activated_count=2,
            activation_skipped_count=0,
            entries=[],
        )

    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_species_blocks_from_legacy_yaml",
        _fake_import,
    )

    args = argparse.Namespace(
        world_id="pipeworks_web",
        actor="importer",
        status="active",
        activate=True,
    )
    result = cli.cmd_import_species_policies(args)

    assert result == 0
    assert captured_kwargs == {
        "world_id": "pipeworks_web",
        "actor": "importer",
        "activate": True,
        "status": "active",
    }


@pytest.mark.unit
def test_cmd_import_species_policies_returns_nonzero_when_errors(monkeypatch) -> None:
    """Import command should return 1 when summary contains per-file errors."""
    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_species_blocks_from_legacy_yaml",
        lambda **kwargs: SimpleNamespace(
            world_id="pipeworks_web",
            activate=False,
            scanned_files=1,
            imported_count=0,
            updated_count=0,
            skipped_count=0,
            error_count=1,
            activated_count=0,
            activation_skipped_count=0,
            entries=[
                SimpleNamespace(
                    source_path="/tmp/broken.yaml",
                    policy_id=None,
                    variant=None,
                    action="error",
                    detail="boom",
                )
            ],
        ),
    )

    args = argparse.Namespace(
        world_id="pipeworks_web",
        actor="importer",
        status="candidate",
        activate=False,
    )
    result = cli.cmd_import_species_policies(args)
    assert result == 1


@pytest.mark.unit
def test_cmd_import_species_policies_uses_default_world_and_actor(monkeypatch) -> None:
    """Import command should fallback to configured world and default actor when blanks are provided."""
    captured_kwargs: dict[str, object] = {}

    def _fake_import(**kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            world_id="pipeworks_web",
            activate=False,
            scanned_files=0,
            imported_count=0,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            activated_count=0,
            activation_skipped_count=0,
            entries=[],
        )

    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.config.config",
        SimpleNamespace(worlds=SimpleNamespace(default_world_id="pipeworks_web")),
    )
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_species_blocks_from_legacy_yaml",
        _fake_import,
    )

    args = argparse.Namespace(
        world_id="  ",
        actor="",
        status="active",
        activate=False,
    )
    result = cli.cmd_import_species_policies(args)

    assert result == 0
    assert captured_kwargs == {
        "world_id": "pipeworks_web",
        "actor": "policy-importer",
        "activate": False,
        "status": "active",
    }


@pytest.mark.unit
def test_cmd_import_species_policies_handles_policy_service_error(monkeypatch) -> None:
    """Import command should return 1 and handle service-specific failures."""
    from mud_server.services.policy_service import PolicyServiceError

    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)

    def _raise_policy_error(**_kwargs):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_IMPORT_STATUS_INVALID",
            detail="invalid status",
        )

    monkeypatch.setattr(
        "mud_server.services.policy_service.import_species_blocks_from_legacy_yaml",
        _raise_policy_error,
    )

    args = argparse.Namespace(
        world_id="pipeworks_web",
        actor="importer",
        status="active",
        activate=True,
    )
    assert cli.cmd_import_species_policies(args) == 1


@pytest.mark.unit
def test_cmd_import_species_policies_handles_unexpected_exception(monkeypatch) -> None:
    """Import command should return 1 for non-service exceptions."""
    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_species_blocks_from_legacy_yaml",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    args = argparse.Namespace(
        world_id="pipeworks_web",
        actor="importer",
        status="active",
        activate=True,
    )
    assert cli.cmd_import_species_policies(args) == 1


@pytest.mark.unit
def test_main_import_species_policies_routes_command(monkeypatch) -> None:
    """Main parser should route import-species-policies to the command handler."""
    monkeypatch.setattr("mud_server.cli.cmd_import_species_policies", lambda args: 0)
    with patch("sys.argv", ["mud-server", "import-species-policies"]):
        assert cli.main() == 0


# ============================================================================
# IMPORT-LAYER2-POLICIES COMMAND TESTS
# ============================================================================


@pytest.mark.unit
def test_cmd_import_layer2_policies_success(monkeypatch) -> None:
    """Layer 2 import command should return 0 for successful runs without errors."""
    captured_kwargs: dict[str, object] = {}

    def _fake_import(**kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            world_id="pipeworks_web",
            activate=True,
            scanned_descriptor_files=1,
            scanned_registry_files=2,
            imported_count=2,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            activated_count=2,
            activation_skipped_count=0,
            entries=[],
        )

    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_layer2_policies_from_legacy_files",
        _fake_import,
    )

    args = argparse.Namespace(
        world_id="pipeworks_web",
        actor="importer",
        status="active",
        activate=True,
    )
    result = cli.cmd_import_layer2_policies(args)

    assert result == 0
    assert captured_kwargs == {
        "world_id": "pipeworks_web",
        "actor": "importer",
        "activate": True,
        "status": "active",
    }


@pytest.mark.unit
def test_cmd_import_layer2_policies_returns_nonzero_when_errors(monkeypatch) -> None:
    """Layer 2 import command should return 1 when summary contains per-file errors."""
    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_layer2_policies_from_legacy_files",
        lambda **kwargs: SimpleNamespace(
            world_id="pipeworks_web",
            activate=False,
            scanned_descriptor_files=1,
            scanned_registry_files=1,
            imported_count=0,
            updated_count=0,
            skipped_count=0,
            error_count=1,
            activated_count=0,
            activation_skipped_count=0,
            entries=[
                SimpleNamespace(
                    source_path="/tmp/registry.yaml",
                    policy_id=None,
                    variant=None,
                    action="error",
                    detail="boom",
                )
            ],
        ),
    )

    args = argparse.Namespace(
        world_id="pipeworks_web",
        actor="importer",
        status="candidate",
        activate=False,
    )
    assert cli.cmd_import_layer2_policies(args) == 1


@pytest.mark.unit
def test_cmd_import_layer2_policies_handles_policy_service_error(monkeypatch) -> None:
    """Layer 2 import command should return 1 and handle service-specific failures."""
    from mud_server.services.policy_service import PolicyServiceError

    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)

    def _raise_policy_error(**_kwargs):
        raise PolicyServiceError(
            status_code=422,
            code="POLICY_LAYER2_SOURCE_NOT_FOUND",
            detail="missing source",
        )

    monkeypatch.setattr(
        "mud_server.services.policy_service.import_layer2_policies_from_legacy_files",
        _raise_policy_error,
    )

    args = argparse.Namespace(
        world_id="pipeworks_web",
        actor="importer",
        status="active",
        activate=True,
    )
    assert cli.cmd_import_layer2_policies(args) == 1


@pytest.mark.unit
def test_cmd_import_layer2_policies_handles_unexpected_exception(monkeypatch) -> None:
    """Layer 2 import command should return 1 for non-service exceptions."""
    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_layer2_policies_from_legacy_files",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    args = argparse.Namespace(
        world_id="pipeworks_web",
        actor="importer",
        status="active",
        activate=True,
    )
    assert cli.cmd_import_layer2_policies(args) == 1


@pytest.mark.unit
def test_cmd_import_layer2_policies_uses_default_world_and_actor(monkeypatch) -> None:
    """Layer 2 import command should fallback to configured world and default actor."""
    captured_kwargs: dict[str, object] = {}

    def _fake_import(**kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            world_id="pipeworks_web",
            activate=False,
            scanned_descriptor_files=0,
            scanned_registry_files=0,
            imported_count=0,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            activated_count=0,
            activation_skipped_count=0,
            entries=[],
        )

    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.config.config",
        SimpleNamespace(worlds=SimpleNamespace(default_world_id="pipeworks_web")),
    )
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_layer2_policies_from_legacy_files",
        _fake_import,
    )

    args = argparse.Namespace(
        world_id=" ",
        actor="",
        status="active",
        activate=False,
    )
    result = cli.cmd_import_layer2_policies(args)
    assert result == 0
    assert captured_kwargs == {
        "world_id": "pipeworks_web",
        "actor": "policy-importer",
        "activate": False,
        "status": "active",
    }


@pytest.mark.unit
def test_main_import_layer2_policies_routes_command(monkeypatch) -> None:
    """Main parser should route import-layer2-policies to the command handler."""
    monkeypatch.setattr("mud_server.cli.cmd_import_layer2_policies", lambda args: 0)
    with patch("sys.argv", ["mud-server", "import-layer2-policies"]):
        assert cli.main() == 0


# ============================================================================
# MAIN ENTRY POINT TESTS
# ============================================================================


@pytest.mark.unit
def test_main_no_command(capsys):
    """Test main with no command shows help."""
    with patch("sys.argv", ["mud-server"]):
        result = cli.main()
        assert result == 0


@pytest.mark.unit
def test_main_init_db():
    """Test main routes to init-db command."""
    with patch("sys.argv", ["mud-server", "init-db"]):
        with patch("mud_server.db.database.init_database"):
            result = cli.main()
            assert result == 0


@pytest.mark.unit
def test_main_create_superuser():
    """Test main routes to create-superuser command."""
    with patch("sys.argv", ["mud-server", "create-superuser"]):
        with patch("mud_server.db.database.init_database"):
            with patch("mud_server.db.database.user_exists", return_value=False):
                with patch("mud_server.db.database.create_user_with_password", return_value=True):
                    with patch.dict(
                        "os.environ",
                        {"MUD_ADMIN_USER": "admin", "MUD_ADMIN_PASSWORD": TEST_PASSWORD},
                    ):
                        result = cli.main()
                        assert result == 0
