"""
Tests for character state snapshot seeding.

These tests validate:
- Character state columns are added to legacy databases.
- Snapshot JSON is written on character creation.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from mud_server.config import use_test_database
from mud_server.db import axis_repo, database, policy_repo
from tests.constants import TEST_PASSWORD


@pytest.mark.unit
@pytest.mark.db
def test_ensure_character_state_columns_adds_missing(temp_db_path) -> None:
    """Legacy character tables should gain snapshot columns."""
    with use_test_database(temp_db_path):
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
        cursor.execute("INSERT INTO characters (name) VALUES ('legacy_char')")
        database._ensure_character_state_columns(cursor)
        conn.commit()

        cursor.execute("PRAGMA table_info(characters)")
        column_names = {row[1] for row in cursor.fetchall()}
        assert "base_state_json" in column_names
        assert "current_state_json" in column_names
        assert "state_seed" in column_names
        assert "state_version" in column_names
        assert "state_updated_at" in column_names

        cursor.execute("SELECT state_seed FROM characters WHERE name = 'legacy_char'")
        assert cursor.fetchone()[0] == 0
        conn.close()


@pytest.mark.unit
@pytest.mark.db
def test_character_state_snapshot_seeded_on_creation(temp_db_path, monkeypatch) -> None:
    """Character creation should seed axis scores and snapshots."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        monkeypatch.setattr(axis_repo, "_get_axis_policy_hash", lambda _world_id: "policyhash")
        # Use a fixed seed in this unit test so assertions remain deterministic.
        monkeypatch.setattr(axis_repo, "_generate_state_seed", lambda: 424242)

        axes_payload = {
            "axes": {
                "wealth": {
                    "description": "Economic status",
                    "ordering": {"type": "ordinal", "values": ["poor", "wealthy"]},
                }
            }
        }
        thresholds_payload = {
            "axes": {
                "wealth": {
                    "values": {
                        "poor": {"min": 0.0, "max": 0.49},
                        "wealthy": {"min": 0.5, "max": 1.0},
                    }
                }
            }
        }

        database.seed_axis_registry(
            world_id="test_world",
            axes_payload=axes_payload,
            thresholds_payload=thresholds_payload,
        )

        assert database.create_user_with_password("snapshot_user", TEST_PASSWORD)
        user_id = database.get_user_id("snapshot_user")
        assert user_id is not None
        assert database.create_character_for_user(user_id, "snapshot_char", world_id="test_world")

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT base_state_json, current_state_json, state_seed, state_version
            FROM characters
            WHERE name = ?
            """,
            ("snapshot_char",),
        )
        row = cursor.fetchone()
        assert row is not None
        base_state_json, current_state_json, state_seed, state_version = row
        conn.close()

        assert base_state_json is not None
        assert current_state_json is not None
        assert state_seed == 424242
        assert state_version == "policyhash"

        snapshot = json.loads(base_state_json)
        assert snapshot["world_id"] == "test_world"
        assert snapshot["seed"] == 424242
        assert snapshot["axes"]["wealth"]["label"] == "wealthy"
        assert snapshot["axes"]["wealth"]["score"] == 0.5


@pytest.mark.unit
@pytest.mark.db
def test_get_axis_policy_hash_returns_value(temp_db_path) -> None:
    """Policy hash helper should resolve canonical manifest+axis activations."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        world_id = database.DEFAULT_WORLD_ID
        manifest_policy_id = f"manifest_bundle:world.manifests:{world_id}"
        axis_policy_id = "axis_bundle:axis.bundles:axis_core_v1"

        policy_repo.upsert_policy_item(
            policy_id=manifest_policy_id,
            policy_type="manifest_bundle",
            namespace="world.manifests",
            policy_key=world_id,
        )
        policy_repo.upsert_policy_variant(
            policy_id=manifest_policy_id,
            variant="v1",
            schema_version="1.0",
            policy_version=1,
            status="active",
            content={
                "manifest": {
                    "axis": {
                        "active_bundle": {
                            "id": "axis_core_v1",
                            "version": 1,
                        }
                    }
                }
            },
            content_hash="manifest-hash",
            updated_at="2026-03-13T00:00:00Z",
            updated_by="test",
        )
        policy_repo.upsert_policy_item(
            policy_id=axis_policy_id,
            policy_type="axis_bundle",
            namespace="axis.bundles",
            policy_key="axis_core_v1",
        )
        policy_repo.upsert_policy_variant(
            policy_id=axis_policy_id,
            variant="v1",
            schema_version="1.0",
            policy_version=1,
            status="active",
            content={
                "axes": {"axes": {"wealth": {}}},
                "thresholds": {"axes": {}},
                "resolution": {"version": "1.0"},
            },
            content_hash="axis-hash",
            updated_at="2026-03-13T00:00:00Z",
            updated_by="test",
        )
        policy_repo.set_policy_activation(
            world_id=world_id,
            client_profile="",
            policy_id=manifest_policy_id,
            variant="v1",
            activated_at="2026-03-13T00:00:00Z",
            activated_by="test",
            rollback_of_activation_id=None,
        )
        policy_repo.set_policy_activation(
            world_id=world_id,
            client_profile="",
            policy_id=axis_policy_id,
            variant="v1",
            activated_at="2026-03-13T00:00:00Z",
            activated_by="test",
            rollback_of_activation_id=None,
        )

        policy_hash = database._get_axis_policy_hash(world_id)
        assert isinstance(policy_hash, str) and policy_hash


@pytest.mark.unit
def test_generate_state_seed_returns_non_zero_positive_int() -> None:
    """Generated snapshot seeds should always be positive/non-zero."""
    seed = database._generate_state_seed()
    assert isinstance(seed, int)
    assert seed > 0


@pytest.mark.unit
@pytest.mark.db
def test_resolve_axis_label_for_score_returns_none(temp_db_path) -> None:
    """Axes without thresholds should resolve to no label."""
    with use_test_database(temp_db_path):
        database.init_database(skip_superuser=True)

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO axis (world_id, name) VALUES (?, ?)",
            ("test_world", "mood"),
        )
        axis_id = cursor.lastrowid
        assert axis_id is not None

        label = database._resolve_axis_label_for_score(cursor, int(axis_id), 0.5)
        conn.close()

        assert label is None
