# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based MUD (Multi-User Dungeon) server with a web-based client interface, organized using a modern Python src-layout structure.

### Directory Structure
```
pipeworks_mud_server/
├── src/mud_server/        # Main package
│   ├── api/               # FastAPI REST API
│   │   ├── server.py      # App initialization and startup
│   │   ├── routes.py      # All API endpoints
│   │   ├── models.py      # Pydantic request/response models
│   │   └── auth.py        # Session validation
│   ├── core/              # Game engine logic
│   │   ├── engine.py      # GameEngine class
│   │   └── world.py       # World, Room, Item classes
│   ├── db/                # Database layer
│   │   └── database.py    # SQLite operations
│   └── client/            # Frontend
│       └── app.py         # Gradio web interface
├── data/                  # Data files
│   ├── world_data.json    # Room and item definitions
│   └── mud.db             # SQLite database (generated)
├── docs/                  # Documentation
├── logs/                  # Server and client logs
└── tests/                 # Test files
```

### Architecture Components
- **FastAPI backend** (src/mud_server/api/) - RESTful API server on port 8000
- **Gradio frontend** (src/mud_server/client/) - Web interface on port 7860
- **Game engine** (src/mud_server/core/) - Core game logic and world management
- **SQLite database** (src/mud_server/db/) - Player state, sessions, and chat persistence
- **JSON world data** (data/) - Room and item definitions

## Common Commands

### Setup and Installation
```bash
# Setup virtual environment and dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Initialize database (required before first run)
PYTHONPATH=src python3 -m mud_server.db.database
```

**Note**: The project uses src-layout structure, so `PYTHONPATH=src` is required when running modules directly. The `run.sh` script handles this automatically.

### Running the Server
```bash
# Start both server and client
./run.sh

# The script starts:
# - FastAPI server on http://0.0.0.0:8000
# - Gradio client on http://0.0.0.0:7860
# Press Ctrl+C to stop both services
```

### Development
```bash
# Run server only (for API development)
PYTHONPATH=src python3 src/mud_server/api/server.py

# Run client only (ensure server is running first)
PYTHONPATH=src python3 src/mud_server/client/app.py

# Check server health
curl http://localhost:8000/health

# Reset database (deletes all player data)
rm data/mud.db && PYTHONPATH=src python3 -m mud_server.db.database
```

### Environment Variables
```bash
# Configure server binding (defaults shown)
export MUD_HOST="0.0.0.0"
export MUD_PORT=8000
export MUD_SERVER_URL="http://localhost:8000"
```

## Architecture

### Three-Tier Design

**Client Layer (src/mud_server/client/app.py)**
- Gradio web interface with login, game, and help tabs
- Stateful session management using `gr.State`
- HTTP requests to backend API endpoints
- Real-time display updates for room, inventory, chat, and player status

**Server Layer (src/mud_server/api/)**
- **server.py**: FastAPI app initialization, CORS middleware, engine instance
- **routes.py**: All API endpoint definitions, command parsing
- **models.py**: Pydantic request/response models
- **auth.py**: Session validation and in-memory session tracking

**Game Engine Layer (src/mud_server/core/)**
- **world.py**: `World`, `Room`, `Item` classes - loads and manages data from JSON
- **engine.py**: `GameEngine` class - implements game logic (movement, inventory, chat)
- Database interface for persistence
- Room-based chat and player presence system

### Data Flow Patterns

**Session Management**
- Login creates UUID session_id stored in both database and server memory (auth.py:active_sessions)
- All API requests require valid session_id for authentication
- Sessions are not persisted to disk (lost on server restart)
- Session activity updated on each API call via `update_session_activity()`

**Player Movement**
1. Client sends command to `/command` endpoint
2. Server validates session and parses direction
3. Engine checks current room exits via `world.can_move()`
4. Database updated with new room via `set_player_room()`
5. Engine generates room description including items, players, exits
6. Broadcast messages sent (not yet implemented - see `_broadcast_to_room()`)

**Chat System**
- Messages stored in `chat_messages` table with room association
- Only messages from player's current room are retrieved
- Room-based isolation (players only see messages from their location)
- Chat retrieval limited to 20 recent messages by default

**Inventory Management**
- Stored as JSON array in players table
- Items picked up are NOT removed from room (intentional design)
- Items dropped are NOT added back to room
- Item matching uses case-insensitive name comparison

### Database Schema

**players table**
- `username` (unique) - Player identifier
- `current_room` - Current location (room ID)
- `inventory` - JSON array of item IDs
- Timestamps for created_at and last_login

**sessions table**
- `username` (unique) - One session per player
- `session_id` (unique) - UUID for API authentication
- Timestamps for connected_at and last_activity

**chat_messages table**
- `username` - Message sender
- `message` - Message content
- `room` - Room where message was sent
- `timestamp` - Message time

### World Data Structure

World is defined in `data/world_data.json`:
- **Rooms**: id, name, description, exits dict, items list
- **Items**: id, name, description
- Default spawn room is "spawn" (central hub)
- Exits are one-way unless explicitly defined in both directions

## Key Design Patterns

**Command Parsing** (routes.py:60-150)
- Commands split into `cmd` and `args`
- Directional shortcuts (n/s/e/w) mapped to full names
- Each command type delegates to specific engine method
- Returns `CommandResponse` with success flag and message

**Room Description Generation** (world.py:77-112)
- Combines room name, description, items, players, and exits
- Players list excludes requesting user
- Active players determined by session table JOIN
- Exit names resolved from room IDs

**Session Validation** (auth.py:16-22)
- All protected endpoints call `validate_session()`
- Raises 401 HTTPException on invalid session
- Updates session activity timestamp on success
- Returns username for subsequent operations

## Important Considerations

**Item Pickup Behavior**
- Items remain in room after pickup (not removed from `data/world_data.json`)
- Multiple players can pick up same item
- Dropping items doesn't add them back to room
- This is intentional for the current proof-of-concept design

**Broadcast Messages**
- `_broadcast_to_room()` is stubbed (engine.py:185-189)
- Movement notifications not actually sent to other players
- Would require WebSocket implementation for real-time delivery

**Session Persistence**
- Sessions stored only in memory (`active_sessions` dict in auth.py)
- Server restart disconnects all players
- Database sessions table also tracks sessions but server memory is source of truth

**Concurrency**
- SQLite handles basic locking for concurrent writes
- No explicit transaction management or optimistic locking
- Suitable for ~50-100 concurrent players

**No Password Authentication**
- Login only requires username
- No password, email, or other verification
- Anyone can login as any username
- Sessions prevent username conflicts while logged in

## File Responsibilities

### API Layer (src/mud_server/api/)
**server.py**
- FastAPI app initialization and configuration
- CORS middleware setup
- GameEngine instantiation
- Route registration
- Main entry point with uvicorn

**routes.py**
- All API endpoint definitions
- Command parsing and routing to game engine
- Request validation and error handling

**models.py**
- Pydantic request models (LoginRequest, CommandRequest, ChatRequest)
- Pydantic response models (LoginResponse, CommandResponse, StatusResponse)

**auth.py**
- In-memory session storage (`active_sessions` dict)
- Session validation logic
- Session activity tracking

### Core Layer (src/mud_server/core/)
**engine.py**
- GameEngine class with all game logic
- Player actions (movement, inventory, chat)
- Room navigation and validation
- Database integration

**world.py**
- World, Room, Item dataclasses
- JSON world data loading
- Room description generation
- Exit validation

### Database Layer (src/mud_server/db/)
**database.py**
- SQLite connection management
- Table schema definitions (players, sessions, chat_messages)
- CRUD operations for all entities
- JSON serialization for inventory

### Client Layer (src/mud_server/client/)
**app.py**
- Gradio interface components
- Tab layouts (login, game, help)
- Event handlers for buttons and inputs
- API request formatting and response handling

### Data Files
**data/world_data.json**
- Static world definition (rooms and items)
- Not modified during gameplay
- Loaded once at engine initialization

**data/mud.db**
- SQLite database (generated at runtime)
- Stores players, sessions, chat messages
