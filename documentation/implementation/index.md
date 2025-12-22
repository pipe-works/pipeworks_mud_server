# Implementation

Code examples, database schema, and implementation details for The Undertaking.

## Overview

This section provides detailed implementation guidance for:

- **Axis-based resolution** engine
- **Character issuance** system
- **Ledger and newspaper** (two-layer truth)
- **Item quirks** and maker profiles
- **Database schema** for full implementation

## Implementation Documents

<div class="grid cards" markdown>

-   :material-code-tags:{ .lg .middle } __Code Examples__

    ---

    Pseudo-code and database schema for core systems

    [:octicons-arrow-right-24: Code Examples](code-examples.md)

-   :material-file-code:{ .lg .middle } __Supplementary Examples__

    ---

    Content libraries, API examples, additional details

    [:octicons-arrow-right-24: Supplementary Examples](supplementary-examples.md)

-   :material-road-variant:{ .lg .middle } __Implementation Roadmap__

    ---

    Phases, priorities, and timeline for development

    [:octicons-arrow-right-24: Roadmap](roadmap.md)

</div>

## Current Status

### Implemented Features ✅

The proof-of-concept validates the technical architecture:

- FastAPI backend with REST API
- Gradio frontend with tabs
- SQLite database for persistence
- Session-based authentication
- Role-based access control (RBAC)
- Basic room navigation
- Inventory management
- Room-based chat
- JSON world data loading

### Designed But Not Implemented ⏳

The following systems are fully designed with pseudo-code and schema:

- **Character Issuance** - Procedural generation with quirks, failings, useless bits
- **Axis-Based Resolution** - Six-axis action resolution engine
- **Ledger System** - Immutable action records with blame attribution
- **Newspaper System** - Narrative interpretation layer
- **Item Quirks** - Items with maker profiles and mechanical properties
- **Environmental Quirks** - Room properties affecting resolution
- **Reputation System** - Bias and blame tracking
- **Creator's Toolkit** - Gradio authoring environment

## Implementation Phases

### Phase 1: Character Issuance

Extend the current player system with:

- Procedural name generation
- Attribute distribution (seven stats)
- Quirk selection (2-4 mandatory)
- Failing assignment
- Useless bit assignment
- Character sealing (immutable)

**Database Changes**:
- Add `characters` table
- Link to `players` via `account_id`
- Store quirks, failings, useless_bits as JSON or relations

### Phase 2: Resolution Engine

Replace simple command parsing with:

- Six-axis deviation calculation
- Quirk modifier system
- Failing application
- Deterministic seeding
- Outcome determination
- Contributing factor tracking

**Key Modules**:
- `resolution/engine.py` - Main resolution logic
- `resolution/axes.py` - Axis definitions
- `resolution/modifiers.py` - Quirk and failing effects

### Phase 3: Ledger System

Add immutable action recording:

- Ledger table with all action details
- Contributing factors JSON
- Blame weight calculation
- Replay capability from seed
- Hard truth storage

**Database Changes**:
- Add `ledger` table
- Store seed, inputs, modifiers, outcome
- Never update once written

### Phase 4: Interpretation Layer

Add narrative generation:

- Newspaper table with articles
- LLM integration for narrative
- Reputation-based interpretation
- Context variation
- Regeneration support

**Key Modules**:
- `interpretation/newspaper.py` - Article generation
- `interpretation/reputation.py` - Reputation tracking

### Phase 5: Items and Rooms

Extend world system:

- Item quirks and maker profiles
- Environmental quirks for rooms
- Player-created content support
- Item discovery and learning

**Database Changes**:
- Add `items` table with quirks
- Add `item_quirks` table
- Add `rooms` table with environmental_quirks
- Store maker_profile JSON on items

### Phase 6: Creator's Toolkit

Extend Gradio interface:

- Quirk designer
- Item forge
- Room builder
- NPC scripter
- Newspaper editor
- Content publication

**New Tabs**:
- `tabs/quirk_studio_tab.py`
- `tabs/item_forge_tab.py`
- `tabs/room_builder_tab.py`
- `tabs/content_library_tab.py`

## Key Implementation Principles

### 1. Determinism First

All game logic must be:

- **Replayable from seed**: Same seed → same outcome
- **Never call LLMs for mechanics**: LLMs only for language
- **Traceable**: Every modifier logged
- **Testable**: Reproducible test cases

### 2. Separation of Concerns

**Programmatic** (authoritative):
- Character names, attributes, quirks
- Resolution math and axis calculations
- Ledger truth
- All game state

**LLM** (non-authoritative):
- Descriptions and flavor text
- Newspaper articles
- NPC dialogue gloss
- Help text

### 3. Schema Stability

When adding new tables:

- Keep existing `players` for auth
- Add `characters` separately
- Link via `account_id`
- Preserve backward compatibility
- Migrate data carefully

### 4. Content Libraries

Store content as JSON files:

- `data/quirks.json` - Character quirks
- `data/failings.json` - Failings
- `data/useless_bits.json` - Useless specializations
- `data/item_quirks.json` - Item quirks
- `data/environmental_quirks.json` - Room quirks

**Benefits**:
- Easy to edit and extend
- No code changes for new content
- Version controllable
- Community contributions

## Testing Strategy

### Unit Tests

Test each component in isolation:

- Axis calculations (deterministic)
- Quirk modifiers (correct application)
- Ledger recording (immutable)
- Name generation (unique, weighted)

### Integration Tests

Test component interaction:

- Character issuance end-to-end
- Action resolution with multiple modifiers
- Ledger → Newspaper pipeline
- Item quirk interactions

### Replay Tests

Verify determinism:

- Same seed → same outcome
- Ledger replayability
- No hidden state
- No LLM calls in resolution

### Content Tests

Validate content libraries:

- JSON schema validation
- No duplicate IDs
- Required fields present
- Modifier ranges valid

## Code Organization

Suggested file structure for new features:

```
src/mud_server/
├── core/
│   ├── character/
│   │   ├── issuer.py       # Character generation
│   │   ├── attributes.py   # Attribute distribution
│   │   └── quirks.py       # Quirk application
│   ├── resolution/
│   │   ├── engine.py       # Axis-based resolution
│   │   ├── axes.py         # Axis definitions
│   │   └── modifiers.py    # Modifier system
│   ├── ledger/
│   │   ├── recorder.py     # Ledger writing
│   │   └── replay.py       # Replay capability
│   └── interpretation/
│       ├── newspaper.py    # Article generation
│       └── reputation.py   # Reputation tracking
├── db/
│   └── schema/
│       ├── characters.py   # Character tables
│       ├── ledger.py       # Ledger tables
│       └── items.py        # Item tables
└── content/
    ├── loader.py           # Load JSON libraries
    └── validator.py        # Validate content
```

## API Evolution

When extending the API:

- **Don't break existing endpoints**: Add new ones
- **Version if necessary**: `/api/v2/...`
- **Return both ledger and interpretation**: Let client choose
- **Document all endpoints**: Use Pydantic models
- **Test backward compatibility**: Ensure old clients work

## Migration Strategy

From proof-of-concept to full implementation:

1. **Keep current code working**: Don't break existing features
2. **Add new systems alongside**: Parallel development
3. **Feature flags**: Toggle new features on/off
4. **Gradual migration**: Move users incrementally
5. **Preserve data**: Don't lose player progress

## Further Reading

- [Code Examples](code-examples.md) - Detailed pseudo-code and schema
- [Supplementary Examples](supplementary-examples.md) - Content libraries and API examples
- [Roadmap](roadmap.md) - Timeline and priorities
- [Architecture Overview](../architecture/overview.md) - System design
- [Developer Guide](../developer/contributing.md) - How to contribute
