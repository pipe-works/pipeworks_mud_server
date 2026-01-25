# The Undertaking

> **A procedural, ledger-driven multiplayer interactive fiction system where characters are issued, not built, and failure is recorded as data.**

[![Test and Lint](https://github.com/pipe-works/pipeworks_mud_server/actions/workflows/test-and-lint.yml/badge.svg)](https://github.com/pipe-works/pipeworks_mud_server/actions/workflows/test-and-lint.yml)
[![codecov](https://codecov.io/gh/pipe-works/pipeworks_mud_server/branch/main/graph/badge.svg)](https://codecov.io/gh/pipe-works/pipeworks_mud_server)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

---

## What is The Undertaking?

**The Undertaking** is not a traditional MMO. It's a procedural accountability system where you are a low-level functionary trying to survive in a bureaucratic machine designed by people who were worse at maths than you are.

**Core Design Pillars:**

1. **Character Issuance, Not Creation** - You don't build characters; you receive them. Choose your sex, and the system issues you a complete, immutable goblin with uneven attributes, mandatory quirks, persistent failings, useless specializations, and an inherited reputation.

2. **Failure as Data, Not Punishment** - Actions are resolved through six axes (Timing, Precision, Stability, Visibility, Interpretability, Recovery Cost). Attributes don't determine success—they determine **how you fail**. Every failure is recorded in an immutable ledger.

3. **Ledgers are Truth, Newspapers are Stories** - The ledger records what actually happened (hard truth, deterministic, replayable). The newspaper interprets what happened (soft truth, narrative, biased by reputation). Both are game mechanics.

4. **Optimization is Resisted** - There is no "best build." There is no meta. Success comes from understanding how **this specific goblin** fails and learning to work within those constraints.

5. **Players Become Creators** - Start as a functionary. Learn to tinker. Eventually earn the right to use the same tools as developers to build your own content. The journey: Functionary → Tinkerer → Creator.

---

## Current Status: Proof-of-Concept

This repository contains a **working MUD server** that validates the technical architecture for The Undertaking. It's a proof-of-concept that implements:

### ✅ Currently Implemented

- **FastAPI REST API** - High-performance backend on port 8000
- **Gradio Web Interface** - Modular, professional client on port 7860
- **SQLite Database** - Player state, sessions, and chat persistence
- **Authentication System** - Password-based auth with bcrypt hashing
- **Role-Based Access Control** - 4 user types (Player, WorldBuilder, Admin, Superuser)
- **Room Navigation** - Basic MUD-style movement and exploration
- **Inventory System** - Pick up and drop items
- **Room-Based Chat** - Location-specific messaging with whisper/yell support
- **JSON World Data** - Flexible world definition system
- **Ollama Integration** - AI model management and conversational interface (admin/superuser)
- **Fully Modular Client Architecture** - Clean separation of concerns with dedicated API, UI, and tab layers
- **100% Test Coverage on Client Modules** - 191 tests covering all API clients and UI utilities
- **Centralized CSS** - External stylesheet with Safari-compatible dark mode

### ⏳ Designed But Not Yet Implemented

The complete vision is documented in `docs/`. Planned features include:

- **Character Issuance System** - Procedural goblin generation with quirks, failings, and useless bits
- **Axis-Based Resolution** - Six-axis action resolution replacing simple commands
- **Ledger and Newspaper** - Dual-layer truth system (hard + soft)
- **Item Quirks** - Items as frozen decisions carrying maker's attributes
- **Environmental Quirks** - Rooms that affect how actions resolve
- **Reputation System** - Blame attribution and social dynamics
- **Creator's Toolkit** - Gradio-based authoring environment for player-created content

See the [Implementation Roadmap](#implementation-roadmap) for details.

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
```
Username: admin
Password: admin123
```

**Change this immediately!** Login and use the user management interface to set a new password.

---

## Documentation

Comprehensive documentation is available both locally and online:

### Online Documentation

- **ReadTheDocs** (Coming Soon): https://pipeworks-mud-server.readthedocs.io/
- Full searchable documentation with API reference
- Auto-generated from code docstrings
- Always up-to-date with the latest release

### Local Documentation

Build and view the documentation locally:

```bash
# Install documentation dependencies
pip install -r requirements-docs.txt

# Build documentation
PYTHONPATH=src mkdocs build

# Serve documentation locally
PYTHONPATH=src mkdocs serve
# Then visit http://localhost:8000
```

### Documentation Sections

- **[Getting Started](documentation/getting-started/index.md)** - Installation, quick start, first steps
- **[Design Vision](documentation/design/index.md)** - Core design pillars and philosophy
- **[Architecture](documentation/architecture/index.md)** - Technical architecture and system design
- **[Implementation](documentation/implementation/index.md)** - Code examples and implementation details
- **[API Reference](documentation/api/index.md)** - Complete API documentation
- **[Developer Guide](documentation/developer/testing.md)** - Testing, contributing, code style

---

## Ollama Integration

The Ollama tab provides AI model management and conversational interface for **Admin** and **Superuser** accounts only.

### Features

- **Model Management** - List, pull, and run Ollama models
- **Conversational Mode** - Natural chat interface with AI models
- **Slash Commands** - Command-line style interaction
- **Server Configuration** - Connect to local or remote Ollama servers

### Slash Commands

The Ollama tab supports these commands:

| Command | Description | Example |
|---------|-------------|---------|
| `/list` or `/ls` | List all available models | `/list` |
| `/ps` | Show currently running models | `/ps` |
| `/pull <model>` | Download a new model | `/pull llama2` |
| `/run <model> [prompt]` | Run a model with optional prompt | `/run llama2 Write a haiku` |
| `/show <model>` | Show detailed model information | `/show llama2` |

### Conversational Mode

After starting a model with `/run <model> [prompt]`, you can continue chatting naturally without repeating the `/run` prefix:

```
> /run llama2 Hello, who are you?
[Model responds...]

> What can you help me with?
[Model continues conversation...]

> Tell me a joke
[Model continues conversation...]
```

The system remembers your active model until you start a new `/run` command with a different model.

### Configuration

**Default Ollama Server**: `http://localhost:11434`

To use a remote Ollama server, change the Server URL in the Ollama tab interface.

---

## Documentation

Comprehensive design documentation is in the `docs/` directory:

| Document | Description |
|----------|-------------|
| **[docs/README.md](docs/README.md)** | Overview of all design documents |
| **[docs/the_undertaking_articulation.md](docs/the_undertaking_articulation.md)** | Core design with five pillars and worked examples |
| **[docs/the_undertaking_platform_vision.md](docs/the_undertaking_platform_vision.md)** | Unified platform vision (Engine + Toolkit) |
| **[docs/undertaking_code_examples.md](docs/undertaking_code_examples.md)** | Pseudo-code and database schema for full implementation |
| **[docs/undertaking_supplementary_examples.md](docs/undertaking_supplementary_examples.md)** | Content libraries, API examples, testing scenarios |
| **[CLAUDE.md](CLAUDE.md)** | Developer guide with current implementation and roadmap |

---

## Architecture

### Modular Client Design

The Gradio web client uses a fully modular architecture for maintainability, testability, and scalability:

- **app.py** (~180 lines) - Clean entry point that assembles the interface
- **api/** - Modular API client layer with clean separation of concerns
  - **base.py** - BaseAPIClient with common HTTP patterns
  - **auth.py** - Authentication operations (login, register, logout)
  - **game.py** - Game operations (commands, chat, status, refresh)
  - **settings.py** - Settings and server control
  - **admin.py** - Admin database operations and user management
  - **ollama.py** - Ollama AI model operations
- **ui/** - UI utilities separate from API logic
  - **validators.py** - Input validation functions (100% test coverage)
  - **state.py** - Gradio state builders for UI updates
- **utils.py** - Shared utilities (CSS loading, session state initialization)
- **static/styles.css** - Centralized CSS with Safari-compatible dark mode
- **tabs/** - Individual modules for each interface tab (login, game, settings, database, ollama, help)

**Benefits:**
- Clear separation between API logic, validation, and UI concerns
- 100% test coverage on API and UI utility modules (191 tests)
- API clients can be used outside Gradio (CLI tools, tests, scripts)
- Easy to test individual components with mocked HTTP requests
- Simple to add new features or tabs
- Better code organization and navigation
- Externalized CSS for better syntax highlighting and maintenance
- Type-safe with comprehensive type hints throughout

### Three-Tier Design

```
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

### Project Structure

```
pipeworks_mud_server/
├── src/mud_server/              # Main application package
│   ├── api/                     # FastAPI REST API
│   │   ├── server.py            # App initialization
│   │   ├── routes.py            # API endpoints
│   │   ├── models.py            # Pydantic models
│   │   ├── auth.py              # Session management
│   │   ├── password.py          # Password hashing
│   │   └── permissions.py       # RBAC system
│   ├── core/                    # Game engine
│   │   ├── engine.py            # Game logic
│   │   └── world.py             # World management
│   ├── db/                      # Database layer
│   │   └── database.py          # SQLite operations
│   └── client/                  # Frontend (fully modular architecture)
│       ├── app.py               # Main entry point (~180 lines)
│       ├── api/                 # API client layer (clean HTTP communication)
│       │   ├── __init__.py      # Package initialization
│       │   ├── base.py          # BaseAPIClient - common HTTP patterns
│       │   ├── auth.py          # AuthAPIClient - authentication
│       │   ├── game.py          # GameAPIClient - game operations
│       │   ├── settings.py      # SettingsAPIClient - settings & server
│       │   ├── admin.py         # AdminAPIClient - admin operations
│       │   └── ollama.py        # OllamaAPIClient - AI model management
│       ├── ui/                  # UI utilities (separate from API)
│       │   ├── __init__.py      # Package initialization
│       │   ├── validators.py    # Input validation (100% coverage)
│       │   └── state.py         # Gradio state builders
│       ├── utils.py             # Shared utilities (CSS loading, state)
│       ├── static/              # Static assets
│       │   └── styles.css       # Centralized CSS (Safari-compatible)
│       └── tabs/                # UI tab modules
│           ├── __init__.py      # Package initialization
│           ├── login_tab.py     # Login interface
│           ├── register_tab.py  # Registration interface
│           ├── game_tab.py      # Main gameplay interface
│           ├── settings_tab.py  # Settings and server control
│           ├── database_tab.py  # Database viewer and user management
│           ├── ollama_tab.py    # Ollama AI model management
│           └── help_tab.py      # Help documentation
├── data/                        # Data files
│   ├── world_data.json          # Room and item definitions
│   └── mud.db                   # SQLite database (generated)
├── docs/                        # Design documentation
├── tests/                       # Test files
├── logs/                        # Application logs
└── requirements.txt             # Python dependencies
```

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

**Note on Client Architecture**: The Gradio client (`src/mud_server/client/`) uses a fully modular design with clear separation of concerns. When adding new features:

1. **API Layer** (`api/` directory):
   - Add new API client classes inheriting from `BaseAPIClient`
   - Each client handles one domain (auth, game, settings, admin, ollama)
   - Return standardized dicts: `{"success": bool, "message": str, "data": dict|None, "error": str|None}`
   - Write comprehensive tests with 100% coverage

2. **UI Layer** (`ui/` directory):
   - Add new validators to `validators.py` for input validation
   - Add new state builders to `state.py` for Gradio UI updates
   - Keep UI logic separate from API logic

3. **Tab Modules** (`tabs/` directory):
   - Create new tab files for new interface sections
   - Import API clients and UI utilities
   - Wire up event handlers

4. **Shared Resources**:
   - Add shared utilities to `utils.py`
   - Update CSS in `static/styles.css`
   - Wire everything together in `app.py`

**Benefits of this structure**:
- API clients can be tested in isolation with mocked HTTP
- API clients work outside Gradio (CLI tools, scripts, tests)
- Validators and state builders are pure functions, easy to test
- Clear separation makes code easier to understand and maintain

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

## Implementation Roadmap

The proof-of-concept validates the architecture. Full implementation follows these phases:

### Phase 1: Character Issuance
- Character generator with procedural attributes
- Quirks, failings, and useless bits system
- Immutable character sealing
- Name generation with weighted pools

### Phase 2: Resolution Engine
- Axis-based resolution system (6 axes)
- Quirk modifier application
- Deterministic outcome calculation
- Seed-based replay capability

### Phase 3: Ledger System
- Ledger table for immutable action records
- Contributing factors tracking
- Blame weight calculation
- Deterministic truth recording

### Phase 4: Interpretation Layer
- Newspaper generation from ledger
- Reputation system
- Narrative tone and bias
- LLM integration for soft truth

### Phase 5: Items and Rooms
- Item quirks and maker profiles
- Environmental quirks for rooms
- Context-dependent interactions
- Player-created content support

### Phase 6: Creator's Toolkit
- Gradio authoring interfaces
- Content creation tools
- Player-to-creator progression
- Content sharing and publication

---

## Testing

The project uses comprehensive testing with GitHub Actions CI/CD:

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

**Current Implementation:**
- Bug fixes and stability improvements
- Test coverage expansion
- Documentation improvements
- Performance optimizations
- UI/UX enhancements for existing tabs
- Additional Ollama features and integrations

**Planned Features:**
- Character issuance system implementation
- Axis-based resolution engine
- Ledger and newspaper systems
- Content library development
- UI/UX enhancements

### Development Process

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes** with tests
4. **Ensure tests pass** (`pytest`)
5. **Lint and format** (`ruff check`, `black`)
6. **Commit your changes** (`git commit -m 'Add amazing feature'`)
7. **Push to the branch** (`git push origin feature/amazing-feature`)
8. **Open a Pull Request**

### Code Style

- Follow PEP 8 (enforced by Black)
- Use type hints (checked by mypy)
- Write docstrings for public functions
- Keep functions focused and testable
- See `CLAUDE.md` for architecture guidelines

---

## Design Philosophy

### Programmatic vs. LLM Responsibilities

**Programmatic systems are AUTHORITATIVE:**
- All game logic and state
- Character generation and attributes
- Resolution math and axis calculations
- Ledger truth and contributing factors

**LLMs are NON-AUTHORITATIVE (narrative only):**
- Descriptions and flavor text
- Newspaper copy and interpretations
- Tone and voice
- Help text and explanations

This separation prevents hallucinated mechanics, balance drift, and schema corruption.

### Key Principles

1. **Determinism First** - All game logic must be deterministic and replayable from seed
2. **Ledger is Truth** - The ledger is the source of authority; everything else is interpretation
3. **Resistance to Optimization** - Design choices that resist meta-gaming
4. **Gradual Disclosure** - Players discover quirks through failure
5. **Context Matters** - Same action fails differently based on character + item + room
6. **Blame Attribution** - Always track who/what is responsible for outcomes

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Inspired by classic MUDs and the magic of tinkering with systems
- Built with [FastAPI](https://fastapi.tiangolo.com/), [Gradio](https://gradio.app/), and love for procedural generation
- Design documentation generated with assistance from Claude (Anthropic)

---

## Links

- **Documentation**:
  - [ReadTheDocs](https://pipeworks-mud-server.readthedocs.io/) (Coming Soon)
  - [Local Docs](documentation/) - Full documentation source
  - [Original Design Docs](docs/README.md) - Original design documentation
- **Developer Resources**:
  - [Claude Code Guide](CLAUDE.md) - AI-assisted development guide
  - [API Documentation](documentation/api/index.md) - Auto-generated API reference
  - [Testing Guide](documentation/developer/testing.md) - Testing and code quality
- **Community**:
  - [GitHub Repository](https://github.com/aa-parky/pipeworks_mud_server)
  - [Issue Tracker](https://github.com/aa-parky/pipeworks_mud_server/issues)
  - [Discussions](https://github.com/aa-parky/pipeworks_mud_server/discussions)

---

**The Undertaking** - *A game about learning to survive as yourself, not about becoming powerful.*
