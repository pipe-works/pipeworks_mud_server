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

In ``src/mud_server/db/schema.py`` inside ``init_database``:

.. code-block:: python

    def init_database(*, skip_superuser: bool = False) -> None:
        # ... existing schema statements ...
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

Create a repository module (for example ``src/mud_server/db/achievements_repo.py``):

.. code-block:: python

    def add_achievement(character_id: int, achievement_id: str):
        """Record an achievement for a character."""
        with connection_scope(write=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO achievements (character_id, achievement_id) VALUES (?, ?)",
                (character_id, achievement_id)
            )

    def get_achievements(character_id: int) -> list[dict]:
        """Get all achievements for a character."""
        with connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM achievements WHERE character_id = ?",
                (character_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

Add API Endpoint
~~~~~~~~~~~~~~~~

Expose the repository function from ``mud_server.db.facade`` and use it from
an API route module (for example ``src/mud_server/api/routes/game.py``):

Do not add new runtime exports to ``mud_server.db.database``. That module exists
only as a compatibility re-export surface for legacy imports and tests.

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

* World definitions (``data/worlds/<world_id>/world.json``)
* Resolution grammar (``policies/resolution.yaml``)
* Translation prompt (``policies/ic_prompt.txt``)
* Environment variables for server config
* Database for runtime state only

Enabling Subsystems Per World
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each world opts in to the axis engine and translation layer
independently via ``world.json``:

.. code-block:: json

   {
     "axis_engine":       {"enabled": true},
     "translation_layer": {"enabled": true, "model": "gemma2:2b"}
   }

Both default to ``false``.  A world that enables ``axis_engine`` but
not ``translation_layer`` will compute axis mutations without rendering
IC dialogue (and vice versa).  The engine degrades gracefully in all
combinations.

Adding a New Resolver
~~~~~~~~~~~~~~~~~~~~~

To add a new resolver algorithm:

1. Add a pure function to ``src/mud_server/axis/resolvers.py``
   matching the resolver contract:

   .. code-block:: python

      def my_resolver(
          speaker_score: float,
          listener_score: float,
          *,
          base_magnitude: float,
          multiplier: float,
      ) -> tuple[float, float]:
          """Return (speaker_delta, listener_delta).  Never raise; never clamp."""
          ...

2. Register it in ``_RESOLVER_REGISTRY`` in ``src/mud_server/axis/engine.py``:

   .. code-block:: python

      _RESOLVER_REGISTRY: dict[str, Callable] = {
          "dominance_shift": dominance_shift,
          "shared_drain":    shared_drain,
          "no_effect":       no_effect,
          "my_resolver":     my_resolver,   # ← add here
      }

3. Reference it from any world's ``policies/resolution.yaml``:

   .. code-block:: yaml

      axes:
        some_axis:
          resolver: my_resolver
          base_magnitude: 0.05

   No other code changes are required.

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
    │   ├── engine.py         # GameEngine: chat calls axis engine then translation
    │   ├── world.py          # World dataclass; loads axis engine + translation service
    │   ├── bus.py            # Event bus
    │   └── events.py         # Event type constants
    ├── axis/                 # Axis resolution engine
    │   ├── __init__.py       # Exports: AxisEngine, AxisResolutionResult
    │   ├── types.py          # AxisDelta, EntityResolution, AxisResolutionResult
    │   ├── grammar.py        # ResolutionGrammar loader (resolution.yaml)
    │   ├── resolvers.py      # dominance_shift, shared_drain, no_effect
    │   └── engine.py         # AxisEngine class
    ├── ledger/               # JSONL audit ledger
    │   ├── __init__.py       # Exports: append_event, verify_world_ledger
    │   └── writer.py         # append_event, verify, checksum, POSIX file lock
    ├── translation/          # OOC→IC translation layer
    │   ├── config.py         # TranslationLayerConfig (frozen dataclass)
    │   ├── profile_builder.py # CharacterProfileBuilder
    │   ├── renderer.py       # OllamaRenderer
    │   ├── validator.py      # OutputValidator (PASSTHROUGH sentinel)
    │   └── service.py        # OOCToICTranslationService (orchestrator)
    ├── db/
    │   ├── facade.py         # App-facing DB contract
    │   ├── database.py       # Compatibility re-export module only
    │   ├── schema.py         # DDL + invariant triggers
    │   ├── connection.py     # SQLite connection/transaction helpers
    │   ├── users_repo.py     # Account persistence
    │   ├── characters_repo.py # Character identity, inventory, room state
    │   ├── sessions_repo.py  # Session lifecycle and world activity
    │   ├── chat_repo.py      # Chat persistence
    │   ├── worlds_repo.py    # World catalog, access decisions, online status
    │   ├── axis_repo.py      # Axis policy/state registry and scoring helpers
    │   ├── events_repo.py    # Event ledger persistence (apply_axis_event)
    │   └── admin_repo.py     # Admin dashboard and inspector read paths
    ├── api/
    │   ├── server.py
    │   ├── routes.py
    │   ├── models.py
    │   └── ...
    └── web/                  # Admin WebUI
        ├── routes.py
        ├── templates/
        └── static/

Migration Strategy
~~~~~~~~~~~~~~~~~~

When adding new features:

1. Define compatibility policy first (breaking changes are acceptable only when explicitly versioned and documented)
2. Change the app-facing contract in ``mud_server.db.facade`` and update call sites
3. Keep repository responsibilities bounded (do not re-introduce monolithic DB helpers)
4. Add/adjust tests for contract, repository behavior, and error mapping at API boundaries
5. Preserve data and invariants with schema changes, indexes, and migration notes

Contributing
------------

See the Contributing Guide for:

* Code style guidelines
* Pull request process
* Testing requirements
* Documentation standards
