# PipeWorks MUD Server

Welcome to **PipeWorks MUD Server** documentation! This is a deterministic, procedural multiplayer text game engine for building accountable interactive fiction worlds.

## What is PipeWorks MUD Server?

PipeWorks MUD Server is a modern, extensible MUD (Multi-User Dungeon) server framework built with Python, FastAPI, and Gradio. It provides a solid foundation for creating text-based multiplayer games with:

### Core Capabilities

1. **Data-Driven World Design** - Define worlds entirely in JSON. Create rooms, items, and connections without writing code.

2. **Modern Web Interface** - Beautiful Gradio client with clean UX, mobile-responsive design, and dark mode support.

3. **RESTful Architecture** - FastAPI backend with proper separation of concerns, making it easy to build custom clients.

4. **Deterministic Game Logic** - All game mechanics are programmatic and reproducible - perfect for testing and debugging.

5. **Extensible Command System** - Add new commands by implementing simple handler functions. No complex plugin system needed.

## Current Implementation Status

This project provides a **working proof-of-concept** MUD server with these features:

- ✅ FastAPI REST API backend (port 8000)
- ✅ Gradio web interface (port 7860)
- ✅ SQLite database for persistence
- ✅ Authentication and session management
- ✅ Role-based access control (Player/WorldBuilder/Admin/Superuser)
- ✅ Room navigation with directional movement
- ✅ Inventory system (pickup/drop items)
- ✅ Multi-channel chat (say/yell/whisper)
- ✅ JSON-based world data structure
- ✅ Ollama AI integration (admin/superuser only)
- ✅ 100% test coverage on core client modules

See the [Implementation Roadmap](implementation/roadmap.md) for planned features.

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install and run the server in minutes

    [:octicons-arrow-right-24: Quick Start](getting-started/quick-start.md)

-   :material-cog:{ .lg .middle } **Architecture**

    ---

    Understand the technical design

    [:octicons-arrow-right-24: System Overview](architecture/overview.md)

-   :material-gamepad-variant:{ .lg .middle } **User Guide**

    ---

    Learn how to play and build worlds

    [:octicons-arrow-right-24: Playing Guide](guide/playing.md)

-   :material-code-braces:{ .lg .middle } **API Reference**

    ---

    Complete API documentation

    [:octicons-arrow-right-24: API Docs](api/index.md)

</div>

## Key Features

### For Players

- **Intuitive Commands**: Natural language-style commands (north/n, look/l, inventory/inv)
- **Multiplayer Chat**: Room-based communication with whisper and yell support
- **Web-Based Interface**: No client installation needed - just open your browser
- **Real-Time Updates**: See other players' actions as they happen

### For Developers

- **Clean Architecture**: Three-tier design (Client → API → Engine/Database)
- **Modern Python**: Python 3.12+, type hints, comprehensive tests
- **Modular Client**: API clients work outside Gradio (CLI tools, tests, scripts)
- **Extensible Design**: Add new commands, mechanics, or features easily
- **Comprehensive Tests**: High code coverage with pytest
- **CI/CD Ready**: GitHub Actions, Codecov integration, automated testing

### For World Builders

- **JSON World Definition**: Create entire worlds with simple JSON files
- **No Code Required**: Build rooms, items, and connections without programming
- **Hot Reload**: Update world data without restarting the server (coming soon)
- **Visual Tools**: World editor interface planned for future releases
- **Flexible Structure**: Support for any theme (fantasy, sci-fi, historical, etc.)

## Technology Stack

- **Backend**: FastAPI (REST API), Python 3.12+
- **Frontend**: Gradio 5.0+ (web interface)
- **Database**: SQLite with direct access (aiosqlite support planned)
- **Authentication**: Bcrypt password hashing, session-based auth
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Code Quality**: ruff (linting), black (formatting), mypy (type checking)

## Design Philosophy

### Programmatic Authority

All game logic and state is deterministic and code-driven. Game mechanics are reproducible, testable, and never left to LLM interpretation. This ensures:

- **Predictable Behavior**: Same inputs always produce same outputs
- **Debuggable Systems**: You can trace exactly why something happened
- **No Hallucinations**: Game state never drifts due to AI uncertainty
- **Replayable Actions**: Seed-based determinism for testing and debugging

### Clean Separation of Concerns

- **Client Layer** (Gradio): UI and user interaction
- **Server Layer** (FastAPI): HTTP API and routing
- **Game Layer** (Engine + World): Core mechanics and state
- **Persistence Layer** (SQLite): Data storage

This separation makes it easy to:

- Build alternative clients (CLI, mobile app, etc.)
- Test components in isolation
- Extend one layer without affecting others
- Deploy across multiple servers

### Data-Driven World Design

World content lives in JSON files, not in code. This means:

- **Rapid Prototyping**: Test new rooms and items in seconds
- **Non-Programmer Friendly**: World builders don't need to code
- **Version Control**: Track world changes in git
- **Easy Sharing**: Export and import world data between servers

## Documentation Structure

This documentation is organized into several sections:

- **[Getting Started](getting-started/index.md)**: Installation, setup, and first steps
- **[Architecture](architecture/index.md)**: Technical architecture and system design
- **[Implementation](implementation/index.md)**: Code examples and implementation details
- **[User Guide](guide/index.md)**: How to play and use the system
- **[Developer Guide](developer/index.md)**: Contributing, testing, and development workflow
- **[API Reference](api/index.md)**: Complete API documentation (auto-generated)

## Example Use Cases

### Fantasy MUD

```json
{
  "rooms": {
    "tavern": {
      "name": "The Prancing Pony",
      "description": "A cozy tavern with a roaring fireplace.",
      "exits": {"north": "market_square"}
    }
  }
}
```

### Sci-Fi Adventure

```json
{
  "rooms": {
    "bridge": {
      "name": "Starship Bridge",
      "description": "The command center of the USS Discovery.",
      "exits": {"down": "engineering"}
    }
  }
}
```

### Educational Game

```json
{
  "rooms": {
    "history_hall": {
      "name": "Ancient Rome Exhibit",
      "description": "Artifacts from the Roman Empire.",
      "exits": {"east": "egypt_exhibit"}
    }
  }
}
```

## Get Involved

This is an open-source project. Contributions are welcome!

- **GitHub**: [pipeworks_mud_server](https://github.com/aa-parky/pipeworks_mud_server)
- **Issues**: Report bugs or request features
- **Discussions**: Share ideas and ask questions
- **Contributing**: See the [Developer Guide](developer/contributing.md)

## License

This project is licensed under the GNU General Public License v3.0. See the [License](about/license.md) page for details.
