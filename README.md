# PipeWorks MUD Server

> **A deterministic, procedural multiplayer text game engine for building accountable interactive fiction worlds.**

<!-- markdownlint-disable MD013 -->
[![CI][ci-badge]][ci-url]
[![Documentation][docs-badge]][docs-url]
[![codecov][codecov-badge]][codecov-url]
[![Python 3.12+][python-badge]][python-url]
[![License: GPL v3][license-badge]][license-url]
[![Code style: black][black-badge]][black-url]
[![Ruff][ruff-badge]][ruff-url]

<!-- markdownlint-disable-next-line MD013 -->
[ci-badge]: https://github.com/pipe-works/pipeworks_mud_server/actions/workflows/ci.yml/badge.svg
<!-- markdownlint-disable-next-line MD013 -->
[ci-url]: https://github.com/pipe-works/pipeworks_mud_server/actions/workflows/ci.yml
<!-- markdownlint-disable-next-line MD013 -->
[docs-badge]: https://readthedocs.org/projects/pipeworks-mud-server/badge/?version=latest
<!-- markdownlint-disable-next-line MD013 -->
[docs-url]: https://pipeworks-mud-server.readthedocs.io/en/latest/?badge=latest
<!-- markdownlint-disable-next-line MD013 -->
[codecov-badge]: https://codecov.io/gh/pipe-works/pipeworks_mud_server/branch/main/graph/badge.svg
<!-- markdownlint-disable-next-line MD013 -->
[codecov-url]: https://codecov.io/gh/pipe-works/pipeworks_mud_server
<!-- markdownlint-disable-next-line MD013 -->
[python-badge]: https://img.shields.io/badge/python-3.12+-blue.svg
<!-- markdownlint-disable-next-line MD013 -->
[python-url]: https://www.python.org/downloads/
<!-- markdownlint-disable-next-line MD013 -->
[license-badge]: https://img.shields.io/badge/License-GPLv3-blue.svg
<!-- markdownlint-disable-next-line MD013 -->
[license-url]: https://www.gnu.org/licenses/gpl-3.0
<!-- markdownlint-disable-next-line MD013 -->
[black-badge]: https://img.shields.io/badge/code%20style-black-000000.svg
<!-- markdownlint-disable-next-line MD013 -->
[black-url]: https://github.com/psf/black
<!-- markdownlint-disable-next-line MD013 -->
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
<!-- markdownlint-disable-next-line MD013 -->
[ruff-url]: https://github.com/astral-sh/ruff
<!-- markdownlint-enable MD013 -->

---

## What is PipeWorks MUD Server?

A **generic, extensible MUD (Multi-User Dungeon) server** for building text-based multiplayer
games. Built with modern Python tooling, this server provides the technical foundation for
creating interactive fiction worlds with:

- **Deterministic game mechanics** - Reproducible outcomes for testing and replay
- **JSON-driven world data** - Define rooms, items, and connections without code changes
- **Modern web interface** - First-party admin WebUI with clean UX
- **REST API backend** - FastAPI server for high performance
- **Role-based access control** - Built-in auth and permission system
- **Modular architecture** - Clean separation between client, server, and game logic

**Use it to build:** Fantasy MUDs, sci-fi adventures, educational games, procedural narratives,
or any text-based multiplayer experience.

**[Read the full documentation](https://pipeworks-mud-server.readthedocs.io/)**

---

## Quick Start

### Prerequisites

- Python 3.12 or 3.13
- pip (Python package manager)
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/pipe-works/pipeworks_mud_server.git
cd pipeworks_mud_server

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package (enables mud-server CLI)
pip install -e .

# Initialize database and create superuser
mud-server init-db
mud-server create-superuser  # Follow prompts to create admin account
```

`mud-server init-db` now bootstraps canonical policy objects/activations for
the configured default world. Use `--skip-policy-import` only when you need a
schema-only setup.

### Running the Server

```bash
# Start API server and admin WebUI
mud-server run

# The server will start on:
# - API + Web UI: http://localhost:8000 (Admin UI at /admin)
```

Press `Ctrl+C` to stop the service.

### Admin UI Security (Production)

The admin Web UI is served by the same API process at `/admin`. In production:

- Run behind Nginx and bind the API to `127.0.0.1`.
- Expose the admin UI on a separate admin domain.
- Protect the admin domain with mTLS or an IP allowlist.

See `docs/source/admin_web_ui_mtls.rst` for a full mTLS deployment guide.

### Creating a Superuser

**Interactive** (recommended):

```bash
mud-server create-superuser
# Enter username and password when prompted
```

### Canonical Artifact Import (DB-First)

Canonical policy state is now imported from deterministic publish artifacts.
Legacy file-import commands were removed.

```bash
mud-server import-policy-artifact --artifact-path /abs/path/publish_<manifest_hash>.json
```

Use `--no-activate` to import/update variants without applying activation
pointers from the artifact.

### Breaking Changes: Legacy Import Command Removal

The following commands were removed:

1. `import-species-policies`
2. `import-layer2-policies`
3. `import-tone-prompt-policies`
4. `import-world-policies`

Replacement command:

1. `import-policy-artifact --artifact-path ...`

### Migration Note (Legacy Files)

`data/worlds/<world_id>/policies/**` files are no longer a runtime or bootstrap
authority. Canonical runtime reads DB activation + variant state only. Legacy
files should be treated as historical content artifacts unless explicitly
converted into publish artifacts.

### Command Replacement Table

| Removed Command | Replacement |
|---|---|
| `mud-server import-species-policies --world-id <world>` | `mud-server import-policy-artifact --artifact-path <publish_*.json>` |
| `mud-server import-layer2-policies --world-id <world>` | `mud-server import-policy-artifact --artifact-path <publish_*.json>` |
| `mud-server import-tone-prompt-policies --world-id <world>` | `mud-server import-policy-artifact --artifact-path <publish_*.json>` |
| `mud-server import-world-policies --world-id <world>` | `mud-server import-policy-artifact --artifact-path <publish_*.json>` |

---

## Features

### Implemented

- **FastAPI REST API** - High-performance backend (port 8000)
- **Admin WebUI** - First-party dashboard served from the API (`/admin`)
- **SQLite Database** - Player state, sessions, and chat persistence
- **Authentication System** - Password-based auth with bcrypt hashing
- **Role-Based Access Control (RBAC)** - 4 user types (Player, WorldBuilder, Admin, Superuser)
- **Room Navigation** - Directional movement between connected rooms
- **Inventory System** - Pick up and drop items in rooms
- **Multi-Channel Chat** - Room-based `say`, area-wide `yell`, targeted `whisper`
- **JSON World Definition** - Data-driven room and item configuration
- **Ollama Integration** - AI model management interface (admin/superuser only)
- **Modular Client Architecture** - Clean API/UI separation with high test coverage

### Design Philosophy

**Programmatic Authority:**

- All game logic and state is deterministic and code-driven
- Game mechanics are reproducible and testable
- No LLM involvement in authoritative systems (state, logic, resolution)

**Extensibility First:**

- World data is JSON-driven (swap worlds without code changes)
- Commands are extensible (add new actions without server rewrites)
- Modular architecture supports plugins and custom mechanics

---

## Creating Your Own World

The MUD server is **fully data-driven**. Worlds now live under `data/worlds/<world_id>/` as self-contained packages:

```text
data/worlds/<world_id>/
├── world.json
├── zones/
│   └── <zone>.json
└── policies/
    ├── axes.yaml
    ├── thresholds.yaml
    ├── resolution.yaml
    └── ic_prompt.txt
```

A minimal world package looks like this:

```json
{
  "name": "My World",
  "description": "A custom world package.",
  "version": "0.1.0",
  "default_spawn": {"zone": "my_world", "room": "spawn"},
  "zones": ["my_world"],
  "global_items": {},
  "translation_layer": {
    "enabled": true,
    "model": "gemma2:2b",
    "prompt_policy_id": "prompt:translation.prompts.ic:default",
    "prompt_template_path": "policies/ic_prompt.txt",
    "active_axes": ["demeanor", "health"]
  },
  "axis_engine": {"enabled": true}
}
```

`prompt_policy_id` is the authoritative runtime selector. `prompt_template_path`
is retained as legacy metadata for migration/debug context and is not runtime
authority in DB-first policy resolution.

And the zone data lives separately in `zones/<zone>.json`:

```json
{
  "id": "my_world",
  "name": "My World",
  "rooms": {
    "spawn": {
      "id": "spawn",
      "name": "Spawn Zone",
      "description": "A central gathering point.",
      "exits": {"north": "library"},
      "items": []
    },
    "library": {
      "id": "library",
      "name": "Ancient Library",
      "description": "Dusty books line the shelves.",
      "exits": {"south": "spawn"},
      "items": ["dusty_book"]
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

No server code changes are required when you add a new world package or tune
its policies. The server loads the world from disk and the axis engine and
translation layer read canonical runtime policy state from DB activation
mappings. World `policies/*` files are import/bootstrap sources and artifact
exchange outputs, not runtime authority.

## Axis Descriptor Lab Integration

The mud server is now the canonical source of truth for policy objects used by
the Policy Workbench and other clients.

Canonical authoring path (DB-first):

- `GET /api/policies`
- `GET /api/policies/{policy_id}`
- `POST /api/policies/{policy_id}/validate`
- `PUT /api/policies/{policy_id}/variants/{variant}`
- `POST /api/policy-activations`
- `GET /api/policy-activations`
- `POST /api/policy-publish`

Lab integration endpoints (DB-first, runtime-safe):

- `GET /api/lab/worlds`
- `GET /api/lab/world-config/{world_id}`
- `GET /api/lab/world-image-policy-bundle/{world_id}`
- `POST /api/lab/compile-image-prompt`
- `POST /api/lab/translate`

Legacy lab file-authoring routes (`/api/lab/world-prompts/*`,
`/api/lab/world-policy-bundle/*`) have been removed as a deliberate breaking
change. Canonical runtime state now comes only from SQLite policy tables plus
Layer 3 activation pointers.

DB-only runtime semantics:

- `policy_variant.status` tracks workflow state (`draft/candidate/active/archived`)
- `policy_activation` selects effective runtime variants by scope
- runtime reads use effective activations, not world `policies/*` files
- world policy files are migration/import inputs or exchange artifacts only

### DB-Only Operator Runbook

1. Initialize DB schema and baseline world catalog:
   - `mud-server init-db`
2. Import canonical policy artifact into DB:
   - `mud-server import-policy-artifact --artifact-path <artifact.json> --activate`
3. Verify effective activation state:
   - `curl -s "http://127.0.0.1:8000/api/policy-activations?scope=<world_id>&effective=true&session_id=<sid>"`
4. Publish/export deterministic artifact:
   - `curl -s -X POST "http://127.0.0.1:8000/api/policy-publish?session_id=<sid>"`
     `-H "Content-Type: application/json" -d '{"scope":"<world_id>"}'`
5. Share artifact via `pipe-works-world-policies` mirror repo; do not treat mirror files as runtime authority.

---

## Available Commands

### Movement

- `north` / `n`, `south` / `s`, `east` / `e`, `west` / `w`
- `up` / `u`, `down` / `d`

### Observation

- `look` / `l` - Observe your current surroundings
- `inventory` / `inv` / `i` - Check your inventory

### Items

- `pickup <item>` / `get <item>` - Pick up an item from the room
- `drop <item>` - Drop an item from your inventory

### Communication

- `say <message>` - Speak to others in the same room
- `yell <message>` - Shout to nearby areas
- `whisper <username> <message>` - Send a private message

### Utility

- `who` - See all players online
- `help` - Show help information

---

## Development

### Setup

```bash
# Install with development dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_api/test_auth.py -v

# Run tests matching pattern
pytest -k "test_login"

# Skip coverage for faster iteration
pytest --no-cov
```

### API Notes

- `register_routes` moved to `mud_server.api.routes.register` (the package root no longer re-exports it).

### Code Quality

```bash
# Lint
ruff check src/ tests/

# Format
black src/ tests/

# Type check
mypy src/ --ignore-missing-imports
```

### Building Documentation

Documentation is built with [Sphinx](https://www.sphinx-doc.org/) and hosted on [ReadTheDocs](https://pipeworks-mud-server.readthedocs.io/).

```bash
# Install docs dependencies
pip install -e ".[docs]"

# Build HTML documentation locally
cd docs
make html

# View in browser
open build/html/index.html  # macOS
xdg-open build/html/index.html  # Linux
```

### Running Components Separately

```bash
# Run API server only
python -m mud_server.api.server

# Admin WebUI is served by the API server at /admin

# Check server health
curl http://localhost:8000/health
```

### Admin TUI (Optional)

The text-based admin client is available as `pipeworks-admin-tui`:

```bash
# Install the TUI extras
pip install -e ".[admin-tui]"

# Point at a remote server if needed
export MUD_SERVER_URL="http://localhost:8000"
pipeworks-admin-tui
```

### Database Management

```bash
# Reset database (deletes all player data)
rm data/mud.db && mud-server init-db
mud-server create-superuser  # Create admin after reset

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
export MUD_SERVER_URL="http://localhost:8000"  # Admin TUI endpoint
```

---

## Continuous Integration

Every push and pull request runs:

- Fast matrix tests on Python 3.12 and 3.13
- Full coverage suite on Python 3.12
- Code linting with Ruff
- Formatting check with Black
- Type checking with mypy
- Coverage reporting to Codecov
- Secret scanning with gitleaks
- Security scanning with Bandit and Trivy
- Documentation build with Sphinx

---

## Contributing

Contributions are welcome! This project is in active development.

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
- See [CLAUDE.md](CLAUDE.md) for architecture guidelines

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

## Links

- **Documentation**: [ReadTheDocs](https://pipeworks-mud-server.readthedocs.io/)
- **Repository**: [GitHub](https://github.com/pipe-works/pipeworks_mud_server)
- **Issue Tracker**: [GitHub Issues](https://github.com/pipe-works/pipeworks_mud_server/issues)
- **Developer Guide**: [CLAUDE.md](CLAUDE.md)

---

**PipeWorks MUD Server** - *A foundation for building deterministic, procedural interactive fiction worlds.*
