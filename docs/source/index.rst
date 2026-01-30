PipeWorks MUD Server
====================

**A deterministic, procedural multiplayer text game engine for building accountable interactive fiction worlds.**

A modern, extensible MUD (Multi-User Dungeon) server framework built with Python, FastAPI, and Gradio.
Provides a solid foundation for creating text-based multiplayer games with deterministic mechanics,
JSON-driven world data, and clean architecture.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   getting_started
   architecture
   extending

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
* **Data-driven**: JSON world definitions, no code changes needed
* **Modern stack**: FastAPI + Gradio + SQLite
* **Secure**: CLI-based superuser management, bcrypt passwords
* **Extensible**: Modular architecture, clean API
* **Well-tested**: Comprehensive test suite with coverage

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

Running the Server:

.. code-block:: bash

   mud-server run

   # The server will start on:
   # - API: http://localhost:8000
   # - Web UI: http://localhost:7860

Superuser Setup
~~~~~~~~~~~~~~~

The server uses secure credential management - no default passwords.

**Option 1: Interactive** (recommended for local development):

.. code-block:: bash

   mud-server create-superuser
   # Follow prompts for username and password

**Option 2: Environment variables** (for CI/deployment):

.. code-block:: bash

   export MUD_ADMIN_USER=myadmin
   export MUD_ADMIN_PASSWORD=mysecurepassword123
   mud-server init-db

Use Cases
---------

PipeWorks MUD Server is suitable for:

* **Fantasy MUDs** - Traditional dungeon exploration
* **Sci-Fi Adventures** - Space stations and starships
* **Educational Games** - Learning through interaction
* **Any text-based multiplayer world** you can imagine

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
