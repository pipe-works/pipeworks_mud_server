[![CI](https://github.com/pipe-works/pipeworks_mud_server/actions/workflows/ci.yml/badge.svg)](https://github.com/pipe-works/pipeworks_mud_server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pipe-works/pipeworks_mud_server/branch/main/graph/badge.svg)](https://codecov.io/gh/pipe-works/pipeworks_mud_server)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# PipeWorks MUD Server

PipeWorks MUD Server is the canonical multiplayer runtime in the PipeWorks
ecosystem. It provides the FastAPI API surface, the browser admin and play
surfaces, the SQLite-backed canonical runtime state, and the bootstrap/import
flows that turn published policy artifacts into active runtime behavior.

## PipeWorks Workspace

These repositories are designed to live inside a shared PipeWorks workspace
rooted at `/srv/work/pipeworks`.

- `repos/` contains source checkouts only.
- `venvs/` contains per-project virtual environments such as `pw-mud-server`.
- `runtime/` contains mutable runtime state such as databases, exports, session
  files, and caches.
- `logs/` contains service-owned log output when a project writes logs outside
  the process manager.
- `config/` contains workspace-level configuration files that should not be
  treated as source.
- `bin/` contains optional workspace helper scripts.
- `home/` is reserved for workspace-local user data when a project needs it.

Across the PipeWorks ecosphere, the rule is simple: keep source in `repos/`,
keep mutable state outside the repo checkout, and use explicit paths between
repos when one project depends on another.

## What This Repo Owns

This repository is the source of truth for:

- the `mud-server` CLI and `pipeworks-admin-tui` entry points
- the FastAPI API server and browser-served admin/play UIs
- canonical runtime storage in SQLite
- world package loading from `data/worlds/`
- policy artifact import, activation, and runtime policy APIs
- game logic, session/auth flows, event materialization, and translation
  orchestration

This repository does not own:

- published policy artifacts as a distribution format
- name-generation corpus and lexicon authoring
- non-authoritative lab tooling such as Axis Descriptor Lab

## Runtime Model

The server is DB-first.

- SQLite is the canonical runtime store for accounts, sessions, world catalog
  rows, policy variants, and policy activation state.
- Published artifacts from `pipe-works-world-policies` are import/bootstrap
  inputs, not runtime authority.
- World packages remain filesystem-backed under `data/worlds/<world_id>/`.
- LLM-backed translation is non-authoritative flavour output and does not become
  source of truth.

The server also maintains a JSONL event ledger. At present, that ledger still
resolves to repo-local `data/ledger/` paths in code. The workspace examples
below therefore externalize the runtime DB while documenting the current
ledger-path limitation honestly.

## Repository Layout

- `src/mud_server/api/` FastAPI app, route registration, auth, and schemas
- `src/mud_server/core/` game engine, world loading, and event flow
- `src/mud_server/db/` SQLite schema and repository layer
- `src/mud_server/services/policy/` policy import, publish, and path resolution
- `src/mud_server/translation/` OOC to IC translation orchestration
- `src/mud_server/admin_tui/` optional terminal admin client
- `src/mud_server/web/` browser UI templates and static assets
- `data/worlds/` versioned world packages loaded by the server
- `deploy/` checked-in deployment templates (systemd unit, env reference, nginx)
- `examples/` example clients and usage material
- `docs/` Sphinx documentation
- `tests/` pytest suite

## Quick Start

### Requirements

- Python `>=3.12`
- Git access to the private `pipeworks-ipc` dependency referenced in
  `pyproject.toml`
- a PipeWorks workspace rooted at `/srv/work/pipeworks`
- `pipe-works-world-policies` checked out if you want canonical policy bootstrap

### Install

From the repo root:

```bash
python3 -m venv /srv/work/pipeworks/venvs/pw-mud-server
/srv/work/pipeworks/venvs/pw-mud-server/bin/pip install -e ".[dev]"
```

If you also want the terminal admin client:

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/pip install -e ".[dev,admin-tui]"
```

### Bootstrap Canonical Runtime State

The canonical runtime DB should live outside the repo checkout:

```bash
export MUD_DB_PATH=/srv/work/pipeworks/runtime/pipeworks_mud_server/mud.db
export MUD_POLICY_EXPORTS_ROOT=/srv/work/pipeworks/repos/pipe-works-world-policies
export MUD_WORLDS_ROOT=/srv/work/pipeworks/repos/pipeworks_mud_server/data/worlds

/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server init-db
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server create-superuser
```

`init-db` does more than schema creation. It also syncs the world catalog and,
unless `--skip-policy-import` is supplied, imports canonical world artifacts
using `latest.json` pointers from the policy export repo.

### Run The Server

```bash
export MUD_HOST=127.0.0.1
export MUD_PORT=18000
export MUD_DB_PATH=/srv/work/pipeworks/runtime/pipeworks_mud_server/mud.db
export MUD_POLICY_EXPORTS_ROOT=/srv/work/pipeworks/repos/pipe-works-world-policies
export MUD_WORLDS_ROOT=/srv/work/pipeworks/repos/pipeworks_mud_server/data/worlds

/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server run
```

Default browser entry points for that example are:

- `http://127.0.0.1:18000/`
- `http://127.0.0.1:18000/admin`
- `http://127.0.0.1:18000/play`

## Core Commands

Initialize schema and import canonical world artifacts:

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server init-db
```

Skip artifact import if you only want schema bootstrap:

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server init-db --skip-policy-import
```

Create the first superuser interactively:

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server create-superuser
```

Import one published policy artifact explicitly:

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/mud-server import-policy-artifact \
  --artifact-path /srv/work/pipeworks/repos/pipe-works-world-policies/worlds/<world_id>/<scope>/publish_<manifest_hash>.json
```

Run the optional terminal admin client:

```bash
MUD_SERVER_URL=http://127.0.0.1:18000 \
/srv/work/pipeworks/venvs/pw-mud-server/bin/pipeworks-admin-tui
```

## Configuration

Configuration resolves in this order:

1. environment variables
2. `config/server.ini` in the repo
3. built-in defaults

The most important runtime variables for workspace-backed development are:

- `MUD_DB_PATH` for the canonical SQLite database path
- `MUD_POLICY_EXPORTS_ROOT` for the policy export repo root
- `MUD_WORLDS_ROOT` for the world package root
- `MUD_HOST` and `MUD_PORT` for the API bind address
- `MUD_NAMEGEN_BASE_URL` for name-generation integration
- `MUD_ENTITY_STATE_BASE_URL` for entity-state integration
- `MUD_TRANSLATION_OLLAMA_URL` for translation rendering

The repo still ships `config/server.example.ini` and repo-local defaults, but
workspace-backed runs should prefer explicit environment variables or a
workspace-managed config copy under `/srv/work/pipeworks/config/`.

## Hosted Service Posture

For hosted service use the expected bind is driven by external environment
variables set in the systemd unit.

Current Luminal-oriented host-managed posture:

- bind host `127.0.0.1`
- bind port `18000`
- nginx front door at `https://admin.pipeworks.luminal.local`
- `MUD_NAMEGEN_BASE_URL` must point to the **backend port directly**
  (`http://127.0.0.1:8360`) rather than the nginx front door — service-to-service
  calls within the host must not go through HTTPS to avoid TLS certificate
  verification failures

Do not treat the repo-local defaults as the hosted-service truth.

### Deploy Templates

Checked-in templates for the Luminal posture live under `deploy/`:

- `deploy/systemd/pipeworks-dev.service` — systemd unit with all `Environment=`
  lines that must be set on a new host
- `deploy/env/mud-server.env.example` — annotated reference for every recognised
  environment variable
- `deploy/nginx/admin.pipeworks.luminal.local` — nginx reverse-proxy config

Treat those as checked-in templates. Machine-specific rollout state (TLS certs,
runtime DB, policy exports) lives outside the repo.

## World Packages

World packages remain versioned in this repo:

```text
data/worlds/<world_id>/
├── world.json
└── zones/
    └── <zone>.json
```

`world.json` enables or disables runtime subsystems for that world, including
translation and axis-engine behavior. Policy activation state itself is not read
from world files; it is resolved from canonical policy rows in SQLite.

## Ecosystem Integrations

- `pipe-works-world-policies`
  Canonical published artifact source for bootstrap and explicit import flows.
- `pipeworks-policy-workbench`
  Authoring and inspection client for the server's canonical policy APIs.
- `pipeworks_axis_descriptor_lab`
  Non-authoritative inspection surface that proxies selected mud-server APIs.
- `pipeworks-namegen-api`
  Optional runtime integration for generated naming flows.
- `pipeworks_entity_state_generation`
  Optional runtime integration for structured entity-state generation.

## Development

Run the main local checks from the repo root:

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/pytest
/srv/work/pipeworks/venvs/pw-mud-server/bin/ruff check src tests
/srv/work/pipeworks/venvs/pw-mud-server/bin/black --check src tests
/srv/work/pipeworks/venvs/pw-mud-server/bin/mypy src
```

Build the docs locally:

```bash
/srv/work/pipeworks/venvs/pw-mud-server/bin/pip install -e ".[docs]"
make -C docs html
```

## Documentation

Additional documentation lives in `docs/source/`, including:

- `getting_started.rst`
- `architecture.rst`
- `api_reference.rst`
- `security.rst`
- `translation_layer.rst`

Published docs:

- <https://pipeworks-mud-server.readthedocs.io/>

## License

[GPL-3.0-or-later](LICENSE)
