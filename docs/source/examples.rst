Examples
========

Demo applications showcasing the MUD server's REST API.

ASCII Movement Demo
-------------------

A minimal browser-based client demonstrating keyboard-controlled movement
through the game world. Features a retro terminal aesthetic with green-on-black
styling.

The demo displays an ASCII map like this::

                      +----------+
                      |  FOREST  |
                      +----+-----+
                           |
    +--------+    |    +----------+
    |  LAKE  |----+--------+----| MOUNTAIN |
    +--------+    | SPAWN  |    +----------+
                  +---+----+
                      |
                  +---+----+
                  | DESERT |
                  +--------+

Features
~~~~~~~~

* **ASCII Map**: Visual representation of 5 rooms in a cross pattern
* **Keyboard Controls**: WASD or Arrow keys for movement
* **Visual Feedback**: Current room highlighted in yellow, movement keys light up
* **Room Descriptions**: Updates dynamically as you move
* **Login/Logout**: Full authentication flow via REST API

World Layout
~~~~~~~~~~~~

The demo uses the default world with spawn at the center::

                  [FOREST]
                     |
        [LAKE] -- [SPAWN] -- [MOUNTAIN]
                     |
                  [DESERT]

Each room has one exit back to spawn, and spawn has exits to all four
cardinal directions.

Running the Demo
~~~~~~~~~~~~~~~~

**Step 1: Start the MUD server**

.. code-block:: bash

   mud-server run

**Step 2: Configure CORS** (if needed)

The demo requires its origin to be allowed by the server. Add ``http://localhost:8080``
to your ``config/server.ini``:

.. code-block:: ini

   [security]
   cors_origins = http://localhost:8000, http://localhost:8080

**Step 3: Serve the demo**

.. code-block:: bash

   # From the project root
   python -m http.server 8080 -d examples

**Step 4: Open in browser**

Navigate to http://localhost:8080/ascii_demo.html

**Step 5: Login and play**

Enter your username and password, then use WASD or arrow keys to move!

API Endpoints Used
~~~~~~~~~~~~~~~~~~

The demo uses these REST API endpoints:

.. list-table::
   :header-rows: 1
   :widths: 20 20 60

   * - Method
     - Endpoint
     - Purpose
   * - POST
     - ``/login``
     - Authenticate and receive session ID
   * - POST
     - ``/logout``
     - End the session
   * - GET
     - ``/status/{session_id}``
     - Get current room, inventory, active players
   * - POST
     - ``/command``
     - Send movement commands (north, south, east, west)

Request/Response Examples
~~~~~~~~~~~~~~~~~~~~~~~~~

**Login:**

.. code-block:: javascript

   // Request
   POST /login
   { "username": "player1", "password": "secret123" }

   // Response
   { "success": true, "session_id": "uuid-here", "message": "Welcome..." }

**Movement:**

.. code-block:: javascript

   // Request
   POST /command
   { "session_id": "uuid-here", "command": "north" }

   // Response
   { "success": true, "message": "You move north.\n=== Enchanted Forest ===" }

**Status:**

.. code-block:: javascript

   // Request
   GET /status/uuid-here

   // Response
   {
       "current_room": "forest",
       "inventory": "Your inventory is empty.",
       "active_players": ["player1"]
   }

Code Structure
~~~~~~~~~~~~~~

The demo is a single self-contained HTML file with embedded CSS and JavaScript:

.. code-block:: text

   examples/ascii_demo.html
   ├── <style>           - Retro terminal CSS styling
   ├── Login Section     - Username/password form
   ├── Game Section      - Map, description, controls
   └── <script>          - API client and game logic
       ├── State         - sessionId, currentRoom, username
       ├── ROOMS         - Static room data (name, description)
       ├── apiCall()     - Generic fetch wrapper
       ├── login()       - POST /login handler
       ├── logout()      - POST /logout handler
       ├── updateStatus()- GET /status handler
       ├── move()        - POST /command handler
       ├── renderMap()   - ASCII map generation
       └── keydown       - Keyboard event listener

Extending the Demo
~~~~~~~~~~~~~~~~~~

The demo is intentionally minimal. Here are some ideas for extending it:

* **Add inventory display**: Show items from the ``/status`` response
* **Add chat**: Implement ``say`` command and poll for room messages
* **Add player list**: Show other players from ``active_players``
* **Add sound effects**: Play sounds on movement success/failure
* **Mobile support**: Add touch controls for mobile devices
* **WebSocket upgrade**: Replace polling with real-time updates

Event Bus Integration
~~~~~~~~~~~~~~~~~~~~~

While the demo client doesn't interact with the event bus directly, the server
emits events for every movement command. This enables future plugin systems
to react to player actions.

When you move in the demo, the server's ``GameEngine.move()`` method emits events:

**Successful Movement:**

.. code-block:: python

   # Server-side (engine.py)
   bus.emit(Events.PLAYER_MOVED, {
       "username": "player1",
       "from_room": "spawn",
       "to_room": "forest",
       "direction": "north"
   })

**Failed Movement** (no exit in that direction):

.. code-block:: python

   bus.emit(Events.PLAYER_MOVE_FAILED, {
       "username": "player1",
       "room": "spawn",
       "direction": "west",
       "reason": "No exit west"
   })

These events are recorded in the bus's event log with:

* **Sequence number**: Monotonic counter for deterministic ordering
* **Timestamp**: When the event occurred
* **Source**: Which system emitted it (e.g., "engine")

**Why This Matters:**

Future plugins can subscribe to these events to add behavior:

.. code-block:: python

   from mud_server.core.bus import bus
   from mud_server.core.events import Events

   # Weather plugin reacting to movement
   def on_player_moved(event):
       if event.detail["to_room"] == "mountain":
           # Trigger weather effects
           pass

   bus.on(Events.PLAYER_MOVED, on_player_moved)

The event bus follows the principle: **"Plugins react, don't intervene."**
Events record facts about what happened (Ledger truth), and plugins respond
to those facts without blocking or modifying the original action.

See :doc:`architecture` for more details on the event bus design.

CORS Troubleshooting
~~~~~~~~~~~~~~~~~~~~

If you see "Connection failed" or CORS errors in the browser console:

1. **Check the server output** - Look for ``OPTIONS /login 400 Bad Request``
2. **Verify cors_origins** - Ensure your origin is in the list
3. **Restart the server** - Config changes require a restart
4. **Check the origin** - ``file://`` origins show as ``null``

For development, serve the file via HTTP rather than opening directly:

.. code-block:: bash

   # Good - origin is http://localhost:8080
   python -m http.server 8080 -d examples

   # Problematic - origin is null
   open examples/ascii_demo.html
