Getting Started
===============

This guide will help you get PipeWorks MUD Server up and running.

Prerequisites
-------------

* Python 3.12 or 3.13
* pip (Python package manager)
* Git

Installation
------------

Clone and Setup
~~~~~~~~~~~~~~~

.. code-block:: bash

    # Clone the repository
    git clone https://github.com/pipe-works/pipeworks_mud_server.git
    cd pipeworks_mud_server

    # Create and activate virtual environment
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate

    # Install the package
    pip install -e .

Initialize Database
~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    # Initialize the database schema
    mud-server init-db

This creates the SQLite database with required tables. If ``MUD_ADMIN_USER``
and ``MUD_ADMIN_PASSWORD`` are set and no users exist, ``init-db`` also
bootstraps the superuser.

Create Superuser
~~~~~~~~~~~~~~~~

The server requires a superuser account for administration. Passwords must meet
the **STANDARD security policy** requirements:

* **Minimum 12 characters** (NIST SP 800-63B recommended)
* **Not a commonly used password** (checked against 150+ known weak passwords)
* **No sequential characters** (abc, 123, xyz)
* **No excessive repeated characters** (aaa, 1111)

Choose one method:

**Interactive mode** (recommended for local development):

.. code-block:: bash

    mud-server create-superuser
    # Password requirements will be displayed
    # Real-time feedback on password strength

**Environment variables** (for CI/deployment):

.. code-block:: bash

    export MUD_ADMIN_USER=myadmin
    export MUD_ADMIN_PASSWORD="MySecure#Pass2024"  # Must meet policy requirements
    mud-server create-superuser

.. note::

    The password policy ensures strong passwords are used from the start.
    See :doc:`security` for complete details on the password policy.

Running the Server
------------------

Start the Server
~~~~~~~~~~~~~~~~

.. code-block:: bash

    mud-server run

This starts:

* **API Server**: http://localhost:8000
* **Web UI**: http://localhost:7860

Press ``Ctrl+C`` to stop the server.

First Login
-----------

1. Open the web UI at http://localhost:7860
2. Login with the superuser credentials you created
3. Explore the interface and start building your world

Creating Your First World
--------------------------

The default world is defined in ``data/world_data.json``:

.. code-block:: json

    {
      "rooms": {
        "spawn": {
          "id": "spawn",
          "name": "Spawn Zone",
          "description": "A central gathering point.",
          "exits": {
            "north": "forest",
            "south": "desert"
          },
          "items": ["torch"]
        }
      },
      "items": {
        "torch": {
          "id": "torch",
          "name": "torch",
          "description": "A burning torch providing light."
        }
      }
    }

To create your own world:

1. Edit ``data/world_data.json``
2. Add rooms with connections
3. Add items to rooms
4. Restart the server

No code changes required!

Development Setup
-----------------

For development work:

.. code-block:: bash

    # Install development dependencies
    pip install -e ".[dev]"

    # Run tests
    pytest -v

    # Run tests with coverage
    pytest --cov=mud_server --cov-report=html

    # Lint code
    ruff check src/ tests/

    # Format code
    black src/ tests/

    # Type checking
    mypy src/ --ignore-missing-imports

Running Components Separately
------------------------------

API Server Only
~~~~~~~~~~~~~~~

.. code-block:: bash

    python -m mud_server.api.server

Gradio Client Only
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    python -m mud_server.admin_gradio.app

Requires API server to be running.

Admin TUI (Terminal Interface)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For SSH/tmux workflows or terminal-based administration:

.. code-block:: bash

    # Install TUI dependencies
    pip install -e ".[admin-tui]"

    # Run the terminal UI (connects to localhost:8000 by default)
    pipeworks-admin-tui

    # Connect to a remote server
    pipeworks-admin-tui --server http://remote-server:8000

The TUI provides:

* Login screen with username/password authentication
* Dashboard with server status and quick actions
* Create user workflow (role selection + password confirmation)
* Keyboard shortcuts for common operations

Requires API server to be running.

Guest Registration
------------------

The public ``/register`` endpoint creates **temporary guest** accounts for
testing/dev. Each guest account gets a single character and is automatically
purged after 24 hours.

Environment Variables
---------------------

Optional configuration:

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Variable
     - Default
     - Description
   * - ``MUD_HOST``
     - ``0.0.0.0``
     - Server bind address
   * - ``MUD_PORT``
     - ``8000``
     - API server port
   * - ``MUD_SERVER_URL``
     - ``http://localhost:8000``
     - Client API endpoint
   * - ``MUD_ADMIN_USER``
     - (none)
     - Superuser username for create-superuser or init-db bootstrap
   * - ``MUD_ADMIN_PASSWORD``
     - (none)
     - Superuser password for create-superuser or init-db bootstrap
   * - ``MUD_REQUEST_TIMEOUT``
     - ``30``
     - HTTP request timeout (seconds) for TUI

CLI Reference
-------------

The ``mud-server`` CLI provides these commands:

.. code-block:: text

    mud-server init-db           Initialize database schema
    mud-server create-superuser  Create a superuser account
    mud-server run               Start the server

The ``pipeworks-admin-tui`` CLI (requires ``[admin-tui]`` extra):

.. code-block:: text

    pipeworks-admin-tui                    Connect to localhost:8000
    pipeworks-admin-tui -s URL             Connect to specified server
    pipeworks-admin-tui -t SECONDS         Set request timeout

For help on any command:

.. code-block:: bash

    mud-server --help
    mud-server init-db --help
    pipeworks-admin-tui --help

Next Steps
----------

* Read the :doc:`architecture` to understand the system design
* Learn how to :doc:`extending` the server with new features
* Explore the :doc:`api_reference` for API documentation
   * - ``MUD_CHAR_DEFAULT_SLOTS``
     - ``2``
     - Default character slots per account
   * - ``MUD_CHAR_MAX_SLOTS``
     - ``10``
     - Maximum character slots per account
