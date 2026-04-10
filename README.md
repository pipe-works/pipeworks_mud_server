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

## Overview

PipeWorks MUD Server is the live PipeWorks multiplayer runtime. It is a
FastAPI-based service with a first-party admin WebUI, SQLite-backed canonical
state, and DB-first policy/bootstrap flows.

The current host model matters:

- source code lives in the repo checkout
- the live service runs under `systemd`
- the canonical runtime DB should live outside the repo checkout
- policy bootstrap imports canonical publish artifacts from
  `pipe-works-world-policies`

The repo still supports ad hoc local development, but the host-managed Luminal
model is now the important reference point for operational work.

**[Read the full documentation](https://pipeworks-mud-server.readthedocs.io/)**

## Current Luminal Shape

On `luminal.local`, the current steady-state runtime looks like this:

- repo root:
  - `/srv/work/pipeworks/repos/pipeworks_mud_server`
- venv:
  - `/srv/work/pipeworks/venvs/pw-mud-server`
- runtime DB:
  - `/srv/work/pipeworks/runtime/pipeworks_mud_server/mud.db`
- policy export root:
  - `/srv/work/pipeworks/repos/pipe-works-world-policies`
- systemd unit:
  - `pipeworks-dev.service`
- backend bind:
  - `127.0.0.1:18000`
- canonical browser entry points:
  - `https://pipeworks.luminal.local`
  - `https://admin.pipeworks.luminal.local`

This is the mental model to prefer when working on the repo:

- repo checkout is not the runtime DB home
- `systemd` owns steady-state serving
- operators run explicit bootstrap/admin commands against the same venv and DB

## Quick Start

### Repo-Local Development

For ad hoc local development, the repo still supports a simple in-checkout
workflow:

```bash
git clone https://github.com/pipe-works/pipeworks_mud_server.git
cd pipeworks_mud_server
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
mud-server init-db
mud-server create-superuser
mud-server run
```

That path is fine for local experimentation. It is not the canonical Luminal
host-managed operating model.

### Luminal Host-Managed Bootstrap

For Luminal, prefer:

1. create or reuse the dedicated venv
2. initialize the runtime DB at its explicit absolute path
3. create the first superuser interactively
4. let the live service run under `systemd`
5. access the app through nginx hostnames, not the raw backend port

Keep the exact Luminal bootstrap procedure in your local operations docs. This
repo README only summarizes the model.

## Runtime Model

### DB-First Authority

Canonical runtime state is DB-first.

- SQLite is the runtime authority for players, sessions, world catalog rows,
  policy variants, and policy activation state.
- Published artifact files are import/bootstrap inputs, not runtime authority.
- `data/worlds/<world_id>/policies/**` legacy files are no longer a canonical
  runtime source.

### Policy Bootstrap

`mud-server init-db` now does more than schema creation:

- initializes the schema
- syncs the world catalog from world packages on disk
- bootstraps canonical artifact imports for discovered worlds unless
  `--skip-policy-import` is used

Artifact discovery for host-managed runs should be explicit. When bootstrap is
expected to discover artifacts from `pipe-works-world-policies`, either:

- run `init-db` from the `pipeworks_mud_server` repo root, or
- set `MUD_POLICY_EXPORTS_ROOT=/srv/work/pipeworks/repos/pipe-works-world-policies`

so discovery does not depend on an unrelated current working directory.

### Superuser Bootstrap

The preferred Luminal pattern is interactive:

1. `/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server init-db`
2. `/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server create-superuser`

The CLI also supports environment-driven creation via `MUD_ADMIN_USER` and
`MUD_ADMIN_PASSWORD`, but that is better treated as an automation path than the
default operator workflow.

## Running The Service

### Ad Hoc Local Run

```bash
mud-server run
```

By default this is convenient for local iteration. It can auto-discover a free
port if the preferred one is already in use.

### Host-Managed Run

For host-managed deployment:

- bind to `127.0.0.1`
- keep a fixed port
- use an explicit absolute runtime DB path
- front the service with nginx

Example environment:

```bash
export MUD_HOST="127.0.0.1"
export MUD_PORT=18000
export MUD_DB_PATH="/srv/work/pipeworks/runtime/pipeworks_mud_server/mud.db"
export MUD_POLICY_EXPORTS_ROOT="/srv/work/pipeworks/repos/pipe-works-world-policies"
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server run
```

Notes:

- direct backend port access is diagnostic-only
- the live service should not rely on repo-local `data/mud.db`
- automatic port fallback is acceptable for ad hoc runs, not for systemd steady
  state

## Canonical Commands

### Initialize Schema And Bootstrap Canonical Artifacts

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server init-db
```

Use `--skip-policy-import` only when you intentionally want schema creation
without artifact bootstrap.

### Create The First Superuser

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server create-superuser
```

### Import One Canonical Policy Artifact

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server import-policy-artifact --artifact-path /abs/path/publish_<manifest_hash>.json
```

Use `--no-activate` to import or update variants without applying activation
pointers from the artifact.

### Removed Legacy Commands

These older commands were deliberately removed:

- `import-species-policies`
- `import-layer2-policies`
- `import-tone-prompt-policies`
- `import-world-policies`

Replacement:

- `mud-server import-policy-artifact --artifact-path ...`

## Worlds

World packages are still filesystem-backed and versioned in the repo:

```text
data/worlds/<world_id>/
├── world.json
├── zones/
│   └── <zone>.json
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
    "active_axes": ["demeanor", "health"]
  },
  "axis_engine": {"enabled": true}
}
```

`prompt_policy_id` is the authoritative runtime selector for translation
templates from canonical policy activation state.

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

No server code changes are required when you add or tune a world package. The
server loads world packages from disk, while canonical policy runtime state is
resolved from DB activation mappings rather than legacy world `policies/*`
files.

## Policy And Lab Integration

The mud server is the canonical runtime source for policy-aware clients such as
the Policy Workbench and related lab tooling.

Canonical authoring path (DB-first):

- `GET /api/policy-capabilities`
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

### DB-Only Operator Flow

1. Initialize DB schema and baseline world catalog:
   - `mud-server init-db`
2. Import canonical policy artifact into DB:
   - `mud-server import-policy-artifact --artifact-path <artifact.json> --activate`
3. Verify effective activation state:
   - `curl -s "http://127.0.0.1:8000/api/policy-activations?scope=<world_id>&effective=true&session_id=<sid>"`
4. Publish/export deterministic artifact:
   - `curl -s -X POST "http://127.0.0.1:8000/api/policy-publish?session_id=<sid>"`
     `-H "Content-Type: application/json" -d '{"scope":"<world_id>"}'`
5. Share artifact via `pipe-works-world-policies` artifact exchange repo; do not treat exported files as runtime authority.

For Luminal or other host-managed setups, keep the backend bound to
`127.0.0.1:<fixed-port>` and verify operator flows through the canonical nginx
hostnames after the DB/bootstrap steps succeed.

---

## Development

### Setup

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Install local hooks
pre-commit install
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

# Run configured local hooks
pre-commit run --all-files
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

# Public play UI is served by the API server at /play
# Admin WebUI is served by the API server at /admin

# Check server health
curl http://127.0.0.1:8000/health
```

### Admin TUI (Optional)

The text-based admin client is available as `pipeworks-admin-tui`:

```bash
# Install the TUI extras
pip install -e ".[admin-tui]"

# Point at a direct local server if needed
export MUD_SERVER_URL="http://127.0.0.1:8000"
pipeworks-admin-tui
```

When the service is fronted by HTTPS and Nginx, point the TUI at the canonical
hostname instead, for example:

```bash
export MUD_SERVER_URL="https://admin.pipeworks.luminal.local"
pipeworks-admin-tui
```

### Database Management

```bash
# Repo-local reset for ad hoc development
rm data/mud.db && mud-server init-db
mud-server create-superuser

# Repo-local inspection
sqlite3 data/mud.db ".schema"
sqlite3 data/mud.db "SELECT username, role, current_room FROM players;"
```

For host-managed Luminal work, use the runtime DB path explicitly instead:

```bash
export MUD_DB_PATH="/srv/work/pipeworks/runtime/pipeworks_mud_server/mud.db"
export MUD_POLICY_EXPORTS_ROOT="/srv/work/pipeworks/repos/pipe-works-world-policies"

# Fresh bootstrap against the canonical runtime DB path
cd /srv/work/pipeworks/repos/pipeworks_mud_server
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server init-db
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server create-superuser
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server import-policy-artifact --artifact-path /abs/path/publish_<manifest_hash>.json

# Inspect the runtime DB directly if needed
/srv/work/pipeworks/venvs/pw-mud-server/bin/python -c "import sqlite3; conn = sqlite3.connect('$MUD_DB_PATH'); print(conn.execute(\"SELECT username, role FROM users\").fetchall()); conn.close()"
```

### Environment Variables

```bash
# Server configuration
export MUD_HOST="127.0.0.1"                     # Bind address for host-managed deployment
export MUD_PORT=8000                            # API port
export MUD_DB_PATH="/abs/path/to/mud.db"        # Absolute runtime DB path for host-managed deployment
export MUD_POLICY_EXPORTS_ROOT="/abs/path/to/pipe-works-world-policies"
export MUD_SERVER_URL="http://127.0.0.1:8000"  # Direct Admin TUI endpoint
```

For direct ad hoc development, `mud-server run` will still use its own local
defaults if these variables are unset. For steady-state host deployment, prefer
explicit `MUD_HOST`, `MUD_PORT`, and `MUD_DB_PATH` values plus HTTPS reverse
proxying. On Luminal, that means `MUD_HOST=127.0.0.1`, a service-owned fixed
`MUD_PORT`, a runtime DB under `/srv/work/pipeworks/runtime/pipeworks_mud_server/`,
operator access via `https://pipeworks.luminal.local` and
`https://admin.pipeworks.luminal.local` rather than the raw backend port.

## CI And Contribution

Every push and pull request runs the normal Python quality gates, including
tests, Ruff, Black, mypy, docs, and security-oriented checks.

For normal repo work:

1. create a feature branch
2. make the change with tests when appropriate
3. run the relevant local checks
4. open a PR

See [CLAUDE.md](CLAUDE.md) for repo-specific architecture guidance.

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
