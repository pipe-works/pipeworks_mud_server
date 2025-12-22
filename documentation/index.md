# The Undertaking

Welcome to **The Undertaking** documentation! This is a procedural, ledger-driven multiplayer interactive fiction system where accountability matters more than optimization.

## What is The Undertaking?

The Undertaking is a unique MUD (Multi-User Dungeon) that challenges conventional game design through five core principles:

### Design Pillars

1. **Characters are issued, not built** - Players receive complete, immutable goblins with uneven attributes, mandatory quirks, persistent failings, and inherited reputations. No optimization, no respeccing.

2. **Failure is recorded as data** - Actions resolve through six axes (Timing, Precision, Stability, Visibility, Interpretability, Recovery Cost) and are recorded in an immutable ledger.

3. **Ledgers are truth, newspapers are stories** - The deterministic ledger (hard truth) is separated from narrative interpretation (soft truth). The same failure can be told different ways.

4. **Optimization is resisted** - No "best builds" or meta-gaming. Success comes from understanding your specific goblin's flaws and working within them.

5. **Players become creators** - Journey from functionary (survive) → tinkerer (understand) → creator (build). Eventually use the same tools as developers to create content.

## Current Status

This project is currently a **proof-of-concept** MUD server that validates the technical architecture. The following features are implemented:

- ✅ FastAPI backend with authentication and session management
- ✅ Gradio web interface for client interaction
- ✅ SQLite database for persistence
- ✅ Basic room navigation and chat system
- ✅ Role-based access control (Player/WorldBuilder/Admin/Superuser)
- ✅ JSON-based world data structure

Many features from the full design vision are planned but not yet implemented. See the [Implementation Roadmap](implementation/roadmap.md) for details.

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __Getting Started__

    ---

    Install and run the server in minutes

    [:octicons-arrow-right-24: Quick Start](getting-started/quick-start.md)

-   :material-brain:{ .lg .middle } __Design Vision__

    ---

    Understand the philosophy and principles

    [:octicons-arrow-right-24: Core Articulation](design/articulation.md)

-   :material-floor-plan:{ .lg .middle } __Architecture__

    ---

    Explore the technical architecture

    [:octicons-arrow-right-24: System Overview](architecture/overview.md)

-   :material-code-braces:{ .lg .middle } __API Reference__

    ---

    Complete API documentation

    [:octicons-arrow-right-24: API Docs](api/index.md)

</div>

## Key Features

### For Players

- **Unique Characters**: Each goblin is procedurally generated with distinctive quirks, failings, and useless specializations
- **Meaningful Failure**: Failures aren't just binary outcomes - they have context, causes, and consequences
- **No Optimization**: Resist the urge to min-max. Your goblin is what it is.
- **Emergent Stories**: The newspaper system interprets your actions, creating narratives from mechanical outcomes

### For Developers

- **Clean Architecture**: Three-tier design with FastAPI backend, Gradio frontend, and SQLite persistence
- **Deterministic Resolution**: All game logic is replayable from seed - no LLM hallucinations
- **Extensible Design**: Modular systems for characters, items, rooms, and actions
- **Comprehensive Tests**: 80%+ code coverage with pytest
- **Modern Python**: Python 3.12+, type hints, src-layout structure

### For World Builders

- **Creator's Toolkit**: Gradio-based authoring environment (coming soon)
- **Content Libraries**: JSON-based quirks, failings, items, and environmental properties
- **Player-Created Content**: Players can become creators, designing new content for the world
- **Deterministic Systems**: No silent failures - all mechanics are trackable and debuggable

## Technology Stack

- **Backend**: FastAPI (REST API), Python 3.12+
- **Frontend**: Gradio (web interface)
- **Database**: SQLite with aiosqlite
- **Authentication**: Bcrypt password hashing, session-based auth
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Code Quality**: ruff (linting), black (formatting), mypy (type checking)

## Documentation Structure

This documentation is organized into several sections:

- **[Getting Started](getting-started/index.md)**: Installation, setup, and first steps
- **[Design Vision](design/index.md)**: Philosophy, principles, and design goals
- **[Architecture](architecture/index.md)**: Technical architecture and system design
- **[Implementation](implementation/index.md)**: Code examples and implementation details
- **[User Guide](guide/index.md)**: How to play and use the system
- **[Developer Guide](developer/index.md)**: Contributing, testing, and development workflow
- **[API Reference](api/index.md)**: Complete API documentation (auto-generated)

## Get Involved

This is an open-source project. Contributions are welcome!

- **GitHub**: [pipeworks_mud_server](https://github.com/yourusername/pipeworks_mud_server)
- **Issues**: Report bugs or request features
- **Discussions**: Share ideas and ask questions

## License

This project is open-source. See the [License](about/license.md) page for details.
