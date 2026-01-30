# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**PipeWorks MUD Server** is a Python-based multiplayer text game (MUD) server with a web interface. It's a proof-of-concept for "The Undertaking" - a procedural, ledger-driven interactive fiction system.

**Tech Stack**: Python 3.12+, FastAPI, Gradio, SQLite, bcrypt

**Current Status**: Working proof-of-concept with auth, RBAC, room navigation, inventory, and chat. The design vision (character issuance, axis-based resolution, ledger/newspaper truth systems) is documented in `docs/` but not yet implemented.

## Common Commands

### Setup
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python3 -m mud_server.db.database  # Initialize DB
```

### Running
```bash
./run.sh                                          # Start both server (:8000) and client (:7860)
PYTHONPATH=src python3 src/mud_server/api/server.py   # API server only
PYTHONPATH=src python3 src/mud_server/client/app.py   # Gradio client only (server must be running)
```

### Testing
```bash
pytest                                            # Run all tests (includes coverage)
pytest tests/test_api/                            # Run specific test directory
pytest tests/test_api/test_auth.py -v            # Run specific test file
pytest -k "test_login"                            # Run tests matching pattern
pytest -m "unit"                                  # Run only unit tests
pytest -m "not slow"                              # Skip slow tests
pytest --no-cov                                   # Skip coverage (faster iteration)
```

**Test markers** (defined in pyproject.toml): `unit`, `integration`, `slow`, `requires_model`, `api`, `db`, `auth`, `game`, `admin`

### Code Quality
```bash
ruff check src/ tests/                            # Lint
black src/ tests/                                 # Format
mypy src/ --ignore-missing-imports                # Type check
```

### Database
```bash
rm data/mud.db && PYTHONPATH=src python3 -m mud_server.db.database  # Reset DB
sqlite3 data/mud.db ".schema"                     # View schema
sqlite3 data/mud.db "SELECT username, role, current_room FROM players;"
```

## Architecture

```
src/mud_server/
├── api/                    # FastAPI REST API (port 8000)
│   ├── server.py           # App init, CORS, uvicorn entry
│   ├── routes.py           # All endpoints, command parsing
│   ├── models.py           # Pydantic request/response schemas
│   ├── auth.py             # In-memory sessions: dict[session_id, (username, role)]
│   ├── password.py         # bcrypt hashing via passlib
│   └── permissions.py      # RBAC: Role enum, Permission enum, decorators
├── core/                   # Game engine
│   ├── engine.py           # GameEngine: movement, inventory, chat
│   └── world.py            # World, Room, Item dataclasses (loads from JSON)
├── db/
│   └── database.py         # SQLite: players, sessions, chat_messages tables
└── client/                 # Gradio web interface (port 7860)
    ├── app.py              # Main entry, tab assembly
    ├── api/                # API client layer (works outside Gradio)
    │   ├── base.py         # BaseAPIClient with common HTTP patterns
    │   ├── auth.py         # Login, register, logout
    │   ├── game.py         # Commands, status, chat
    │   ├── admin.py        # User management
    │   ├── settings.py     # Server control
    │   └── ollama.py       # AI model integration
    ├── ui/                 # UI utilities
    │   ├── state.py        # Gradio state builders
    │   └── validators.py   # Input validation (100% coverage)
    ├── tabs/               # Individual tab modules
    │   ├── login_tab.py, register_tab.py, game_tab.py
    │   ├── settings_tab.py, database_tab.py
    │   ├── ollama_tab.py, help_tab.py
    └── static/styles.css   # Centralized CSS
```

**Data Flow**: Client → HTTP → routes.py → auth.py (validate session) → engine.py → database.py → SQLite

**Sessions**: Stored in memory (`auth.py:active_sessions`), lost on restart. Format: `{session_id: (username, role)}`

## Key Files for Common Tasks

| Task | Files |
|------|-------|
| Add new API endpoint | `api/routes.py`, `api/models.py` |
| Add new game command | `api/routes.py` (parsing), `core/engine.py` (logic) |
| Add new room/item | `data/world_data.json` (no code changes needed) |
| Add database table | `db/database.py` |
| Add Gradio tab | `client/tabs/`, then register in `client/app.py` |
| Add API client method | `client/api/` (pick appropriate module) |

## Testing Patterns

Tests use fixtures from `tests/conftest.py`:

```python
def test_example(test_client, db_with_users):
    """test_client provides FastAPI TestClient, db_with_users creates test users."""
    response = test_client.post("/login", json={"username": "testplayer", "password": "password123"})
    assert response.status_code == 200

def test_authenticated(authenticated_client):
    """authenticated_client provides logged-in session."""
    client = authenticated_client["client"]
    session_id = authenticated_client["session_id"]
    response = client.post("/command", json={"session_id": session_id, "command": "look"})
```

**Key fixtures**: `temp_db_path`, `test_db`, `db_with_users`, `mock_world`, `mock_engine`, `test_client`, `authenticated_client`

**Test users created by `db_with_users`**: testplayer, testbuilder, testadmin, testsuperuser (all with password "password123")

## Important Behaviors

**Item pickup**: Items remain in room after pickup (intentional for PoC). Multiple players can pick up same item.

**RBAC hierarchy**: Player < WorldBuilder < Admin < Superuser. Check permissions via `permissions.py:has_permission()`.

**Default superuser**: `admin` / `admin123` - created on DB init. Change immediately in production.

**World data**: Loaded from `data/world_data.json` at startup. Rooms define one-way exits unless both directions are specified.

**Coverage requirement**: 80% minimum enforced by pytest (see `pyproject.toml:--cov-fail-under`).

## Design Principles (from docs/)

When implementing planned features:

- **Programmatic = Authoritative**: Game logic, state, resolution math, ledger truth
- **LLM = Non-Authoritative**: Descriptions, flavor text, newspaper interpretations
- **Determinism First**: All game logic must be replayable from seed
- **Ledger is Truth**: Immutable records; everything else is interpretation

See `docs/the_undertaking_articulation.md` for full design philosophy and `docs/undertaking_code_examples.md` for implementation patterns.

## pipe-works Organization Standards

This repository follows pipe-works organization standards.
See https://github.com/pipe-works/pipe-works/blob/main/CLAUDE.md for full details.

- Python 3.12+, pyenv virtualenvs
- pytest >80% coverage (org minimum 50%)
- black 26.1.0 (pinned org-wide) / ruff / mypy
- Reusable CI workflow from pipe-works/.github
- GPL-3.0-or-later license
