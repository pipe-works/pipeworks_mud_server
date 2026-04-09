# AGENTS.md

## Foundation

This repository follows Pipe-Works org standards and reusable workflow conventions.

## Scope

- Multiplayer MUD runtime plus FastAPI-backed play and admin web surfaces.
- Canonical policy state is DB-first; publish artifacts are import/export inputs, not runtime authority.
- Local host-managed deployment is expected to run behind nginx with localhost binds.

## Workspace Layout

- Shared repos live under `/srv/work/pipeworks/repos/`.
- Shared virtual environments live under `/srv/work/pipeworks/venvs/`.
- This repo's current shared venv is `/srv/work/pipeworks/venvs/pw-mud-server`.
- Do not assume a repo-local `venv` or `.venv` is the active environment.

## Repo Shape

- `src/mud_server/` contains the application package, including CLI, API
  server, admin TUI, policy services, translation, and game runtime.
- `tests/` holds the pytest suite.
- `config/` contains `server.example.ini`; `config/server.ini` is optional host- or operator-provided config and is not committed.
- `data/` holds the SQLite database, packaged world content, and runtime-facing local assets used during development.
- `docs/` is the Sphinx documentation tree.

## Build, Test, and Development Commands

- Use the shared venv when running Python tooling for this repo:
  - `/srv/work/pipeworks/venvs/pw-mud-server/bin/python -m pip install -e "/srv/work/pipeworks/repos/pipeworks_mud_server[dev]"`
  - `/srv/work/pipeworks/venvs/pw-mud-server/bin/python -m pytest`
- Start the service with `mud-server run` or `/srv/work/pipeworks/venvs/pw-mud-server/bin/python -m mud_server.cli run`.
- Prefer host-managed settings with explicit `MUD_HOST` and `MUD_PORT` rather than relying on ad hoc defaults.
- For Luminal-style deployment, bind to `127.0.0.1` and treat nginx hostnames as canonical entry points.

## CI and Quality Gates

- CI is defined in `.github/workflows/ci.yml` and delegates to the Pipe-Works reusable Python workflow.
- Matrix coverage in this repo currently targets Python 3.12 and 3.13.
- Coverage threshold is 80%.
- Supplemental pytest lanes cover `slow` and `requires_model`.
- Content-only PR skipping is configured for `data/worlds/**`, `docs/**`, and `*.md`.
- Required security checks include gitleaks; do not weaken required checks or test-marker semantics.

## PipeWorks Neighbors

- `/srv/work/pipeworks/repos/pipeworks-namegen-api` provides the PipeWorks name generation API service.
- `/srv/work/pipeworks/repos/pipeworks-namegen-core` provides shared deterministic name generation logic.
- `/srv/work/pipeworks/repos/pipeworks-namegen-lexicon` provides lexicon and creator-workbench tooling.
- Changes here should preserve integration expectations for upstream
  name/entity/translation service URLs and related host-managed deployment
  assumptions.

## Non-Negotiables

- Keep DB-first policy/bootstrap semantics intact.
- Preserve host-managed deployment clarity: fixed localhost bind plus nginx
  front door is the steady-state model.
- Do not reintroduce stale workspace assumptions, especially repo-local
  virtualenv instructions, when `/srv/work/pipeworks` shared environments are
  the actual runtime pattern.
