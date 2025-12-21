# Testing Guide

This document describes the testing infrastructure for the MUD server project.

## Overview

The project uses **pytest** as the testing framework with comprehensive test coverage across all layers:

- **Database layer** (`src/mud_server/db/`) - 92.05% coverage
- **Core engine** (`src/mud_server/core/`) - 87.58% coverage (engine), 98.55% coverage (world)
- **API layer** (`src/mud_server/api/`) - 65-100% coverage
- **Overall project coverage**: 55.68%

## Test Statistics

- **Total tests**: 171
- **Passing tests**: 161 (94% success rate)
- **Test execution time**: ~100 seconds

## Quick Start

### Installation

```bash
# Install development dependencies
pip install -r requirements-dev.txt
```

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_db/test_database.py

# Run specific test
pytest tests/test_db/test_database.py::test_create_player_with_password_success

# Run tests by marker
pytest -m unit          # Run only unit tests
pytest -m api           # Run only API tests
pytest -m admin         # Run only admin tests
pytest -m integration   # Run only integration tests
```

### Coverage Reports

```bash
# Generate coverage report
pytest --cov=mud_server --cov-report=term-missing

# Generate HTML coverage report
pytest --cov=mud_server --cov-report=html
# Open htmlcov/index.html in browser

# Generate XML coverage report (for CI/CD)
pytest --cov=mud_server --cov-report=xml
```

## Test Organization

### Directory Structure

```
tests/
├── conftest.py              # Shared fixtures and test configuration
├── test_db/                 # Database layer tests
│   ├── __init__.py
│   └── test_database.py     # 44 tests for database operations
├── test_core/               # Game engine tests
│   ├── __init__.py
│   ├── test_world.py        # 21 tests for World, Room, Item
│   └── test_engine.py       # 42 tests for GameEngine
└── test_api/                # API endpoint tests
    ├── __init__.py
    ├── test_auth.py         # 12 tests for authentication
    ├── test_permissions.py  # 36 tests for RBAC permissions
    ├── test_routes.py       # 26 tests for API endpoints
    └── test_admin.py        # 14 tests for admin functions
```

### Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Fast, isolated unit tests with mocked dependencies
- `@pytest.mark.integration` - Integration tests with database/external services
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.db` - Database tests
- `@pytest.mark.auth` - Authentication and authorization tests
- `@pytest.mark.game` - Game logic tests (movement, inventory, chat)
- `@pytest.mark.admin` - Administrative function tests
- `@pytest.mark.slow` - Slow-running tests

## Test Fixtures

The project uses pytest fixtures for test isolation and reusability:

### Database Fixtures

- `temp_db_path` - Creates temporary database file for each test
- `test_db` - Initializes database schema without default users
- `db_with_users` - Creates test users with different roles

### World and Engine Fixtures

- `mock_world_data` - Provides mock world data (rooms, items)
- `mock_world` - Creates World instance with mock data
- `mock_engine` - Creates GameEngine instance for testing

### API Testing Fixtures

- `test_client` - FastAPI TestClient for HTTP requests
- `authenticated_client` - Pre-authenticated client with session
- `mock_session_data` - Mock session data for auth testing

### Sample Data Fixtures

- `sample_room` - Sample Room dataclass instance
- `sample_item` - Sample Item dataclass instance

## Writing Tests

### Test Naming Convention

- Test files: `test_<module_name>.py`
- Test functions: `test_<function>_<scenario>_<expected_outcome>`
- Test classes: `Test<ClassName>`

### Example Test

```python
import pytest
from mud_server.db import database


@pytest.mark.unit
@pytest.mark.db
def test_create_player_with_password_success(test_db, temp_db_path):
    """Test creating a new player with password."""
    with patch.object(database, 'DB_PATH', temp_db_path):
        result = database.create_player_with_password("newuser", "password123", "player")

        assert result is True
        assert database.player_exists("newuser")
        assert database.verify_password_for_user("newuser", "password123")
```

### AAA Pattern

Tests follow the Arrange-Act-Assert pattern:

```python
def test_player_movement():
    # Arrange - Set up test data
    database.set_player_room("testplayer", "spawn")

    # Act - Execute the code being tested
    success, message = engine.move("testplayer", "north")

    # Assert - Verify the results
    assert success is True
    assert database.get_player_room("testplayer") == "forest"
```

## CI/CD Integration

### GitHub Actions Workflow

The project includes a GitHub Actions workflow (`.github/workflows/test-and-lint.yml`) that runs on:
- Push to `main` or `develop` branches
- Pull requests to `main` branch

### CI Pipeline

The CI pipeline includes three jobs:

1. **Test Job** (Python 3.12, 3.13)
   - Linting with `ruff`
   - Formatting check with `black`
   - Type checking with `mypy`
   - Unit tests with `pytest`
   - Coverage reporting to Codecov

2. **Lint Job** (Python 3.12)
   - Strict linting with `ruff`
   - Strict formatting check with `black`
   - Strict type checking with `mypy`

3. **Security Job** (Python 3.12)
   - Security scanning with `pip-audit`

## Code Quality Tools

### Linting with Ruff

```bash
# Check for issues
ruff check src/ tests/

# Auto-fix issues
ruff check --fix src/ tests/
```

### Formatting with Black

```bash
# Check formatting
black --check src/ tests/

# Auto-format code
black src/ tests/
```

### Type Checking with Mypy

```bash
# Run type checker
mypy src/ --ignore-missing-imports
```

## Test Coverage Goals

- **Database layer**: 90%+ coverage
- **Core engine**: 85%+ coverage
- **API endpoints**: 70%+ coverage
- **Overall project**: 70%+ coverage

## Common Test Scenarios

### Database Tests
- Player creation and authentication
- Role management and permissions
- Session tracking
- Chat message storage
- Inventory management

### Core Engine Tests
- Player login/logout
- Movement between rooms
- Item pickup/drop
- Chat commands (say, yell, whisper)
- Room descriptions

### API Tests
- Registration and login endpoints
- Authenticated commands
- Permission-based access control
- Error handling and validation

### Integration Tests
- Full user flow (register → login → play → logout)
- Multi-user interactions
- Data persistence across sessions

## Troubleshooting

### Test Database Isolation

Tests use temporary SQLite databases that are created and destroyed for each test. If tests are interfering with each other:

1. Check that `temp_db_path` fixture is being used
2. Verify `patch.object(database, 'DB_PATH', temp_db_path)` is applied
3. Ensure `reset_active_sessions` autouse fixture is working

### Mock Data Issues

If world data mocking fails:

1. Verify `mock_world_data` fixture is being used
2. Check that `mock_world` fixture properly patches file loading
3. Ensure mock data structure matches expected format

### Coverage Not Updating

If coverage reports aren't updating:

1. Delete `.coverage` file and `htmlcov/` directory
2. Run `pytest --cov=mud_server --cov-report=html` again
3. Check that `pytest.ini` has correct coverage settings

## Best Practices

1. **Use appropriate fixtures** - Leverage existing fixtures for database, world, and API testing
2. **Mark your tests** - Always use pytest markers for categorization
3. **Test isolation** - Each test should be independent and not rely on other tests
4. **Mock external dependencies** - Mock database, file I/O, and external APIs
5. **Descriptive test names** - Test names should clearly describe what is being tested
6. **Test edge cases** - Include tests for error conditions and boundary values
7. **Keep tests fast** - Unit tests should run in milliseconds, not seconds

## Contributing

When adding new features:

1. Write tests **before** or **alongside** implementation (TDD)
2. Ensure new tests pass locally before committing
3. Maintain or improve overall code coverage
4. Add appropriate test markers
5. Update this documentation if adding new test categories

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [FastAPI testing guide](https://fastapi.tiangolo.com/tutorial/testing/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
