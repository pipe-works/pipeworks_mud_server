Architecture
============

Technical architecture and system design of PipeWorks MUD Server.

Overview
--------

PipeWorks MUD Server uses a modern three-tier architecture:

* **FastAPI backend** - RESTful API server
* **Admin WebUI** - Web-based administration dashboard
* **SQLite database** - Persistent data storage

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
    ┌──────────────────┐           ┌──────────────────┐
    │  Game Engine     │           │  SQLite Database │
    │  (Core Layer)    │◄──────────┤  (Persistence)   │
    │                  │           │                  │
    │ - World/Rooms    │           │ - Players        │
    │ - Items          │           │ - Sessions       │
    │ - Actions        │           │ - Chat Messages  │
    └──────────────────┘           └──────────────────┘

WebUI Architecture
------------------

The admin WebUI is a lightweight static frontend served by FastAPI::

    src/mud_server/web/
    ├── routes.py                 # WebUI route registration
    ├── templates/                # HTML shell
    └── static/                   # CSS + JS assets

The UI calls the FastAPI endpoints directly and enforces role checks
client-side while the API enforces permissions server-side.

System Components
-----------------

Backend (FastAPI)
~~~~~~~~~~~~~~~~~

Located in ``src/mud_server/api/``:

* ``server.py`` - App initialization, CORS, routing
* ``routes.py`` - All API endpoints
* ``models.py`` - Pydantic request/response models
* ``auth.py`` - Session management
* ``password.py`` - Bcrypt password hashing
* ``permissions.py`` - Role-based access control

Game Engine
~~~~~~~~~~~

Located in ``src/mud_server/core/``:

* ``engine.py`` - GameEngine class with all game logic
* ``world.py`` - World, Room, Item dataclasses
* ``bus.py`` - Event bus for game event handling
* ``events.py`` - Event type constants

Event Bus Architecture
~~~~~~~~~~~~~~~~~~~~~~

The event bus provides publish-subscribe infrastructure for game events.
It follows these key principles:

**Synchronous Emit**: Events are committed to the log before handlers are notified.
This ensures deterministic ordering via sequence numbers.

**Immutable Events**: Once emitted, events cannot be changed. They represent
facts about what happened (Ledger truth).

**Plugin-Ready**: The bus is designed to support future plugin systems where
plugins react to events but cannot intervene or block them.

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

Event types follow "domain:action" format in past tense (e.g., ``player:moved``,
``item:picked_up``) to emphasize they record facts, not requests.

Database Layer
~~~~~~~~~~~~~~

Located in ``src/mud_server/db/``:

* ``facade.py`` - app-facing DB API contract (used by API/core/services/CLI)
* ``database.py`` - compatibility re-export surface for DB symbols
* ``schema.py`` - schema bootstrap, indexes, and invariant triggers
* ``*_repo.py`` modules - bounded-context repositories (users, characters, sessions, chat, worlds, axis/events, admin)

Data Flow
---------

Request Flow:

1. **Client** - User interacts with the Admin WebUI
2. **API Call** - Client sends HTTP request to FastAPI
3. **Session Validation** - Server validates session and permissions
4. **Command Parsing** - Server parses command and arguments
5. **Game Logic** - Engine executes command
6. **Database** - Engine reads/writes to SQLite
7. **Response** - Server returns result to client
8. **Display** - Client updates interface

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
     - Data persistence
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
     - Black 24.10+
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

* **Player** - Basic gameplay
* **WorldBuilder** - Player + content creation
* **Admin** - WorldBuilder + user management
* **Superuser** - Admin + role management, full access

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
* Connection and transaction ownership lives in ``connection.py`` and repositories

Database Schema
---------------

Users Table
~~~~~~~~~~~

* ``id`` (INTEGER, PRIMARY KEY)
* ``username`` (TEXT, UNIQUE)
* ``password_hash`` (TEXT)
* ``email_hash`` (TEXT, UNIQUE, NULLABLE) - placeholder for hashed emails
* ``role`` (TEXT) - Player, WorldBuilder, Admin, Superuser
* ``is_active`` (INTEGER)
* ``is_guest`` (INTEGER)
* ``guest_expires_at`` (TIMESTAMP, NULLABLE)
* ``account_origin`` (TEXT) - e.g. legacy, visitor, admin
* ``created_at`` (TIMESTAMP)
* ``last_login`` (TIMESTAMP)
* ``tombstoned_at`` (TIMESTAMP, NULLABLE) - set for deactivated users; guest accounts are deleted on expiry

Characters Table
~~~~~~~~~~~~~~~~

* ``id`` (INTEGER, PRIMARY KEY)
* ``user_id`` (INTEGER, NULLABLE)
* ``name`` (TEXT, NOT NULL)
* ``world_id`` (TEXT, NOT NULL)
* ``UNIQUE(world_id, name)`` - character names are world-scoped
* ``inventory`` (TEXT) - JSON array of item IDs
* ``is_guest_created`` (INTEGER)
* ``created_at`` (TIMESTAMP)
* ``updated_at`` (TIMESTAMP)

Character Locations Table
~~~~~~~~~~~~~~~~~~~~~~~~~

* ``character_id`` (INTEGER, PRIMARY KEY)
* ``room_id`` (TEXT)
* ``updated_at`` (TIMESTAMP)

Sessions Table
~~~~~~~~~~~~~~

* ``session_id`` (TEXT, UNIQUE) - UUID
* ``user_id`` (INTEGER)
* ``character_id`` (INTEGER, NULLABLE)
* ``world_id`` (TEXT, NULLABLE) - required when ``character_id`` is set
* ``created_at`` (TIMESTAMP)
* ``last_activity`` (TIMESTAMP)
* ``expires_at`` (TIMESTAMP, NULLABLE)
* ``client_type`` (TEXT)

Chat Messages Table
~~~~~~~~~~~~~~~~~~~

* ``id`` (INTEGER, PRIMARY KEY)
* ``character_id`` (INTEGER, NULLABLE)
* ``user_id`` (INTEGER, NULLABLE)
* ``message`` (TEXT)
* ``world_id`` (TEXT)
* ``room`` (TEXT)
* ``recipient_character_id`` (INTEGER, NULLABLE)
* ``timestamp`` (TIMESTAMP)

Security Considerations
-----------------------

Authentication
~~~~~~~~~~~~~~

* **Password hashing**: Bcrypt via passlib (intentionally slow, ~100ms per hash)
* **Password policy**: NIST SP 800-63B aligned with comprehensive validation
* **Session IDs**: UUID v4 (cryptographically random, hard to guess)
* **Session validation**: Every API call validates session and extracts role
* **Role-based access**: Four-tier permission system (Player < WorldBuilder < Admin < Superuser)

Password Policy
~~~~~~~~~~~~~~~

The STANDARD password policy enforces:

* **Minimum 12 characters** (NIST recommended)
* **Common password rejection** (150+ known weak passwords blocked)
* **Leet-speak detection** (p@ssw0rd detected as "password" variant)
* **Sequential character detection** (abc, 123, xyz patterns blocked)
* **Repeated character detection** (aaa, 1111 patterns blocked)

Three policy levels available: BASIC (8 chars), STANDARD (12 chars), STRICT (16 chars + complexity).

See :doc:`security` for complete details.

Known Limitations
~~~~~~~~~~~~~~~~~

* SQLite concurrency limits for high-traffic deployments
* No email verification (email hashes are placeholders for future use)
* No two-factor authentication

Performance
-----------

Current Capacity
~~~~~~~~~~~~~~~~

* ~50-100 concurrent players (SQLite limitation)
* No caching (every request hits DB)
* Synchronous DB operations
* In-memory sessions (fast but not persistent)

Scaling Considerations
~~~~~~~~~~~~~~~~~~~~~~

For larger deployments:

* Migrate to PostgreSQL for concurrency
* Add Redis for session storage
* Implement caching layer
* Use async database operations
* Add load balancing
