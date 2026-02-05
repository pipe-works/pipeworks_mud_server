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

* ``POST /register`` - Register new account (password must meet STANDARD policy)
* ``POST /login`` - Log in and create session
* ``POST /logout`` - Log out and destroy session
* ``POST /change-password`` - Change password (password must meet STANDARD policy)

Game Actions
~~~~~~~~~~~~

* ``POST /command`` - Execute game command
* ``GET /status`` - Get player status
* ``GET /chat`` - Get chat messages

Admin
~~~~~

* ``GET /admin/users`` - List all users (Admin+)
* ``PUT /admin/users/{username}/role`` - Change user role (Superuser)
* ``PUT /admin/users/{username}/password`` - Reset password (Superuser)
* ``PUT /admin/users/{username}/status`` - Activate/deactivate account (Admin+)

Health
~~~~~~

* ``GET /health`` - Server health check

Authentication
--------------

All protected endpoints require a ``session_id`` in the request body.

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

Session Creation
~~~~~~~~~~~~~~~~

1. **Register**: ``POST /register`` with username and password (must meet policy)
2. **Login**: ``POST /login`` with credentials
3. **Receive**: Session ID returned in response
4. **Use**: Include session_id in all subsequent requests

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
     - WorldBuilder + user management (limited)
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
