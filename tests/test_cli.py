"""CLI tests for canonical artifact-only policy workflows.

These tests intentionally cover the post-refactor command surface where legacy
file-import commands were removed and canonical artifact import is the only
bootstrap/import pathway.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from mud_server import cli


@pytest.fixture
def isolated_cli_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep init-db tests away from the repo's real database and backup paths."""
    from mud_server.config import config

    db_path = tmp_path / "mud.db"
    monkeypatch.setattr(config.database, "path", str(db_path))
    return db_path


@pytest.mark.unit
def test_cmd_init_db_success_uses_artifact_bootstrap(
    isolated_cli_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`init-db` should call artifact bootstrap helper and return success."""
    args = argparse.Namespace(migrate=False, skip_policy_import=False)
    monkeypatch.setattr("shutil.copy2", lambda *_args, **_kwargs: None)
    with patch("mud_server.db.database.init_database") as mock_init:
        with patch(
            "mud_server.cli._sync_world_catalog_from_packages_for_init",
            return_value=["pipeworks_web", "daily_undertaking"],
        ) as mock_sync:
            with patch(
                "mud_server.cli._import_registered_world_artifacts_for_init",
                return_value=0,
            ) as mock_bootstrap:
                result = cli.cmd_init_db(args)

    assert result == 0
    mock_init.assert_called_once()
    mock_sync.assert_called_once()
    mock_bootstrap.assert_called_once_with(
        actor="system-bootstrap",
        world_ids=["pipeworks_web", "daily_undertaking"],
    )


@pytest.mark.unit
def test_cmd_init_db_skip_policy_import(
    isolated_cli_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`init-db --skip-policy-import` should bypass artifact bootstrap."""
    args = argparse.Namespace(migrate=False, skip_policy_import=True)
    monkeypatch.setattr("shutil.copy2", lambda *_args, **_kwargs: None)
    with patch("mud_server.db.database.init_database") as mock_init:
        with patch("mud_server.cli._sync_world_catalog_from_packages_for_init") as mock_sync:
            with patch(
                "mud_server.cli._import_registered_world_artifacts_for_init"
            ) as mock_bootstrap:
                result = cli.cmd_init_db(args)

    assert result == 0
    mock_init.assert_called_once()
    mock_sync.assert_not_called()
    mock_bootstrap.assert_not_called()


@pytest.mark.unit
def test_cmd_init_db_returns_error_when_artifact_bootstrap_fails(
    isolated_cli_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`init-db` should return non-zero when artifact bootstrap reports failures."""
    args = argparse.Namespace(migrate=False, skip_policy_import=False)
    monkeypatch.setattr("shutil.copy2", lambda *_args, **_kwargs: None)
    with patch("mud_server.db.database.init_database") as mock_init:
        with patch(
            "mud_server.cli._sync_world_catalog_from_packages_for_init",
            return_value=["pipeworks_web"],
        ):
            with patch(
                "mud_server.cli._import_registered_world_artifacts_for_init",
                return_value=2,
            ):
                result = cli.cmd_init_db(args)

    assert result == 1
    mock_init.assert_called_once()


@pytest.mark.unit
def test_import_registered_world_artifacts_for_init_success(monkeypatch, tmp_path: Path) -> None:
    """Bootstrap helper should import artifact payload for each selected world."""
    export_root = tmp_path / "exports"
    latest_path = export_root / "worlds" / "pipeworks_web" / "world" / "latest.json"
    artifact_path = export_root / "worlds" / "pipeworks_web" / "world" / "publish_deadbeef.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_payload: dict[str, Any] = {
        "world_id": "pipeworks_web",
        "client_profile": None,
        "variants": [],
        "artifact_hash": "",
    }
    artifact_path.write_text(json.dumps(artifact_payload), encoding="utf-8")
    latest_path.write_text(
        json.dumps({"artifact_path": str(artifact_path)}),
        encoding="utf-8",
    )

    monkeypatch.setenv("MUD_POLICY_EXPORTS_ROOT", str(export_root))
    monkeypatch.setattr(
        "mud_server.core.world_registry.WorldRegistry",
        lambda: SimpleNamespace(list_worlds=lambda include_inactive: [{"id": "pipeworks_web"}]),
    )

    captured: dict[str, Any] = {}

    def _fake_import(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            imported_count=1,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            activated_count=1,
            activation_skipped_count=0,
        )

    monkeypatch.setattr(
        "mud_server.services.policy_service.import_published_artifact", _fake_import
    )

    failures = cli._import_registered_world_artifacts_for_init(actor="bootstrap")

    assert failures == 0
    assert captured["actor"] == "bootstrap"
    assert captured["activate"] is True
    assert captured["artifact"]["world_id"] == "pipeworks_web"


@pytest.mark.unit
def test_import_registered_world_artifacts_for_init_counts_invalid_rows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Bootstrap helper should count malformed world rows as failures."""
    monkeypatch.setenv("MUD_POLICY_EXPORTS_ROOT", str(tmp_path / "exports"))
    monkeypatch.setattr(
        "mud_server.core.world_registry.WorldRegistry",
        lambda: SimpleNamespace(list_worlds=lambda include_inactive: [{"name": "missing-id"}]),
    )

    failures = cli._import_registered_world_artifacts_for_init(actor="bootstrap")
    assert failures == 1


@pytest.mark.unit
def test_import_registered_world_artifacts_for_init_skips_missing_latest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Missing latest pointer should not crash bootstrap helper."""
    monkeypatch.setenv("MUD_POLICY_EXPORTS_ROOT", str(tmp_path / "exports"))
    monkeypatch.setattr(
        "mud_server.core.world_registry.WorldRegistry",
        lambda: SimpleNamespace(list_worlds=lambda include_inactive: [{"id": "pipeworks_web"}]),
    )

    failures = cli._import_registered_world_artifacts_for_init(actor="bootstrap")
    assert failures == 0


@pytest.mark.unit
def test_import_registered_world_artifacts_for_init_resolves_stale_absolute_pointer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Bootstrap should recover when latest.json contains stale absolute paths."""
    export_root = tmp_path / "exports"
    latest_path = export_root / "worlds" / "pipeworks_web" / "world" / "latest.json"
    artifact_path = export_root / "worlds" / "pipeworks_web" / "world" / "publish_deadbeef.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_payload: dict[str, Any] = {
        "world_id": "pipeworks_web",
        "client_profile": None,
        "variants": [],
        "artifact_hash": "",
    }
    artifact_path.write_text(json.dumps(artifact_payload), encoding="utf-8")
    latest_path.write_text(
        json.dumps(
            {
                "artifact_path": "/Users/example/old-machine/worlds/pipeworks_web/world/publish_deadbeef.json",
                "artifact_file": "publish_deadbeef.json",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MUD_POLICY_EXPORTS_ROOT", str(export_root))
    monkeypatch.setattr(
        "mud_server.core.world_registry.WorldRegistry",
        lambda: SimpleNamespace(list_worlds=lambda include_inactive: [{"id": "pipeworks_web"}]),
    )

    captured: dict[str, Any] = {}

    def _fake_import(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            imported_count=1,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            activated_count=1,
            activation_skipped_count=0,
        )

    monkeypatch.setattr(
        "mud_server.services.policy_service.import_published_artifact", _fake_import
    )

    failures = cli._import_registered_world_artifacts_for_init(actor="bootstrap")
    assert failures == 0
    assert captured["artifact"]["world_id"] == "pipeworks_web"


@pytest.mark.unit
@pytest.mark.db
def test_sync_world_catalog_from_packages_for_init_upserts_discovered_worlds(
    test_db, monkeypatch, tmp_path: Path
) -> None:
    """World package discovery should upsert world rows for artifact bootstrap."""
    from mud_server.db import facade as database

    worlds_root = tmp_path / "worlds"
    pipeworks_dir = worlds_root / "pipeworks_web"
    daily_dir = worlds_root / "daily_undertaking"
    pipeworks_dir.mkdir(parents=True, exist_ok=True)
    daily_dir.mkdir(parents=True, exist_ok=True)

    (pipeworks_dir / "world.json").write_text(
        json.dumps({"name": "Pipeworks", "description": "Primary world"}),
        encoding="utf-8",
    )
    (daily_dir / "world.json").write_text(
        json.dumps({"name": "Daily Undertaking", "description": "Secondary world"}),
        encoding="utf-8",
    )

    monkeypatch.setattr("mud_server.config.config.worlds.worlds_root", str(worlds_root))

    discovered = cli._sync_world_catalog_from_packages_for_init()
    assert discovered == ["daily_undertaking", "pipeworks_web"]

    world_rows = {row["id"]: row for row in database.list_worlds(include_inactive=True)}
    assert "pipeworks_web" in world_rows
    assert "daily_undertaking" in world_rows
    assert world_rows["daily_undertaking"]["name"] == "Daily Undertaking"


@pytest.mark.unit
def test_cmd_import_policy_artifact_success(monkeypatch, tmp_path: Path) -> None:
    """Artifact import command should return success for valid summaries."""
    artifact_path = tmp_path / "publish.json"
    artifact_path.write_text(
        json.dumps({"world_id": "pipeworks_web", "variants": []}), encoding="utf-8"
    )

    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_published_artifact",
        lambda **kwargs: SimpleNamespace(
            world_id="pipeworks_web",
            client_profile="",
            activate=True,
            item_count=0,
            imported_count=0,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            activated_count=0,
            activation_skipped_count=0,
            manifest_hash="m",
            items_hash="i",
            variants_hash="v",
            artifact_hash="a",
            entries=[],
        ),
    )

    args = argparse.Namespace(artifact_path=str(artifact_path), actor="tester", activate=True)
    result = cli.cmd_import_policy_artifact(args)
    assert result == 0


@pytest.mark.unit
def test_cmd_import_policy_artifact_returns_nonzero_for_entry_errors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Artifact import command should return non-zero when entries include errors."""
    artifact_path = tmp_path / "publish.json"
    artifact_path.write_text(
        json.dumps({"world_id": "pipeworks_web", "variants": []}), encoding="utf-8"
    )

    monkeypatch.setattr("mud_server.db.database.init_database", lambda **kwargs: None)
    monkeypatch.setattr(
        "mud_server.services.policy_service.import_published_artifact",
        lambda **kwargs: SimpleNamespace(
            world_id="pipeworks_web",
            client_profile="",
            activate=True,
            item_count=1,
            imported_count=0,
            updated_count=0,
            skipped_count=0,
            error_count=1,
            activated_count=0,
            activation_skipped_count=0,
            manifest_hash="m",
            items_hash="i",
            variants_hash="v",
            artifact_hash="a",
            entries=[
                SimpleNamespace(
                    policy_id="species_block:image.blocks.species:goblin",
                    variant="v1",
                    action="error",
                    detail="bad payload",
                )
            ],
        ),
    )

    args = argparse.Namespace(artifact_path=str(artifact_path), actor="tester", activate=True)
    result = cli.cmd_import_policy_artifact(args)
    assert result == 1


@pytest.mark.unit
def test_cmd_import_policy_artifact_missing_file_returns_nonzero() -> None:
    """Artifact import command should fail fast for missing files."""
    args = argparse.Namespace(
        artifact_path="/tmp/does-not-exist.json",
        actor="tester",
        activate=True,
    )
    assert cli.cmd_import_policy_artifact(args) == 1


@pytest.mark.unit
def test_main_routes_import_policy_artifact_command(monkeypatch, tmp_path: Path) -> None:
    """Main parser should route import-policy-artifact to command handler."""
    called = {"value": False}

    def _fake_handler(args):
        called["value"] = True
        assert args.artifact_path == str(tmp_path / "publish.json")
        return 0

    monkeypatch.setattr("mud_server.cli.cmd_import_policy_artifact", _fake_handler)
    with patch(
        "sys.argv",
        ["mud-server", "import-policy-artifact", "--artifact-path", str(tmp_path / "publish.json")],
    ):
        assert cli.main() == 0
    assert called["value"] is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "legacy_command",
    [
        "import-species-policies",
        "import-layer2-policies",
        "import-tone-prompt-policies",
        "import-world-policies",
    ],
)
def test_main_rejects_removed_legacy_import_commands(legacy_command: str) -> None:
    """Parser should reject removed legacy file-import commands."""
    with patch("sys.argv", ["mud-server", legacy_command]):
        with pytest.raises(SystemExit) as exc:
            cli.main()
    assert exc.value.code == 2
