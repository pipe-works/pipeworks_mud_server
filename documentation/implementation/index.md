# Implementation

Current implementation status and extension guides for PipeWorks MUD Server.

## Overview

This section provides implementation details for:

- **Current feature set** - What's built and working
- **Extension patterns** - How to add new features
- **Database design** - Schema and data structures
- **API design** - Request/response patterns

## Current Implementation

### Core Features ✅

The server provides a complete, working MUD foundation:

#### Authentication & Access Control

- Session-based authentication with bcrypt password hashing
- Role-based permissions (Player, WorldBuilder, Admin, Superuser)
- UUID-based session management
- Permission validation decorators

#### World System

- JSON-driven world definition (rooms, items, exits)
- Room navigation with directional movement
- Item system (pickup/drop mechanics)
- World data loading and validation

#### Communication

- Room-based chat (`say` command)
- Area-wide announcements (`yell` command)
- Private messaging (`whisper` command)
- Multi-player presence tracking

#### Client Interface

- Gradio web UI with tabbed interface
- Modular API client layer (100% test coverage)
- Real-time command processing
- Auto-refresh chat display
- Safari-compatible dark mode

#### Admin Tools

- User management interface
- Database viewer
- Server control panel
- Ollama AI integration (admin/superuser only)

### Architecture Components

**Backend** (`src/mud_server/api/`):

- `server.py` - FastAPI app initialization, CORS configuration
- `routes.py` - REST API endpoints
- `models.py` - Pydantic request/response schemas
- `auth.py` - Session management
- `password.py` - Password hashing utilities
- `permissions.py` - RBAC system

**Game Engine** (`src/mud_server/core/`):

- `engine.py` - GameEngine class with game logic
- `world.py` - World, Room, Item dataclasses

**Database** (`src/mud_server/db/`):

- `database.py` - SQLite operations, schema, CRUD functions

**Frontend** (`src/mud_server/client/`):

- `app.py` - Main Gradio interface
- `api/` - API client layer (auth, game, admin, settings, ollama)
- `tabs/` - UI tab components (login, game, settings, database, help)
- `ui/` - Validation and state management utilities

## Extension Patterns

### Adding New Commands

To add a new command (e.g., `examine`):

1. **Add method to GameEngine** ([src/mud_server/core/engine.py](src/mud_server/core/engine.py)):

```python
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
```

1. **Add command handler to routes** ([src/mud_server/api/routes.py](src/mud_server/api/routes.py)):

```python
# In the command parser function:
elif cmd in ["examine", "ex"]:
    if not args:
        return JSONResponse({"result": "Examine what?"})
    target = args[0]
    result = engine.examine(username, target)
    return JSONResponse({"result": result})
```

1. **Restart server** - The new command is now available

### Extending World Data

World data is defined in `data/world_data.json`. To add new properties:

1. **Update JSON schema**:

```json
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
```

1. **Update dataclass** ([src/mud_server/core/world.py](src/mud_server/core/world.py)):

```python
@dataclass
class Room:
    id: str
    name: str
    description: str
    exits: dict[str, str]
    items: list[str]
    properties: dict[str, str] = field(default_factory=dict)  # Add this
```

1. **Update World loader** to parse new fields

1. **Use in game logic**:

```python
room = self.world.get_room(player["current_room"])
if room.properties.get("light_level") == "dim":
    return "It's too dark to see clearly."
```

### Adding Database Tables

To add a new table (e.g., for achievements):

1. **Define schema** in [src/mud_server/db/database.py](src/mud_server/db/database.py):

```python
def init_db():
    # ... existing code ...

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            achievement_id TEXT NOT NULL,
            earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (username) REFERENCES players (username)
        )
    """)
```

1. **Add CRUD functions**:

```python
def add_achievement(username: str, achievement_id: str):
    """Record an achievement for a player."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO achievements (username, achievement_id) VALUES (?, ?)",
            (username, achievement_id)
        )
        conn.commit()

def get_achievements(username: str) -> list[dict]:
    """Get all achievements for a player."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM achievements WHERE username = ?",
            (username,)
        )
        return [dict(row) for row in cursor.fetchall()]
```

1. **Add API endpoint** in routes.py

1. **Add UI component** in appropriate tab

### Adding API Endpoints

To add a new API endpoint:

1. **Define Pydantic model** ([src/mud_server/api/models.py](src/mud_server/api/models.py)):

```python
class AchievementResponse(BaseModel):
    achievement_id: str
    earned_at: str
    description: str
```

1. **Add route** ([src/mud_server/api/routes.py](src/mud_server/api/routes.py)):

```python
@app.get("/api/achievements/{username}", response_model=list[AchievementResponse])
async def get_player_achievements(username: str):
    """Get all achievements for a player."""
    if not validate_session(request):
        raise HTTPException(status_code=401, detail="Not authenticated")

    achievements = db.get_achievements(username)
    return achievements
```

1. **Add client wrapper** ([src/mud_server/client/api/game.py](src/mud_server/client/api/game.py)):

```python
def get_achievements(self, username: str) -> dict:
    """Fetch achievements for a player."""
    response = self._get(f"/api/achievements/{username}")
    return self._parse_response(response)
```

1. **Use in UI** - Call from tab component

## Key Implementation Principles

### 1. Determinism First

All game logic should be:

- **Reproducible** - Same inputs yield same outputs
- **Testable** - Write unit tests for all mechanics
- **Traceable** - Log important state changes
- **Debuggable** - Use seeds for random generation where possible

### 2. Separation of Concerns

- **Client Layer** - UI and user interaction only
- **API Layer** - HTTP routing and validation
- **Game Layer** - Core mechanics and state
- **Database Layer** - Persistence only

Don't mix these layers. Keep them independent.

### 3. Data-Driven Design

Store configuration in data files, not code:

- World definitions (`data/world_data.json`)
- Future: Items, NPCs, quests as JSON
- Environment variables for server config
- Database for runtime state only

**Benefits**:

- Non-programmers can create content
- Easy to test different configurations
- Version control friendly
- Hot-reload capability (future)

### 4. API Stability

When adding features:

- **Don't break existing endpoints** - Add new ones instead
- **Use semantic versioning** - Document breaking changes
- **Return consistent structure** - Always include `success`, `message`, `data`
- **Document with Pydantic** - Models serve as documentation

## Testing Strategy

### Unit Tests

Test individual functions in isolation:

```python
def test_move_command():
    """Test player movement between rooms."""
    engine = GameEngine(world, db)
    result = engine.move("test_user", "north")
    assert "moved north" in result.lower()
```

### Integration Tests

Test component interactions:

```python
def test_pickup_and_inventory():
    """Test item pickup and inventory display."""
    engine.pickup_item("test_user", "torch")
    inventory = engine.get_inventory("test_user")
    assert "torch" in inventory
```

### API Tests

Test HTTP endpoints:

```python
def test_command_endpoint(client):
    """Test /api/command endpoint."""
    response = client.post("/api/command", json={
        "username": "test_user",
        "command": "look"
    })
    assert response.status_code == 200
    assert "result" in response.json()
```

### Determinism Tests

For randomized features:

```python
def test_deterministic_generation():
    """Test that same seed produces same result."""
    result1 = generate_with_seed(seed=42)
    result2 = generate_with_seed(seed=42)
    assert result1 == result2
```

## Code Organization

Keep code organized by feature:

```text
src/mud_server/
├── core/
│   ├── engine.py         # Main game logic
│   ├── world.py          # World data structures
│   └── mechanics/        # Future: specific game mechanics
│       ├── combat.py
│       ├── crafting.py
│       └── quests.py
├── db/
│   ├── database.py       # Core database operations
│   └── migrations/       # Future: schema migrations
├── api/
│   ├── server.py
│   ├── routes.py
│   ├── models.py
│   ├── auth.py
│   ├── password.py
│   └── permissions.py
└── client/
    ├── app.py
    ├── api/              # API client wrappers
    ├── tabs/             # UI components
    └── ui/               # Utilities
```

## Database Schema

### Current Tables

#### players

- `username` (TEXT, PRIMARY KEY)
- `password_hash` (TEXT)
- `role` (TEXT) - Player, WorldBuilder, Admin, Superuser
- `current_room` (TEXT) - Current location
- `inventory` (TEXT) - JSON array of item IDs
- `created_at` (TIMESTAMP)
- `last_login` (TIMESTAMP)

#### sessions

- `session_id` (TEXT, PRIMARY KEY) - UUID
- `username` (TEXT)
- `role` (TEXT)
- `created_at` (TIMESTAMP)
- `last_activity` (TIMESTAMP)

#### chat_messages

- `id` (INTEGER, PRIMARY KEY)
- `username` (TEXT)
- `message` (TEXT)
- `room_id` (TEXT)
- `message_type` (TEXT) - say, yell, whisper
- `target_username` (TEXT) - for whispers
- `timestamp` (TIMESTAMP)

## Migration Strategy

When adding new features:

1. **Keep existing features working** - Don't break current functionality
2. **Add alongside, not replace** - Preserve backward compatibility
3. **Feature flags** - Toggle new features for testing
4. **Gradual rollout** - Deploy to subset of users first
5. **Preserve data** - Never lose player progress

## Further Reading

- [Architecture Overview](../architecture/overview.md) - System design details
- [Database Schema](../architecture/database.md) - Complete schema documentation
- [API Design](../architecture/api-design.md) - API endpoint reference
- [Developer Guide](../developer/contributing.md) - How to contribute
- [Testing Guide](../developer/testing.md) - Testing best practices
