"""
Shared pytest fixtures for the MUD server test suite.

This module provides fixtures that are automatically available to all test files:
- Database mocking and temporary test databases
- FastAPI TestClient instances
- Mock GameEngine and World instances
- Test user accounts and sessions
- Common test data (rooms, items, players)

Fixtures are organized by scope (function, module, session) to optimize
test performance and isolation.
"""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from mud_server.config import use_test_database
from mud_server.core.engine import GameEngine
from mud_server.core.world import Item, Room, World, Zone
from mud_server.db import database

# Import shared test constant
from tests.constants import TEST_PASSWORD  # noqa: F401 - exported for other tests

# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def temp_db_path() -> Generator[Path, None, None]:
    """
    Create a temporary database file for testing.

    This fixture creates a unique temporary database for each test function,
    ensuring complete isolation between tests. Uses the config system's
    use_test_database context manager.

    Yields:
        Path to temporary database file

    Cleanup:
        Removes temporary database after test completes
    """
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    temp_db = Path(temp_dir) / "test_mud.db"

    # Use the config system's test database helper
    with use_test_database(temp_db):
        yield temp_db

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def test_db(temp_db_path: Path) -> Generator[None, None, None]:
    """
    Initialize a test database with schema but no data.

    Creates all database tables but doesn't create the default admin user.
    This allows tests to create their own test users as needed.

    Args:
        temp_db_path: Path to temporary database (from fixture)

    Yields:
        None (database is initialized and ready to use)
    """
    # Use production schema to keep tests aligned with migrations.
    database.init_database(skip_superuser=True)

    yield


@pytest.fixture(scope="function")
def db_with_users(test_db) -> dict[str, str]:
    """
    Create a test database with sample users for testing.

    Creates users with different roles for testing permission systems:
    - testplayer (role: player)
    - testbuilder (role: worldbuilder)
    - testadmin (role: admin)
    - testsuperuser (role: superuser)

    All users have password TEST_PASSWORD ("SecureTest#123")

    Args:
        test_db: Initialized test database (from fixture)

    Returns:
        Dict mapping usernames to roles
    """
    users = {
        "testplayer": "player",
        "testbuilder": "worldbuilder",
        "testadmin": "admin",
        "testsuperuser": "superuser",
    }

    for username, role in users.items():
        database.create_player_with_password(username, TEST_PASSWORD, role)

    return users


# ============================================================================
# WORLD AND GAME ENGINE FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def mock_world_data() -> dict:
    """
    Create mock world data for testing without loading from JSON.

    Provides a minimal test world with:
    - 3 rooms (spawn, forest, desert)
    - 2 items (torch, rope)
    - Room connections

    Returns:
        Dict containing rooms and items data
    """
    return {
        "rooms": [
            {
                "id": "spawn",
                "name": "Test Spawn",
                "description": "A test spawn room",
                "exits": {"north": "forest", "south": "desert"},
                "items": ["torch", "rope"],
            },
            {
                "id": "forest",
                "name": "Test Forest",
                "description": "A dark forest",
                "exits": {"south": "spawn"},
                "items": [],
            },
            {
                "id": "desert",
                "name": "Test Desert",
                "description": "A sandy desert",
                "exits": {"north": "spawn"},
                "items": [],
            },
        ],
        "items": [
            {"id": "torch", "name": "Torch", "description": "A wooden torch"},
            {"id": "rope", "name": "Rope", "description": "A sturdy rope"},
        ],
    }


def _build_mock_world(mock_world_data: dict) -> World:
    """Build a mock World instance without hitting the filesystem."""
    with patch.object(World, "_load_world", lambda self: None):
        world = World()

    world.rooms = {
        room["id"]: Room(
            id=room["id"],
            name=room["name"],
            description=room["description"],
            exits=room.get("exits", {}),
            items=room.get("items", []),
        )
        for room in mock_world_data["rooms"]
    }
    world.items = {
        item["id"]: Item(
            id=item["id"],
            name=item["name"],
            description=item["description"],
        )
        for item in mock_world_data["items"]
    }
    world.zones = {
        "test_zone": Zone(
            id="test_zone",
            name="Test Zone",
            description="Mock zone for tests",
            spawn_room="spawn",
            rooms=list(world.rooms.keys()),
        )
    }
    world.default_spawn = ("test_zone", "spawn")
    world.world_name = "Test World"
    return world


@pytest.fixture(scope="function")
def mock_world(mock_world_data: dict) -> World:
    """
    Create a mock World instance for testing.

    Bypasses disk loading and injects mock zones, rooms, and items directly.
    """
    return _build_mock_world(mock_world_data)


@pytest.fixture(scope="function")
def mock_engine(test_db, mock_world) -> GameEngine:
    """
    Create a mock GameEngine instance for testing.

    Patches the engine to use test database and mock world data.

    Args:
        test_db: Initialized test database (from fixture)
        mock_world: Mock World instance (from fixture)

    Returns:
        GameEngine instance configured for testing
    """
    with patch.object(GameEngine, "__init__", lambda self: None):
        engine = GameEngine()
        engine.world_registry = SimpleNamespace(get_world=lambda _world_id: mock_world)
        engine._get_world = lambda _world_id: mock_world
        return engine


# ============================================================================
# FASTAPI TEST CLIENT FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def test_client(test_db, mock_world_data) -> TestClient:
    """
    Create a FastAPI TestClient for API endpoint testing.

    Provides a fully configured test client with:
    - Test database initialized
    - Mock world data loaded
    - All routes registered

    Args:
        test_db: Initialized test database (from fixture)
        mock_world_data: Mock world data (from fixture)

    Returns:
        TestClient instance for making API requests

    Example:
        def test_login(test_client):
            response = test_client.post("/login", json={
                "username": "test",
                "password": "test123"
            })
            assert response.status_code == 200
    """
    from fastapi import FastAPI

    from mud_server.api.routes import register_routes
    from mud_server.core.engine import GameEngine

    # Create app
    app = FastAPI()

    # Create engine with mocked World loading
    with patch.object(database, "init_database"):
        engine = GameEngine()
        world = _build_mock_world(mock_world_data)
        engine.world_registry = SimpleNamespace(get_world=lambda _world_id: world)
        engine._get_world = lambda _world_id: world

    # Register routes
    register_routes(app, engine)

    # Return test client
    return TestClient(app)


@pytest.fixture(scope="function")
def authenticated_client(test_client: TestClient, db_with_users: dict[str, str]) -> dict:
    """
    Create an authenticated test client with logged-in user.

    Logs in as testplayer and returns both the client and session info.

    Args:
        test_client: FastAPI test client (from fixture)
        db_with_users: Database with test users (from fixture)

    Returns:
        Dict with keys:
        - client: TestClient instance
        - session_id: Valid session ID
        - username: Logged in username ("testplayer")
        - role: User role ("player")
    """
    # Login as testplayer
    response = test_client.post(
        "/login", json={"username": "testplayer", "password": TEST_PASSWORD}
    )

    assert response.status_code == 200
    data = response.json()

    return {
        "client": test_client,
        "session_id": data["session_id"],
        "username": "testplayer",
        "role": "player",
    }


# ============================================================================
# TEST DATA FIXTURES
# ============================================================================


@pytest.fixture
def sample_room() -> Room:
    """Create a sample Room instance for testing."""
    return Room(
        id="test_room",
        name="Test Room",
        description="A room for testing",
        exits={"north": "other_room"},
        items=["torch"],
    )


@pytest.fixture
def sample_item() -> Item:
    """Create a sample Item instance for testing."""
    return Item(id="test_item", name="Test Item", description="An item for testing")
