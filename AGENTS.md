# AGENTS.md

## Foundation Must-Dos (Org-Wide)

Read and apply these before repo-specific instructions:

- Local workspace path: `../.github/.github/docs/AGENT_FOUNDATION.md`
- Local workspace path: `../.github/.github/docs/TEST_TAGGING_AND_GITHUB_CHECKLIST.md`
- Canonical URL: `https://github.com/pipe-works/.github/blob/main/.github/docs/AGENT_FOUNDATION.md`
- Canonical URL: `https://github.com/pipe-works/.github/blob/main/.github/docs/TEST_TAGGING_AND_GITHUB_CHECKLIST.md`

Mandatory requirements:

1. Run the GitHub preflight checklist before any `gh` interaction, CI edits, or
   test-tag changes.
2. Preserve required checks (`All Checks Passed`, `Secret Scan (Gitleaks)`).
3. Do not weaken test-tag semantics to reduce runtime.
4. Keep CI optimization changes evidence-based (run IDs, timings, check states).

## Project Structure & Module Organization

- `src/` contains the Python package (`mud_server`), including API, WebUI, and core game logic.
- `tests/` holds pytest suites; files follow `test_*.py`.
- `data/` stores runtime assets (e.g., `data/world_data.json`) and the SQLite DB (`data/mud.db`).
- `docs/` is Sphinx documentation.
- `scripts/`, `tools/`, and `config/` contain helper utilities and tooling configs.

## Build, Test, and Development Commands

- `python3 -m venv venv && source venv/bin/activate` to create/activate a venv.
- `pip install -e ".[dev]"` to install dev dependencies.
- `mud-server run` to start API + WebUI together.
- `python -m mud_server.api.server` for API only.
- `pytest` to run the full test suite (coverage enabled).
- `ruff check src/ tests/` to lint, `black src/ tests/` to format.
- `mypy src/ --ignore-missing-imports` for type checking.
- `cd docs && make html` to build docs locally.

## Coding Style & Naming Conventions

- Python 3.12+ (org standard).
- Black is pinned to `26.1.0`, line length 100.
- Ruff (>=0.14) and mypy (>=1.19) are required by org standards.
- Use type hints for public interfaces.

## Testing Guidelines

- Framework: `pytest` with strict markers (`--strict-markers`).
- Registered markers include `unit`, `integration`, `slow`, `requires_model`, `api`, `db`, `auth`, `game`, `admin`, `security`.
- Example: `pytest -m "not slow"` or `pytest tests/test_api/test_auth.py -v`.

## CI, Coverage, and Pre-Commit

- CI uses the pipe-works reusable workflow (`.github/workflows/ci.yml`).
- Matrix: Python 3.12 and 3.13 with fast marker-based matrix tests (`not slow and not requires_model`).
- Full coverage threshold enforcement runs once on Python 3.12 (dedicated coverage job).
- Slow/model suites run in a supplemental non-coverage lane (`slow or requires_model`).
- Security gates include Bandit/Trivy plus mandatory gitleaks secret scanning.
- Content-only pull requests can use the fast lane:
  - `Change Classification` detects content-only deltas.
  - `Content Validation` runs targeted policy/package checks.
  - Full matrix + coverage jobs are skipped only for content-only PRs in configured paths (`data/worlds/**`, `docs/**`, `*.md`).
- Weekly schedule (`cron`) runs a full-sweep CI pass on the default branch.
- Coverage threshold is 80% in this repo (org minimum is 50%).
- Pre-commit is configured in `.pre-commit-config.yaml`:
  - Install: `pip install pre-commit && pre-commit install`
  - Run all: `pre-commit run --all-files`
  - Hooks include Black, Ruff, mypy, Bandit, gitleaks, Safety, markdownlint, YAML formatting, and codespell.

## Commit & Pull Request Guidelines

- Conventional Commits are expected (Release Please uses them):
  - Examples: `feat(core): add zone loader`, `fix(data): correct room id`, `chore(main): release`.
- PRs should include a summary, test results, and note any data/schema changes.

## Security & Configuration Tips

- Use environment variables for secrets (`MUD_ADMIN_USER`, `MUD_ADMIN_PASSWORD`, `MUD_HOST`, `MUD_PORT`).
- Avoid committing secrets; prefer `.env` + tooling or OS keychain.
