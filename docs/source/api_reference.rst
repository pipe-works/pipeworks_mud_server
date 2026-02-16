API Reference
=============

Complete API documentation for PipeWorks MUD Server.

Overview
--------

PipeWorks MUD Server provides:

* **REST API** - FastAPI backend on port 8000
* **Python Package** - ``mud_server`` with core game logic
* **Pydantic Models** - Type-safe request/response schemas

Interactive API Docs
--------------------

When the server is running, visit:

* **Swagger UI**: http://localhost:8000/docs
* **ReDoc**: http://localhost:8000/redoc

These provide interactive API exploration with:

* All endpoints listed
* Request/response schemas
* Try-it-out functionality
* Authentication testing

API Endpoints
-------------

Authentication
~~~~~~~~~~~~~~

* ``POST /register`` - Register temporary visitor account (account only; no character)
* ``POST /register-guest`` - Register guest account with server-generated username + character
* ``POST /login`` - Log in and create account session (character selection is separate)
* ``POST /logout`` - Log out and destroy session
* ``POST /change-password`` - Change password (password must meet STANDARD policy)
* ``GET /characters`` - List characters for session
* ``POST /characters/create`` - Self-provision generated character for selected world
* ``POST /characters/select`` - Select active character for session

Register Guest Examples
~~~~~~~~~~~~~~~~~~~~~~~

**POST /register** (client-supplied username)

.. code-block:: bash

    curl -s -X POST http://localhost:8000/register \
      -H "Content-Type: application/json" \
      -d '{
        "username": "guest_demo",
        "password": "SecurePass#1234",
        "password_confirm": "SecurePass#1234"
      }'

**Response** (200):

.. code-block:: json

    {
      "success": true,
      "message": "Temporary account created successfully! You can now login as guest_demo. Character creation is a separate step."
    }

**POST /register-guest** (server-generated username)

.. code-block:: bash

    curl -s -X POST http://localhost:8000/register-guest \
      -H "Content-Type: application/json" \
      -d '{
        "password": "SecurePass#1234",
        "password_confirm": "SecurePass#1234",
        "character_name": "Guest Wanderer"
      }'

**Response** (200):

.. code-block:: json

    {
      "success": true,
      "message": "Temporary guest account created successfully! You can now login as guest_00421.",
      "username": "guest_00421",
      "character_id": 42,
      "character_name": "Guest Wanderer",
      "world_id": "pipeworks_web",
      "entity_state": {
        "seed": 0,
        "world_id": "pipeworks_web",
        "policy_hash": "420079743c68fba68936162bb3f46f7cbddecd9d3ff704a52c702cd6c0b6aec4",
        "axes": {
          "age": {"label": "old", "score": 0.5},
          "demeanor": {"label": "resentful", "score": 0.5},
          "health": {"label": "weary", "score": 0.5}
        }
      },
      "entity_state_error": null
    }

Notes:

* ``entity_state`` is sourced from the freshly seeded in-database character
  snapshot when available.
* If the local snapshot is unavailable, the server may attempt external
  integration fallback (when configured).
* If state generation is unavailable from all sources, registration still
  succeeds and ``entity_state`` is ``null`` with ``entity_state_error``
  populated.

Character Provisioning (Account Session)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``POST /characters/create`` provisions one generated-name character for the
authenticated account in the requested world.

**Request**

.. code-block:: json

    {
      "session_id": "uuid-session-id",
      "world_id": "pipeworks_web"
    }

**Response** (200)

.. code-block:: json

    {
      "success": true,
      "message": "Character 'Fimenscu Tarharsh' created for 'aggro'.",
      "character_id": 314,
      "character_name": "Fimenscu Tarharsh",
      "world_id": "pipeworks_web",
      "seed": 187392,
      "entity_state": null,
      "entity_state_error": null
    }

Policy behavior:

* Requires a valid **account session** (no implicit world entry).
* Honors global and world policy from ``config/server.ini``:
  * ``[character_creation] player_self_create_enabled``
  * ``[world_policy.<world_id>] creation_mode``
  * ``[world_policy.<world_id>] slot_limit_per_account``
* Returns ``403`` for invite-locked worlds without access grants.
* Returns ``409`` when world slot capacity is exhausted.
* Returns ``502`` when name generation integration is unavailable.

World List Metadata
~~~~~~~~~~~~~~~~~~~

``/login`` returns ``available_worlds`` rows decorated for account dashboards:

* ``can_access`` - whether the account can enter/select the world now
* ``can_create`` - whether character creation is currently allowed
* ``access_mode`` - ``open`` or ``invite``
* ``naming_mode`` - ``generated`` or ``manual``
* ``slot_limit_per_account`` / ``current_character_count`` - world slot usage
* ``is_locked`` - convenience flag for invite-only preview rows

Game Actions
~~~~~~~~~~~~

* ``POST /command`` - Execute game command
* ``GET /status/{session_id}`` - Get character status
* ``GET /chat/{session_id}`` - Get chat messages

Admin
~~~~~

* ``GET /admin/database/players`` - List users (Admin+)
  - Includes ``is_online_account`` and ``is_online_in_world`` to distinguish
    dashboard logins from active in-world sessions.
  - Returns non-tombstoned accounts for the Active Users card.
* ``GET /admin/database/connections`` - Active connections (Admin+)
* ``GET /admin/database/player-locations`` - Character locations (Admin+)
* ``GET /admin/database/tables`` - Database table metadata (Admin+)
* ``GET /admin/database/table/{table_name}`` - Table rows (Admin+)
* ``GET /admin/database/sessions`` - Sessions (Admin+)
* ``GET /admin/database/chat-messages`` - Chat logs (Admin+)
* ``GET /admin/characters/{character_id}/axis-state`` - Axis scores + snapshots (Admin+)
* ``GET /admin/characters/{character_id}/axis-events`` - Axis event history (Admin+)
* ``POST /admin/user/create`` - Create user account (Admin/Superuser)
* ``POST /admin/user/create-character`` - Provision generated character for account (Admin+)
* ``POST /admin/user/manage`` - Manage user (change role, ban, delete, password)
* ``POST /admin/session/kick`` - Kick session (Admin+)
* ``POST /admin/server/stop`` - Stop server (Admin+)
* ``POST /admin/ollama/command`` - Run Ollama command (Admin+)
* ``POST /admin/ollama/clear-context`` - Clear Ollama context (Admin+)

Health
~~~~~~

* ``GET /health`` - Server health check

Authentication
--------------

All protected endpoints require a ``session_id``. Depending on the endpoint,
it is provided in the request body (POST), query string (GET), or URL path
(``/status/{session_id}``, ``/chat/{session_id}``).

Password Requirements
~~~~~~~~~~~~~~~~~~~~~

Registration and password changes enforce the **STANDARD** password policy:

* **Minimum 12 characters**
* **Not a commonly used password** (150+ blocked)
* **No sequential characters** (abc, 123, xyz)
* **No excessive repeated characters** (aaa, 1111)

**Example Error Response** (password too short):

.. code-block:: json

    {
        "detail": "Password must be at least 12 characters long (currently 8)"
    }

**Example Error Response** (common password):

.. code-block:: json

    {
        "detail": "This password is too common and easily guessed. Please choose a more unique password."
    }

See :doc:`security` for complete password policy documentation.

Guest Accounts
~~~~~~~~~~~~~~

Guest registrations are intended for testing/dev. Accounts created via
``POST /register`` and ``POST /register-guest`` are marked as temporary and
automatically purged after 24 hours. Admin- or superuser-created accounts are
not affected.

Session Creation
~~~~~~~~~~~~~~~~

1. **Register**: ``POST /register`` with username and password (must meet policy)
2. **Login**: ``POST /login`` with credentials and receive account session
3. **Create Character**: ``POST /characters/create`` (or admin/API flow, or ``/register-guest``)
4. **Select**: ``POST /characters/select`` with chosen character ID
5. **Use**: Include session_id in all subsequent requests

Session Format
~~~~~~~~~~~~~~

Sessions are stored in the database and identified by opaque session IDs.
The server validates the session ID, enforces expiration, and resolves
the user role on each request.

Role-Based Access
-----------------

Four user roles with hierarchical permissions:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Role
     - Permissions
   * - **Player**
     - Play game, chat, manage own inventory
   * - **WorldBuilder**
     - Player + create/edit rooms and items
   * - **Admin**
     - WorldBuilder + create users, ban users, view logs, stop server
   * - **Superuser**
     - Admin + role management, full system access

Error Handling
--------------

HTTP Status Codes
~~~~~~~~~~~~~~~~~

* ``200 OK`` - Request succeeded
* ``400 Bad Request`` - Invalid request data
* ``401 Unauthorized`` - Invalid or missing session
* ``403 Forbidden`` - Insufficient permissions
* ``404 Not Found`` - Resource not found
* ``500 Internal Server Error`` - Server error

Error Response Format
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

    {
        "detail": "Error message describing what went wrong"
    }

CORS Configuration
------------------

CORS origins are configured in ``config/server.ini`` or via environment variable.

**Config File** (config/server.ini):

.. code-block:: ini

    [security]
    cors_origins = https://yourdomain.com, https://api.yourdomain.com

**Environment Variable** (overrides config file):

.. code-block:: bash

    export MUD_CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com

Development default allows localhost origins only.

See ``config/server.example.ini`` for all available security settings.

WebSocket Support (Future)
---------------------------

Planned for real-time features:

* Live chat updates
* Player movement notifications
* Room event broadcasting

Currently uses HTTP polling.

Python API Documentation
------------------------

Full API documentation for all Python modules is available in the
:doc:`autoapi/index` section, automatically generated from code docstrings.
