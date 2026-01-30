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

    # Install dependencies
    pip install -r requirements.txt

Initialize Database
~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    PYTHONPATH=src python3 -m mud_server.db.database

This creates the SQLite database with required tables.

Running the Server
------------------

Start Both Services
~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    ./run.sh

This starts:

* **API Server**: http://localhost:8000
* **Web UI**: http://localhost:7860

Press ``Ctrl+C`` to stop both services.

First Login
-----------

Default Superuser Credentials:

* **Username**: ``admin``
* **Password**: ``admin123``

⚠️ **IMPORTANT**: Change this immediately after first login!

1. Login with default credentials
2. Navigate to user management interface
3. Set a new secure password

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
    pip install -r requirements-dev.txt

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

    PYTHONPATH=src python3 src/mud_server/api/server.py

Gradio Client Only
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    PYTHONPATH=src python3 src/mud_server/client/app.py

Requires API server to be running.

Environment Variables
---------------------

Optional configuration:

.. code-block:: bash

    export MUD_HOST="0.0.0.0"          # Bind address
    export MUD_PORT=8000                # API port
    export MUD_SERVER_URL="http://localhost:8000"  # Client API endpoint

Next Steps
----------

* Read the :doc:`architecture` to understand the system design
* Learn how to :doc:`extending` the server with new features
* Explore the :doc:`api_reference` for API documentation
