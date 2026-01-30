PipeWorks MUD Server
====================

**A deterministic, procedural multiplayer text game engine for building accountable interactive fiction worlds.**

A modern, extensible MUD (Multi-User Dungeon) server framework built with Python, FastAPI, and Gradio.
Provides a solid foundation for creating text-based multiplayer games with deterministic mechanics,
JSON-driven world data, and clean architecture.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   getting_started
   architecture
   extending
   api_reference

.. toctree::
   :maxdepth: 3
   :caption: API Reference

   autoapi/index

Overview
--------

PipeWorks MUD Server is a generic framework suitable for any theme:

* **Fantasy MUDs** - Traditional dungeon exploration
* **Sci-Fi Adventures** - Space stations and starships
* **Educational Games** - Learning through interaction
* **Any text-based multiplayer world** you can imagine

Key Features
------------

**Core Capabilities:**

* FastAPI REST API backend (port 8000)
* Gradio web interface (port 7860)
* SQLite database for persistence
* Authentication and session management
* Role-based access control (Player/WorldBuilder/Admin/Superuser)
* Room navigation with directional movement
* Inventory system (pickup/drop items)
* Multi-channel chat (say/yell/whisper)
* JSON-driven world definition
* Ollama AI integration (admin/superuser only)
* 100% test coverage on core client modules

Design Philosophy
-----------------

**Programmatic Authority**

* All game logic and state is deterministic and code-driven
* Game mechanics are reproducible and testable
* No LLM involvement in authoritative systems (state, logic, resolution)

**Extensibility First**

* World data is JSON-driven (swap worlds without code changes)
* Commands are extensible (add new actions without server rewrites)
* Modular architecture supports plugins and custom mechanics

**Clean Separation**

* **Client Layer** (Gradio) - UI and user interaction
* **Server Layer** (FastAPI) - HTTP API and routing
* **Game Layer** (Engine + World) - Core mechanics and state
* **Persistence Layer** (SQLite) - Data storage

Quick Start
-----------

Installation::

    # Clone the repository
    git clone https://github.com/pipe-works/pipeworks_mud_server.git
    cd pipeworks_mud_server

    # Create and activate virtual environment
    python3 -m venv venv
    source venv/bin/activate

    # Install dependencies
    pip install -r requirements.txt

    # Initialize database
    PYTHONPATH=src python3 -m mud_server.db.database

Running the Server::

    ./run.sh

    # The server will start on:
    # - API: http://localhost:8000
    # - Web UI: http://localhost:7860

Default Credentials
~~~~~~~~~~~~~~~~~~~

⚠️ **Change immediately!**

* Username: ``admin``
* Password: ``admin123``

Available Commands
------------------

**Movement:**

* ``north`` / ``n`` - Move north
* ``south`` / ``s`` - Move south
* ``east`` / ``e`` - Move east
* ``west`` / ``w`` - Move west
* ``up`` / ``u`` - Move upward
* ``down`` / ``d`` - Move downward

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
