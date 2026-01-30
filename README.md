# PipeWorks MUD Server

> **A deterministic, procedural multiplayer text game engine for building accountable interactive fiction worlds.**

[![CI](https://github.com/pipe-works/pipeworks_mud_server/actions/workflows/ci.yml/badge.svg)](https://github.com/pipe-works/pipeworks_mud_server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pipe-works/pipeworks_mud_server/branch/main/graph/badge.svg)](https://codecov.io/gh/pipe-works/pipeworks_mud_server)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

---

## What is PipeWorks MUD Server?

A **generic, extensible MUD (Multi-User Dungeon) server** for building text-based multiplayer games. Built with modern Python tooling, this server provides the technical foundation for creating interactive fiction worlds with:

- **Deterministic game mechanics** - Reproducible outcomes for testing and replay
- **JSON-driven world data** - Define rooms, items, and connections without code changes
- **Modern web interface** - Gradio-based UI with clean UX
- **REST API backend** - FastAPI server for high performance
- **Role-based access control** - Built-in auth and permission system
- **Modular architecture** - Clean separation between client, server, and game logic

**Use it to build:** Fantasy MUDs, sci-fi adventures, educational games, procedural narratives, or any text-based multiplayer experience.

---

## Current Implementation Status

This repository contains a **working proof-of-concept** that validates the core architecture:

### ✅ Implemented Features

- **FastAPI REST API** - High-performance backend (port 8000)
- **Gradio Web Interface** - Modular, professional client (port 7860)
- **SQLite Database** - Player state, sessions, and chat persistence
- **Authentication System** - Password-based auth with bcrypt hashing
- **Role-Based Access Control (RBAC)** - 4 user types (Player, WorldBuilder, Admin, Superuser)
- **Room Navigation** - Directional movement between connected rooms
- **Inventory System** - Pick up and drop items in rooms
- **Multi-Channel Chat** - Room-based `say`, area-wide `yell`, targeted `whisper`
- **JSON World Definition** - Data-driven room and item configuration
- **Ollama Integration** - AI model management interface (admin/superuser only)
- **Modular Client Architecture** - Clean API/UI separation with 100% test coverage on core modules
- **Centralized CSS** - External stylesheet with Safari-compatible dark mode

### 🎯 Design Philosophy

**Programmatic Authority:**

- All game logic and state is deterministic and code-driven
- Game mechanics are reproducible and testable
- No LLM involvement in authoritative systems (state, logic, resolution)

**Extensibility First:**

- World data is JSON-driven (swap worlds without code changes)
- Commands are extensible (add new actions without server rewrites)
- Modular architecture supports plugins and custom mechanics

**Clean Separation:**

- **Client Layer** (Gradio) - UI and user interaction
- **Server Layer** (FastAPI) - HTTP API and routing
- **Game Layer** (Engine + World) - Core mechanics and state
- **Persistence Layer** (SQLite) - Data storage

---

## Quick Start

### Prerequisites

- Python 3.12 or 3.13
- pip (Python package manager)
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/aa-parky/pipeworks_mud_server.git
cd pipeworks_mud_server

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
PYTHONPATH=src python3 -m mud_server.db.database
```

### Running the Server

```bash
# Start both API server and web client
./run.sh

# The server will start on:
# - API: http://localhost:8000
# - Web UI: http://localhost:7860
```

Press `Ctrl+C` to stop both services.

### First Login

⚠️ **Default Superuser Credentials:**

```text
Username: admin
Password: admin123
```

**Change this immediately!** Login and use the user management interface to set a new password.

---

## Architecture

### Three-Tier Design

```text
┌─────────────────────────────────────────────────────────────┐
│                    Gradio Web Interface                      │
│                     (Client Layer)                           │
│              http://localhost:7860                           │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI REST API                          │
│                    (Server Layer)                            │
│              http://localhost:8000                           │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
┌──────────────────┐           ┌──────────────────┐
│  Game Engine     │           │  SQLite Database │
│  (Core Layer)    │◄──────────┤  (Persistence)   │
│                  │           │                  │
│ - World/Rooms    │           │ - Players        │
│ - Items          │           │ - Sessions       │
│ - Actions        │           │ - Chat Messages  │
└──────────────────┘           └──────────────────┘
```

### Modular Client Architecture

The Gradio client uses a fully modular design for maintainability and testability:

```text
src/mud_server/client/
├── app.py                    # Main entry point (~180 lines)
├── api/                      # API client layer
│   ├── base.py              # BaseAPIClient - common HTTP patterns
│   ├── auth.py              # Authentication operations
│   ├── game.py              # Game operations
│   ├── settings.py          # Settings and server control
│   ├── admin.py             # Admin operations
│   └── ollama.py            # Ollama AI integration
├── ui/                       # UI utilities
│   ├── validators.py        # Input validation (100% coverage)
│   └── state.py             # Gradio state builders
├── tabs/                     # Tab modules
│   ├── login_tab.py         # Login interface
│   ├── register_tab.py      # Registration interface
│   ├── game_tab.py          # Main gameplay interface
│   ├── settings_tab.py      # Settings and server control
│   ├── database_tab.py      # Admin database viewer
│   ├── ollama_tab.py        # AI model management
│   └── help_tab.py          # Help documentation
├── utils.py                  # Shared utilities
└── static/styles.css        # Centralized CSS
```

**Benefits:**

- Clear separation between API logic, validation, and UI
- 100% test coverage on API and UI utility modules (191 tests)
- API clients work outside Gradio (CLI tools, tests, scripts)
- Easy to extend with new features or tabs

### Project Structure

```text
pipeworks_mud_server/
├── src/mud_server/              # Main application package
│   ├── api/                     # FastAPI REST API (8 files, ~1200 LOC)
│   │   ├── server.py            # App initialization, CORS, routing
│   │   ├── routes.py            # API endpoints
│   │   ├── models.py            # Pydantic request/response schemas
│   │   ├── auth.py              # Session management
│   │   ├── password.py          # Password hashing
│   │   └── permissions.py       # RBAC system
│   ├── core/                    # Game engine (2 files, ~390 LOC)
│   │   ├── engine.py            # Game logic facade
│   │   └── world.py             # World, Room, Item dataclasses
│   ├── db/                      # Database layer (1 file, ~806 LOC)
│   │   └── database.py          # SQLite operations, schema, CRUD
│   └── client/                  # Gradio frontend (~5000+ LOC)
│       └── [see structure above]
├── data/                        # Data files
│   ├── world_data.json          # Room and item definitions
│   └── mud.db                   # SQLite database (generated)
├── tests/                       # Test files
├── logs/                        # Application logs
├── requirements.txt             # Python dependencies
└── run.sh                       # Startup script
```

---

## Creating Your Own World

The MUD server is **fully data-driven**. Create a custom world by editing `data/world_data.json`:

### World Data Format

```json
{
  "rooms": {
    "room_id": {
      "id": "room_id",
      "name": "Room Name",
      "description": "What the player sees when they look around.",
      "exits": {
        "north": "another_room_id",
        "south": "yet_another_room"
      },
      "items": ["item_id_1", "item_id_2"]
    }
  },
  "items": {
    "item_id": {
      "id": "item_id",
      "name": "Item Name",
      "description": "What the player sees when examining this item."
    }
  }
}
```

### Example: Adding a New Room

```json
{
  "rooms": {
    "library": {
      "id": "library",
      "name": "Ancient Library",
      "description": "Dusty books line the shelves. A reading desk sits by the window.",
      "exits": {
        "south": "spawn",
        "up": "tower"
      },
      "items": ["dusty_book", "reading_lamp"]
    }
  },
  "items": {
    "dusty_book": {
      "id": "dusty_book",
      "name": "dusty book",
      "description": "A leather-bound tome with faded gold lettering."
    }
  }
}
```

**That's it.** No code changes needed. Restart the server and the new room is live.

---

## Available Commands

Players can use these commands in the game interface:

### Movement

- `north` / `n` - Move north
- `south` / `s` - Move south
- `east` / `e` - Move east
- `west` / `w` - Move west
- `up` / `u` - Move upward
- `down` / `d` - Move downward

### Observation

- `look` / `l` - Observe your current surroundings
- `inventory` / `inv` / `i` - Check your inventory

### Items

- `pickup <item>` / `get <item>` - Pick up an item from the room
- `drop <item>` - Drop an item from your inventory

### Communication

- `say <message>` - Speak to others in the same room
- `yell <message>` - Shout to nearby areas
- `whisper <username> <message>` - Send a private message to a specific player

### Utility

- `who` - See all players online
- `help` - Show help information

---

## Ollama Integration

The Ollama tab provides AI model management for **Admin** and **Superuser** accounts only.

### Features

- **Model Management** - List, pull, and run Ollama models
- **Conversational Mode** - Natural chat interface with AI models
- **Slash Commands** - Command-line style interaction
- **Server Configuration** - Connect to local or remote Ollama servers

### Slash Commands

| Command                 | Description                      | Example                     |
| ----------------------- | -------------------------------- | --------------------------- |
| `/list` or `/ls`        | List all available models        | `/list`                     |
| `/ps`                   | Show currently running models    | `/ps`                       |
| `/pull <model>`         | Download a new model             | `/pull llama2`              |
| `/run <model> [prompt]` | Run a model with optional prompt | `/run llama2 Write a haiku` |
| `/show <model>`         | Show detailed model information  | `/show llama2`              |

### Configuration

**Default Ollama Server**: `http://localhost:11434`

Change the Server URL in the Ollama tab interface to use a remote server.

---

## Development

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest -v

# Run tests with coverage
pytest --cov=mud_server --cov-report=html

# Lint code
ruff check src/ tests/

# Format code
black src/ tests/

# Type checking
mypy src/ --ignore-missing-imports
```

### Running Components Separately

```bash
# Run API server only
PYTHONPATH=src python3 src/mud_server/api/server.py

# Run Gradio client only (requires server running)
PYTHONPATH=src python3 src/mud_server/client/app.py

# Check server health
curl http://localhost:8000/health
```

### Database Management

```bash
# Reset database (deletes all player data)
rm data/mud.db && PYTHONPATH=src python3 -m mud_server.db.database

# View database schema
sqlite3 data/mud.db ".schema"

# Query players
sqlite3 data/mud.db "SELECT username, role, current_room FROM players;"
```

### Environment Variables

```bash
# Server configuration
export MUD_HOST="0.0.0.0"          # Bind address
export MUD_PORT=8000                # API port
export MUD_SERVER_URL="http://localhost:8000"  # Client API endpoint
```

---

## Extending the Server

### Adding New Commands

Commands are parsed in [src/mud_server/api/routes.py](src/mud_server/api/routes.py) in the `/api/command` endpoint.

**Example: Adding an "examine" command:**

1. **Add method to GameEngine** ([src/mud_server/core/engine.py](src/mud_server/core/engine.py)):

```python
def examine(self, username: str, target: str) -> str:
    """Examine an item or player in detail."""
    player = self.db.get_player(username)
    if not player:
        return "You don't exist."

    # Check inventory
    if target in player["inventory"]:
        item = self.world.get_item(target)
        return f"You examine the {item.name}: {item.description}"

    # Check room
    room = self.world.get_room(player["current_room"])
    if target in room.items:
        item = self.world.get_item(target)
        return f"You examine the {item.name}: {item.description}"

    return f"You don't see '{target}' here."
```

1. **Add command handler to routes.py**:

```python
# In the command parser (around line 250):
elif cmd in ["examine", "ex"]:
    if not args:
        return JSONResponse({"result": "Examine what?"})
    target = args[0]
    result = engine.examine(username, target)
    return JSONResponse({"result": result})
```

1. **Restart the server**. The new command is now available.

### Adding New World Features

All world data comes from `data/world_data.json`. To extend world capabilities:

1. **Update the JSON schema** - Add new fields to room or item definitions
1. **Update the dataclasses** - Modify `Room` or `Item` in [src/mud_server/core/world.py](src/mud_server/core/world.py)
1. **Update the World loader** - Modify `World.__init__()` to parse new fields
1. **Use in game logic** - Access new fields in engine methods

**Example: Adding room environmental effects:**

```json
{
  "rooms": {
    "dark_cave": {
      "id": "dark_cave",
      "name": "Dark Cave",
      "description": "You can barely see in the darkness.",
      "exits": {"south": "spawn"},
      "items": [],
      "environment": {
        "light_level": "dark",
        "temperature": "cold",
        "hazards": ["slippery"]
      }
    }
  }
}
```

Then access in engine:

```python
room = self.world.get_room(player["current_room"])
if hasattr(room, 'environment') and room.environment.get('light_level') == 'dark':
    return "It's too dark to see anything!"
```

---

## Testing

### Test Suite

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=mud_server --cov-report=html
open htmlcov/index.html

# Run specific test file
pytest tests/test_database.py -v

# Run tests matching pattern
pytest -k "test_auth" -v
```

### Code Quality

```bash
# Linting (Ruff)
ruff check src/ tests/

# Formatting check (Black)
black --check src/ tests/

# Type checking (mypy)
mypy src/ --ignore-missing-imports

# Security audit
pip install pip-audit
pip-audit
```

### Continuous Integration

Every push and pull request runs:
- ✅ Tests on Python 3.12 and 3.13
- ✅ Code linting with Ruff
- ✅ Formatting check with Black
- ✅ Type checking with mypy
- ✅ Coverage reporting to Codecov
- ✅ Security scanning with pip-audit

---

## Contributing

Contributions are welcome! This project is in active development.

### Areas for Contribution

- Bug fixes and stability improvements
- Test coverage expansion
- Documentation improvements
- Performance optimizations
- UI/UX enhancements
- Additional commands and game mechanics
- World builder tools
- Plugin system architecture

### Development Process

1. **Fork the repository**
1. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
1. **Make your changes** with tests
1. **Ensure tests pass** (`pytest`)
1. **Lint and format** (`ruff check`, `black`)
1. **Commit your changes** (`git commit -m 'Add amazing feature'`)
1. **Push to the branch** (`git push origin feature/amazing-feature`)
1. **Open a Pull Request**

### Code Style

- Follow PEP 8 (enforced by Black)
- Use type hints (checked by mypy)
- Write docstrings for public functions
- Keep functions focused and testable
- See [CLAUDE.md](CLAUDE.md) for architecture guidelines

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Inspired by classic MUDs and the joy of procedural world-building
- Built with [FastAPI](https://fastapi.tiangolo.com/), [Gradio](https://gradio.app/), and modern Python tooling
- Documentation generated with assistance from Claude (Anthropic)

---

## Links

- **Repository**: [GitHub](https://github.com/aa-parky/pipeworks_mud_server)
- **Developer Guide**: [CLAUDE.md](CLAUDE.md) - AI-assisted development guide
- **Issue Tracker**: [GitHub Issues](https://github.com/aa-parky/pipeworks_mud_server/issues)
- **Discussions**: [GitHub Discussions](https://github.com/aa-parky/pipeworks_mud_server/discussions)

---

**PipeWorks MUD Server** - *A foundation for building deterministic, procedural interactive fiction worlds.*
