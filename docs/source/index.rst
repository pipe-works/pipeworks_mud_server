PipeWorks MUD Server
====================

**A deterministic, procedural multiplayer text game engine for building accountable interactive fiction worlds.**

A modern, extensible MUD (Multi-User Dungeon) server framework built with Python, FastAPI, and a custom WebUI.
Provides a solid foundation for creating text-based multiplayer games with deterministic mechanics,
JSON-driven world data, and clean architecture.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   getting_started
   architecture
   database
   axis_state
   ledger
   translation_layer
   admin_axis_inspector
   security
   admin_web_ui_mtls
   play_web_ui
   extending
   examples

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api_reference
   Changelog <changelog>

.. toctree::
   :maxdepth: 3
   :caption: API Documentation

   autoapi/index

Key Features
------------

* **Deterministic**: Same seed always produces same game state
* **Ledger-driven**: Every mechanical interaction is written to an
  append-only JSONL audit log before the database is updated
* **Axis resolution engine**: Grammar-driven mechanical resolution of
  character state mutations across any number of axes
* **OOC→IC translation**: Optional LLM-rendered in-character dialogue
  via Ollama, linked to mechanical resolution via ``ipc_hash``
* **Data-driven**: JSON world definitions, YAML grammars, no code changes
  needed to add worlds or tune resolver parameters
* **Modern stack**: FastAPI + WebUI + SQLite
* **Secure**: CLI-based superuser management, bcrypt passwords
* **Extensible**: Modular architecture, clean API
* **Well-tested**: Comprehensive test suite with >80% coverage

Quick Start
-----------

Installation:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/pipe-works/pipeworks_mud_server.git
   cd pipeworks_mud_server

   # Create and activate virtual environment
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

   # Install the package
   pip install -e .

   # Initialize database and create superuser
   mud-server init-db
   mud-server create-superuser

``init-db`` bootstraps the schema and can also create the initial superuser
if ``MUD_ADMIN_USER`` and ``MUD_ADMIN_PASSWORD`` are set and no users exist.

Running the Server:

.. code-block:: bash

   mud-server run

   # The server will start on:
   # - API: http://localhost:8000
   # - Admin Web UI: http://localhost:8000/admin

Superuser Setup
~~~~~~~~~~~~~~~

The server uses secure credential management with strong password requirements.

**Password Requirements (STANDARD policy):**

* Minimum 12 characters
* Cannot be a commonly used password
* No sequential characters (abc, 123)
* No excessive repeated characters (aaa)

**Option 1: Interactive** (recommended for local development):

.. code-block:: bash

   mud-server create-superuser
   # Follow prompts for username and password
   # Password requirements will be displayed

**Option 2: Environment variables** (for CI/deployment):

.. code-block:: bash

   export MUD_ADMIN_USER=myadmin
   export MUD_ADMIN_PASSWORD="MySecure#Pass2024"  # Must meet policy requirements
   mud-server create-superuser

Use Cases
---------

PipeWorks MUD Server is suitable for:

* **Fantasy MUDs** - Traditional dungeon exploration
* **Sci-Fi Adventures** - Space stations and starships
* **Educational Games** - Learning through interaction
* **Any text-based multiplayer world** you can imagine

Design Philosophy
-----------------

**Programmatic = Authoritative**

* All game logic, axis resolution, and ledger writes are deterministic
  and code-driven
* Game mechanics are reproducible and testable from seed
* No LLM involvement in authoritative systems (state, logic, resolution,
  ledger records)

**LLM = Non-Authoritative**

* The translation layer renders flavour text only — IC dialogue is
  cosmetic and never changes game state
* Failure in the translation layer is always non-fatal
* Deterministic rendering (``ipc_hash``-seeded Ollama) is optional

**Ledger is Truth**

* Immutable JSONL ledger records are written before DB updates
* The database is a materialised view that can be reconstructed from
  the ledger
* Every interaction is traceable via ``ipc_hash`` linkage between the
  mechanical resolution event and the translation event

**Extensibility First**

* World data is JSON/YAML-driven (swap worlds or tune resolvers without
  code changes)
* Commands are extensible (add new actions without server rewrites)
* Modular architecture supports plugins and custom mechanics

Available Commands
------------------

**Movement:**

* ``north`` / ``n``, ``south`` / ``s``, ``east`` / ``e``, ``west`` / ``w``
* ``up`` / ``u``, ``down`` / ``d``

**Observation:**

* ``look`` / ``l`` - Observe current surroundings
* ``inventory`` / ``inv`` / ``i`` - Check inventory

**Items:**

* ``pickup <item>`` / ``get <item>`` - Pick up an item
* ``drop <item>`` - Drop an item

**Communication:**

* ``say <message>`` - Speak to others in same room
* ``yell <message>`` - Shout to nearby areas
* ``whisper <username> <message>`` - Private message

**Utility:**

* ``who`` - See all players online
* ``help`` - Show help information

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
