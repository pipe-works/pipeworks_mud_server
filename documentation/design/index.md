# Design Vision

The Undertaking challenges conventional game design through five core principles that resist optimization, embrace failure as data, and invite players to become creators.

## Overview

This section explores the philosophy, design pillars, and vision behind The Undertaking. Unlike traditional MMOs where players optimize characters through grinding and meta-gaming, The Undertaking is a **procedural accountability system** where:

- Characters are **issued**, not built
- Failure is **recorded** as data, not punished
- Truth has two layers: **ledger** (deterministic) and **newspaper** (interpretation)
- Items carry the **frozen decisions** of their makers
- **Optimization is resisted** at every level

## Core Documents

<div class="grid cards" markdown>

-   :material-file-document:{ .lg .middle } __Core Articulation__

    ---

    The foundational design document explaining all five design pillars with worked examples

    [:octicons-arrow-right-24: Read Articulation](articulation.md)

-   :material-tools:{ .lg .middle } __Platform Vision__

    ---

    The unified vision of Engine + Toolkit: how players journey from functionary to creator

    [:octicons-arrow-right-24: Platform Vision](platform-vision.md)

-   :material-pillar:{ .lg .middle } __Design Pillars__

    ---

    Quick reference to the five core design principles

    [:octicons-arrow-right-24: Design Pillars](design-pillars.md)

</div>

## The Five Design Pillars

### 1. Character Issuance, Not Creation

Players don't build characters—they **receive** them. Each goblin is issued as a complete, immutable package:

- **Uneven attributes**: Some goblins are naturally better at certain things
- **Mandatory quirks** (2-4): Mechanical traits affecting resolution
- **Persistent failings**: Deficiencies that apply even on success
- **Useless specializations**: Rare expertise that rarely helps
- **Inherited reputation**: Bias before you've done anything

Once sealed, a character is **immutable**. No respeccing. No optimization.

### 2. Failure as Data, Not Punishment

Actions resolve through **six axes**, not dice rolls:

- **Timing**: When something happens in an action
- **Precision**: How exact an action must be
- **Stability**: How tolerant the system is to deviation
- **Visibility**: How observable an error is
- **Interpretability**: How outcomes are judged
- **Recovery Cost**: Effort to correct or undo

Attributes don't add success—they change **how bad failure looks**. High cunning doesn't prevent failure; it lets you blame someone else.

### 3. Items as Frozen Decisions

Items aren't upgrades—they're the **frozen decision-making of another goblin**:

- Carry the maker's habits, shortcuts, grudges
- Have quirks that interact with character quirks
- Fail differently for different characters
- No "best" items—context determines usefulness

### 4. Ledger as Truth, Newspaper as Interpretation

Two layers of truth:

**The Ledger (Hard Truth)**:
- Deterministic, replayable from seed
- Never calls an LLM
- Records what happened, which quirks triggered, who's to blame

**The Newspaper (Soft Truth)**:
- Consumes ledger facts, produces narrative
- May vary by context and contradict itself
- Disposable, can be regenerated
- Tells stories about the same facts

### 5. Resistance to Optimization

No meta-gaming:

- **Character variance**: Uneven attributes, hidden quirks
- **Contextual synergies**: Quirks help in one situation, harm in another
- **Item discovery**: Unknown behavior until used repeatedly
- **Reputation bias**: Same action interpreted differently per character

The optimal behavior: *"I know how this stupid goblin behaves"* not *"This is the best build."*

## Design Philosophy

### The Magic of Tinkering

The Undertaking invites players to:

1. **Understand the system**: Learn how mechanics actually work
2. **Experiment with boundaries**: Push against constraints
3. **Create within constraints**: Build content using the same tools as developers

### From Functionary to Creator

Players progress through three stages:

1. **Functionary**: Survive in a system you don't control
2. **Tinkerer**: Understand why things fail and how to work around them
3. **Creator**: Use the Creator's Toolkit to build new content

### Why This Matters

Traditional games hide their mechanics and discourage tinkering. The Undertaking:

- Makes mechanics **transparent** and **deterministic**
- Separates **logic** (programmatic) from **language** (LLM)
- Invites players to **modify, extend, and create**
- Resists **commodification** and **optimization**

## Key Concepts

### Character System

- **Seven attributes**: Cunning, Grip Strength, Patience, Spatial Sense, Stamina, Book Learning, Luck (Administrative)
- **Quirks**: Mechanical modifiers with conditional triggers
- **Failings**: Always active, even on success
- **Useless bits**: Rarely helpful specializations
- **Name structure**: Given name + family name + optional honorific

### Resolution Engine

- **Six axes** determine how actions fail
- **Quirk modifiers** bias axes before action starts
- **Item quirks** interact with character quirks
- **Environmental quirks** (room properties) further modify
- **Deterministic deviations** calculated from seed
- **Contributing factors** recorded in ledger

### Ledger System

- **Immutable action records**: What happened, why, who's responsible
- **Blame attribution**: Weight of responsibility
- **Replay capability**: Deterministic from seed
- **Source of truth**: Authority for all game logic

### Interpretation Layer

- **Newspaper articles**: Narrative interpretation of ledger facts
- **Reputation effects**: Same action told differently per character
- **Context variation**: Multiple valid interpretations
- **Regeneratable**: Can produce new narratives from same facts

## Implementation Status

The current codebase is a **proof-of-concept** validating the technical architecture. Most design features are planned but not yet implemented.

See the [Implementation Roadmap](../implementation/roadmap.md) for details on:

- What's currently implemented
- What's designed but not built
- Implementation phases and priorities

## Further Reading

- [Core Articulation](articulation.md) - Full design document with worked examples
- [Platform Vision](platform-vision.md) - Engine + Toolkit unified vision
- [Code Examples](../implementation/code-examples.md) - Pseudo-code and database schema
- [Supplementary Examples](../implementation/supplementary-examples.md) - Content libraries and API examples

## Design Inspirations

The Undertaking draws inspiration from:

- **Bureaucratic systems**: Where accountability matters more than efficiency
- **Dwarf Fortress**: Emergent storytelling from mechanical systems
- **Roguelikes**: Procedural generation and permanent consequences
- **Old-school MUDs**: Player creativity and world-building
- **Interactive fiction**: Narrative emerging from constraint

---

The Undertaking is not about optimization—it's about **understanding your goblin** and **working within their limitations**.
