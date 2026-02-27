Architecture
============

Technical architecture and system design of PipeWorks MUD Server.

Overview
--------

PipeWorks MUD Server is built around a clear separation between
**authoritative** and **non-authoritative** subsystems:

* **Programmatic = Authoritative** — game logic, axis resolution, the
  JSONL ledger, and DB materialization are deterministic and testable.
* **LLM = Non-Authoritative** — OOC→IC translation is flavour text
  rendered by a language model; it cannot mutate game state.

The server uses a modern three-tier runtime backed by a pipeline of
mechanics and translation services:

* **FastAPI backend** — RESTful API server
* **Admin WebUI** — Web-based administration dashboard
* **SQLite database** — Persistent data storage (materialized view of ledger truth)
* **JSONL ledger** — Append-only audit log (``data/ledger/<world_id>.jsonl``)
* **Axis engine** — Mechanical resolution of character state mutations
* **Translation layer** — OOC→IC text rendering via Ollama

All components are written in Python 3.12+ using modern best practices.

Three-Tier Design
-----------------

::

    ┌─────────────────────────────────────────────────────────────┐
    │                    Admin Web UI                               │
    │                     (Client Layer)                           │
    │           http://localhost:8000/admin                         │
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
    ┌──────────────────┐           ┌──────────────────────────────┐
    │  Game Engine     │           │  SQLite Database             │
    │  (Core Layer)    │◄──────────┤  (Persistence / Mat. View)  │
    │                  │           │                              │
    │ - World/Rooms    │           │ - Players / Sessions         │
    │ - Actions        │           │ - Chat Messages              │
    │ - Axis Engine ──────────────►│ - Axis Scores                │
    │ - Translation    │           │ - Event Ledger (DB)          │
    └─────────┬────────┘           └──────────────────────────────┘
              │
              ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  JSONL Ledger   data/ledger/<world_id>.jsonl                 │
    │  (Authoritative record — written before DB materialization)  │
    └──────────────────────────────────────────────────────────────┘

Chat Interaction Data Flow
--------------------------

When a player says, yells, or whispers, the engine runs a pipeline
before storing the message:

::

    Player sends "say <message>"
          │
          ▼
    1. GameEngine.chat() — validate room
          │
          ▼
    2. AxisEngine.resolve_chat_interaction()
       ├── Read speaker + listener axis scores from DB
       ├── Run resolvers (dominance_shift, shared_drain, no_effect)
       ├── Compute ipc_hash (compute_payload_hash from pipeworks_ipc)
       ├── Write chat.mechanical_resolution → JSONL ledger  ← authoritative
       └── Materialise clamped deltas into character_axis_score  ← DB
          │
          ipc_hash
          ▼
    3. OOCToICTranslationService.translate()
       ├── Build character axis profile
       ├── Render system prompt from ic_prompt.txt template
       ├── Call Ollama /api/chat
       ├── Validate output (reject PASSTHROUGH, enforce max_chars)
       └── Write chat.translation → JSONL ledger (carries same ipc_hash)
          │
          IC text (or OOC fallback)
          ▼
    4. Sanitize + store in chat_messages (SQLite)

Both ledger events are fire-and-forget (non-fatal on failure).
If the axis engine or translation layer is disabled for a world,
the pipeline short-circuits gracefully and the OOC message is stored.

WebUI Architecture
------------------

The admin WebUI is a lightweight static frontend served by FastAPI::

    src/mud_server/web/
    ├── routes.py                 # WebUI route registration
    ├── templates/                # HTML shell
    └── static/                   # CSS + JS assets

The UI calls the FastAPI endpoints directly and enforces role checks
client-side while the API enforces permissions server-side.

Package Layout
--------------

::

    src/mud_server/
    ├── api/                    # FastAPI REST API
    │   ├── server.py           # App init, CORS, uvicorn entry
    │   ├── routes.py           # All endpoints, command parsing
    │   ├── models.py           # Pydantic request/response schemas
    │   ├── auth.py             # DB-backed sessions with TTL
    │   ├── password.py         # bcrypt hashing via passlib
    │   └── permissions.py      # RBAC: Role + Permission enums
    ├── core/                   # Game engine
    │   ├── engine.py           # GameEngine: movement, inventory, chat
    │   │                       #   chat/yell/whisper call axis engine
    │   │                       #   then translation before storing
    │   ├── world.py            # World dataclass; loads axis engine +
    │   │                       #   translation service at startup
    │   ├── bus.py              # Event bus (publish-subscribe)
    │   └── events.py           # Event type constants
    ├── axis/                   # Axis resolution engine  ← NEW
    │   ├── __init__.py         # Exports: AxisEngine, AxisResolutionResult
    │   ├── types.py            # AxisDelta, EntityResolution, AxisResolutionResult
    │   ├── grammar.py          # ResolutionGrammar loader (resolution.yaml)
    │   ├── resolvers.py        # dominance_shift, shared_drain, no_effect
    │   └── engine.py           # AxisEngine class
    ├── ledger/                 # JSONL audit ledger  ← NEW
    │   ├── __init__.py         # Exports: append_event, verify_world_ledger
    │   └── writer.py           # append_event, verify, checksum, file lock
    ├── translation/            # OOC→IC translation layer  ← NEW
    │   ├── __init__.py
    │   ├── config.py           # TranslationLayerConfig (frozen dataclass)
    │   ├── profile_builder.py  # CharacterProfileBuilder (axis snapshot)
    │   ├── renderer.py         # OllamaRenderer (sync requests)
    │   ├── validator.py        # OutputValidator (PASSTHROUGH sentinel)
    │   └── service.py          # OOCToICTranslationService (orchestrator)
    ├── db/                     # Database layer
    │   ├── facade.py           # App-facing DB API (used by all runtime code)
    │   ├── database.py         # Compatibility re-export surface only
    │   ├── schema.py           # DDL, indexes, invariant triggers
    │   ├── connection.py       # SQLite connection / transaction scope
    │   ├── users_repo.py
    │   ├── characters_repo.py
    │   ├── sessions_repo.py
    │   ├── chat_repo.py
    │   ├── worlds_repo.py
    │   ├── axis_repo.py        # Axis policy registry + scoring helpers
    │   ├── events_repo.py      # DB event ledger (apply_axis_event)
    │   └── admin_repo.py       # Admin dashboard read paths
    └── web/                    # Admin WebUI
        ├── routes.py
        ├── templates/
        └── static/

World Package Layout
--------------------

Each world is a self-contained directory under ``data/worlds/``::

    data/worlds/<world_id>/
    ├── world.json              # World metadata and enabled subsystems
    ├── zones/                  # Zone definitions (rooms, items)
    └── policies/
        ├── axes.yaml           # Axis registry (names, labels, ordinals)
        ├── thresholds.yaml     # Float-score → label mappings
        ├── resolution.yaml     # Chat resolver grammar  ← NEW
        └── ic_prompt.txt       # Translation system prompt template  ← NEW

``world.json`` controls which subsystems are active for a world:

.. code-block:: json

   {
     "translation_layer": {
       "enabled": true,
       "model": "gemma2:2b",
       "ollama_base_url": "http://localhost:11434"
     },
     "axis_engine": {
       "enabled": true
     }
   }

Both subsystems default to **disabled** and must be explicitly opted in.

System Components
-----------------

Backend (FastAPI)
~~~~~~~~~~~~~~~~~

Located in ``src/mud_server/api/``:

* ``server.py`` — App initialization, CORS, routing
* ``routes.py`` — All API endpoints
* ``models.py`` — Pydantic request/response models
* ``auth.py`` — Session management
* ``password.py`` — Bcrypt password hashing
* ``permissions.py`` — Role-based access control

Game Engine
~~~~~~~~~~~

Located in ``src/mud_server/core/``:

* ``engine.py`` — GameEngine class; coordinates axis engine + translation
  before storing chat messages
* ``world.py`` — World dataclass; loads and caches the axis engine and
  translation service at startup via ``_init_axis_engine`` and
  ``_init_translation_service``
* ``bus.py`` — Event bus for game event handling
* ``events.py`` — Event type constants

Axis Engine
~~~~~~~~~~~

Located in ``src/mud_server/axis/``:

* ``engine.py`` — ``AxisEngine``: coordinates resolution for all axes
  defined in the world grammar.  One instance per world, instantiated
  at startup.
* ``grammar.py`` — Loads and validates ``policies/resolution.yaml``.
  The grammar is immutable after load; field values drive resolver
  dispatch and parameter passing.
* ``resolvers.py`` — Pure stateless functions:

  * ``dominance_shift`` — winner gains, loser loses; zero below gap threshold
  * ``shared_drain`` — both entities lose a fixed health cost
  * ``no_effect`` — explicit no-op for axes not involved in an interaction

* ``types.py`` — Frozen dataclasses: ``AxisDelta``, ``EntityResolution``,
  ``AxisResolutionResult``

JSONL Ledger
~~~~~~~~~~~~

Located in ``src/mud_server/ledger/``:

* ``writer.py`` — ``append_event`` (SHA-256 checksum, POSIX
  ``fcntl.flock``), ``verify_world_ledger`` (startup integrity check),
  ``LedgerWriteError``, ``LedgerVerifyResult``

Ledger files live at ``data/ledger/<world_id>.jsonl``.  They are
**not** committed to version control (git-ignored, like ``data/*.db``).

Translation Layer
~~~~~~~~~~~~~~~~~

Located in ``src/mud_server/translation/``:

* ``service.py`` — ``OOCToICTranslationService``: orchestrates profile
  building, Ollama rendering, output validation, and ledger emit.
* ``profile_builder.py`` — ``CharacterProfileBuilder``: builds the flat
  dict injected into the system prompt template.
* ``renderer.py`` — ``OllamaRenderer``: synchronous HTTP call to
  Ollama ``/api/chat``.
* ``validator.py`` — ``OutputValidator``: rejects the PASSTHROUGH
  sentinel, enforces ``max_output_chars``.
* ``config.py`` — ``TranslationLayerConfig``: frozen dataclass loaded
  from ``world.json``.

See :doc:`translation_layer` for the full service contract and
prompt template format.

Event Bus Architecture
~~~~~~~~~~~~~~~~~~~~~~

The event bus provides publish-subscribe infrastructure for game events.
It follows these key principles:

**Synchronous Emit**: Events are committed to the log before handlers
are notified. This ensures deterministic ordering via sequence numbers.

**Immutable Events**: Once emitted, events cannot be changed. They
represent facts about what happened (Ledger truth).

**Plugin-Ready**: The bus is designed to support future plugin systems
where plugins react to events but cannot intervene or block them.

::

    ┌─────────────────────────────────────────────────────────────────┐
    │                      Event Bus                                   │
    │                                                                  │
    │    Engine.move()                                                 │
    │         │                                                        │
    │         ▼                                                        │
    │    bus.emit("player:moved", {...})                              │
    │         │                                                        │
    │         ├── 1. Increment sequence (deterministic ordering)       │
    │         │                                                        │
    │         ├── 2. Create immutable MudEvent                         │
    │         │                                                        │
    │         ├── 3. Append to event log (COMMITTED)                   │
    │         │                                                        │
    │         └── 4. Notify handlers (async execution allowed)         │
    │                                                                  │
    └─────────────────────────────────────────────────────────────────┘

Event types follow ``"domain:action"`` format in past tense (e.g.,
``player:moved``, ``item:picked_up``) to emphasize they record facts,
not requests.

Database Layer
~~~~~~~~~~~~~~

Located in ``src/mud_server/db/``:

* ``facade.py`` — app-facing DB API contract (used by API/core/services/CLI)
* ``database.py`` — legacy compatibility re-export surface (not for new
  runtime imports)
* ``schema.py`` — schema bootstrap, indexes, and invariant triggers
* ``*_repo.py`` modules — bounded-context repositories (users, characters,
  sessions, chat, worlds, axis/events, admin)

Data Flow
---------

Standard request flow (no mechanics):

1. **Client** — User interacts with the Admin WebUI
2. **API Call** — Client sends HTTP request to FastAPI
3. **Session Validation** — Server validates session and permissions
4. **Command Parsing** — Server parses command and arguments
5. **Game Logic** — Engine executes command
6. **Database** — Engine reads/writes to SQLite
7. **Response** — Server returns result to client
8. **Display** — Client updates interface

Chat interaction flow (with mechanics):

1. Session validation and room check
2. Axis engine: read scores → run resolvers → write JSONL ledger
   → materialise to DB (steps 2–8 of the resolution sequence)
3. Translation: profile build → Ollama render → validate → write
   JSONL ledger (carrying the same ``ipc_hash``)
4. Sanitize + store final message in ``chat_messages``

Technology Stack
----------------

.. list-table::
   :header-rows: 1
   :widths: 20 20 60

   * - Component
     - Technology
     - Purpose
   * - Backend
     - FastAPI 0.125+
     - REST API framework
   * - Frontend
     - Admin WebUI (HTML/CSS/JS)
     - Web interface
   * - Server
     - Uvicorn 0.38+
     - ASGI server
   * - Database
     - SQLite 3
     - Data persistence (materialized view)
   * - Ledger
     - JSONL (append-only files)
     - Authoritative audit log
   * - Axis IPC
     - pipeworks-ipc (GitHub)
     - Deterministic interaction hash (``compute_payload_hash``)
   * - Translation
     - Ollama (local LLM)
     - OOC→IC text rendering
   * - Auth
     - Passlib + Bcrypt
     - Password hashing
   * - Testing
     - pytest 8.3+
     - Test framework
   * - Linting
     - Ruff 0.8+
     - Code quality
   * - Formatting
     - Black 26.1.0
     - Code style
   * - Type Checking
     - Mypy 1.13+
     - Static analysis

Key Design Patterns
-------------------

Session Management
~~~~~~~~~~~~~~~~~~

* UUID-based sessions stored in memory and database
* Session tuples: ``(user_id: int, role: str, character_id: int | None)``
* Activity tracking updated on each API call
* Validation decorator: ``@validate_session()``

Role-Based Access Control
~~~~~~~~~~~~~~~~~~~~~~~~~~

Four roles with hierarchical permissions:

* **Player** — Basic gameplay
* **WorldBuilder** — Player + content creation
* **Admin** — WorldBuilder + user management
* **Superuser** — Admin + role management, full access

Command Pattern
~~~~~~~~~~~~~~~

* Command parsing splits into ``cmd`` and ``args``
* Router delegates to appropriate engine method
* Response model: ``CommandResponse`` with success/message
* Error handling via HTTP exceptions

Repository Pattern
~~~~~~~~~~~~~~~~~~

* App layer imports DB operations through ``mud_server.db.facade``
* SQL implementation is split across repository modules by domain
* ``database.py`` remains as a compatibility symbol surface only
* Connection and transaction ownership lives in ``connection.py`` and
  repositories
* Repository layers raise typed DB errors and API boundaries map them
  to HTTP responses

Ledger-First Authority
~~~~~~~~~~~~~~~~~~~~~~

Axis mutations follow a strict write order:

1. **Ledger write is the authoritative act** — the ``chat.mechanical_resolution``
   JSONL event is written before any DB update.
2. **DB write is materialisation** — ``apply_axis_event`` reflects the
   already-committed ledger record into ``character_axis_score``.
3. Both writes are **non-fatal** — a failure logs a WARNING/ERROR and
   the interaction continues; the resolution result is still returned.

This ordering means the ledger is always ahead of (or equal to) the DB,
never behind it.

Known Limitations
~~~~~~~~~~~~~~~~~

* SQLite concurrency limits for high-traffic deployments
* No email verification (email hashes are placeholders)
* No two-factor authentication
* Translation is synchronous (Ollama call blocks the request thread);
  async upgrade path is documented in ``translation/renderer.py``

Performance
-----------

Current Capacity
~~~~~~~~~~~~~~~~

* ~50-100 concurrent players (SQLite limitation)
* No caching (every request hits DB)
* Synchronous DB operations
* Synchronous Ollama calls (blocks while model renders)

Scaling Considerations
~~~~~~~~~~~~~~~~~~~~~~

For larger deployments:

* Migrate to PostgreSQL for concurrency
* Add Redis for session storage
* Implement caching layer
* Use async database and Ollama operations
* Add load balancing
