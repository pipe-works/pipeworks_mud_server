Extending the Server
====================

Guide for adding new features and extending PipeWorks MUD Server.

Adding New Commands
-------------------

To add a new command (e.g., ``examine``):

1. Add Method to GameEngine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In ``src/mud_server/core/engine.py``:

.. code-block:: python

    def examine(self, username: str, target: str) -> str:
        """Examine an item or object in detail."""
        player = self.db.get_player(username)
        if not player:
            return "You don't exist."

        # Check inventory
        if target in player["inventory"]:
            item = self.world.get_item(target)
            return f"You examine the {item.name}: {item.description}"

        # Check room
        room = self.world.get_room(player["current_room"])
        if target in room.items:
            item = self.world.get_item(target)
            return f"You examine the {item.name}: {item.description}"

        return f"You don't see '{target}' here."

2. Add Command Handler
~~~~~~~~~~~~~~~~~~~~~~~

In ``src/mud_server/api/routes.py``:

.. code-block:: python

    # In the command parser (around line 250):
    elif cmd in ["examine", "ex"]:
        if not args:
            return JSONResponse({"result": "Examine what?"})
        target = args[0]
        result = engine.examine(username, target)
        return JSONResponse({"result": result})

3. Restart Server
~~~~~~~~~~~~~~~~~

The new command is now available to players.

Extending World Data
--------------------

World data is defined in ``data/world_data.json``.

Adding Room Properties
~~~~~~~~~~~~~~~~~~~~~~~

1. **Update JSON schema**:

.. code-block:: json

    {
      "rooms": {
        "library": {
          "id": "library",
          "name": "Ancient Library",
          "description": "Dusty books line the shelves.",
          "exits": {"south": "spawn"},
          "items": ["book"],
          "properties": {
            "light_level": "dim",
            "temperature": "cool"
          }
        }
      }
    }

2. **Update dataclass** in ``src/mud_server/core/world.py``:

.. code-block:: python

    @dataclass
    class Room:
        id: str
        name: str
        description: str
        exits: dict[str, str]
        items: list[str]
        properties: dict[str, str] = field(default_factory=dict)

3. **Update World loader** to parse new fields

4. **Use in game logic**:

.. code-block:: python

    room = self.world.get_room(player["current_room"])
    if room.properties.get("light_level") == "dim":
        return "It's too dark to see clearly."

Adding Database Tables
-----------------------

To add a new table (e.g., for achievements):

Define Schema
~~~~~~~~~~~~~

In ``src/mud_server/db/database.py``:

.. code-block:: python

    def init_db():
        # ... existing code ...

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                achievement_id TEXT NOT NULL,
                earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (character_id) REFERENCES characters (id)
            )
        """)

Add CRUD Functions
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def add_achievement(character_id: int, achievement_id: str):
        """Record an achievement for a character."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO achievements (character_id, achievement_id) VALUES (?, ?)",
                (character_id, achievement_id)
            )
            conn.commit()

    def get_achievements(character_id: int) -> list[dict]:
        """Get all achievements for a character."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM achievements WHERE character_id = ?",
                (character_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

Add API Endpoint
~~~~~~~~~~~~~~~~

In ``src/mud_server/api/routes.py``:

.. code-block:: python

    @app.get("/api/achievements/{character_id}")
    async def get_player_achievements(character_id: int):
        """Get all achievements for a character."""
        if not validate_session(request):
            raise HTTPException(status_code=401, detail="Not authenticated")

        achievements = db.get_achievements(character_id)
        return achievements

Add Client Wrapper
~~~~~~~~~~~~~~~~~~

In ``src/mud_server/client/api/game.py``:

.. code-block:: python

    def get_achievements(self, character_id: int) -> dict:
        """Fetch achievements for a character."""
        response = self._get(f"/api/achievements/{character_id}")
        return self._parse_response(response)

Adding API Endpoints
--------------------

Define Pydantic Model
~~~~~~~~~~~~~~~~~~~~~

In ``src/mud_server/api/models.py``:

.. code-block:: python

    class AchievementResponse(BaseModel):
        achievement_id: str
        earned_at: str
        description: str

Add Route
~~~~~~~~~

In ``src/mud_server/api/routes.py``:

.. code-block:: python

    @app.get("/api/achievements/{username}", response_model=list[AchievementResponse])
    async def get_player_achievements(username: str, request: Request):
        """Get all achievements for a player."""
        if not validate_session(request):
            raise HTTPException(status_code=401, detail="Not authenticated")

        achievements = db.get_achievements(username)
        return achievements

Testing Strategy
----------------

Unit Tests
~~~~~~~~~~

Test individual functions:

.. code-block:: python

    def test_move_command():
        """Test player movement between rooms."""
        engine = GameEngine(world, db)
        result = engine.move("test_user", "north")
        assert "moved north" in result.lower()

Integration Tests
~~~~~~~~~~~~~~~~~

Test component interactions:

.. code-block:: python

    def test_pickup_and_inventory():
        """Test item pickup and inventory display."""
        engine.pickup_item("test_user", "torch")
        inventory = engine.get_inventory("test_user")
        assert "torch" in inventory

API Tests
~~~~~~~~~

Test HTTP endpoints:

.. code-block:: python

    def test_command_endpoint(client):
        """Test /api/command endpoint."""
        response = client.post("/api/command", json={
            "username": "test_user",
            "command": "look"
        })
        assert response.status_code == 200
        assert "result" in response.json()

Key Implementation Principles
------------------------------

1. Determinism First
~~~~~~~~~~~~~~~~~~~~

All game logic should be:

* **Reproducible** - Same inputs yield same outputs
* **Testable** - Write unit tests for all mechanics
* **Traceable** - Log important state changes
* **Debuggable** - Use seeds for random generation

2. Separation of Concerns
~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Client Layer** - UI and user interaction only
* **API Layer** - HTTP routing and validation
* **Game Layer** - Core mechanics and state
* **Database Layer** - Persistence only

3. Data-Driven Design
~~~~~~~~~~~~~~~~~~~~~~

Store configuration in data files, not code:

* World definitions (``data/world_data.json``)
* Environment variables for server config
* Database for runtime state only

4. API Stability
~~~~~~~~~~~~~~~~

When adding features:

* Don't break existing endpoints - add new ones
* Use semantic versioning - document breaking changes
* Return consistent structure - always include success/message/data
* Document with Pydantic - models serve as documentation

Best Practices
--------------

Code Organization
~~~~~~~~~~~~~~~~~

Keep code organized by feature::

    src/mud_server/
    ├── core/
    │   ├── engine.py         # Main game logic
    │   ├── world.py          # World data structures
    │   └── mechanics/        # Specific game mechanics
    ├── db/
    │   ├── database.py       # Core database operations
    │   └── migrations/       # Schema migrations
    ├── api/
    │   ├── server.py
    │   ├── routes.py
    │   ├── models.py
    │   └── ...
    └── client/
        ├── app.py
        ├── api/              # API client wrappers
        ├── tabs/             # UI components
        └── ui/               # Utilities

Migration Strategy
~~~~~~~~~~~~~~~~~~

When adding new features:

1. Keep existing features working
2. Add new systems alongside old ones
3. Use feature flags for testing
4. Gradual rollout to users
5. Preserve data - don't lose player progress

Contributing
------------

See the Contributing Guide for:

* Code style guidelines
* Pull request process
* Testing requirements
* Documentation standards
