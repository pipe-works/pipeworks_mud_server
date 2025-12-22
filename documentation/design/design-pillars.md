# Design Pillars

Quick reference to the five core design principles of The Undertaking.

## 1. Character Issuance, Not Creation

**Players receive characters, they don't build them.**

- Choose **only sex**—everything else is generated and sealed
- **Immutable once sealed**—no respeccing, no optimization
- **Deliberately uneven**—some goblins are naturally better
- **Quirks** (2-4 mandatory)—mechanical traits affecting resolution
- **Failings**—persistent deficiencies, even on success
- **Useless bits**—specializations that rarely help
- **Inherited reputation**—bias before you've done anything

### Why This Matters

- Prevents optimization and meta-gaming
- Creates unique, memorable characters
- Forces players to work within constraints
- No "best build"—every goblin is different

## 2. Failure as Data, Not Punishment

**Actions resolve through six axes, not dice rolls.**

| Axis | What It Controls |
|------|------------------|
| **Timing** | When something happens in an action |
| **Precision** | How exact an action must be |
| **Stability** | How tolerant the system is to deviation |
| **Visibility** | How observable an error is |
| **Interpretability** | How outcomes are judged |
| **Recovery Cost** | Effort to correct or undo |

### How It Works

1. **Quirks and failings** bias axes before action starts
2. **Item quirks** modify which axes matter most
3. **Environmental quirks** (room properties) further modify
4. **Deterministic deviations** calculated (seeded for replay)
5. **Outcome determined**: success, partial, or failure
6. **Contributing factors** recorded in ledger

### Why This Matters

- Failure has **context** and **cause**, not randomness
- Attributes don't add success—they change **how bad failure looks**
- High cunning doesn't prevent failure—it lets you **blame someone else**
- All failures are **trackable** and **explainable**

## 3. Items as Frozen Decisions

**Items carry the maker's habits, shortcuts, grudges, and mistakes.**

- **Maker profile**: Item stores creator's attributes and quirks
- **Item quirks**: Mechanical properties that interact with character quirks
- **Context-dependent**: Same item fails differently for different goblins
- **No "best" items**: A quirk that helps one goblin hurts another

### Example

A fishing pole made by a goblin with **low patience**:

- **Loose reel** (made in a hurry)
- **Delayed feedback** (attempt to compensate for impatience)

When you use it:

- **Patient goblin**: Delayed feedback helps—you wait anyway
- **Impatient goblin**: Delayed feedback hurts—makes you jerk the line too early

### Why This Matters

- Items aren't upgrades—they're **someone else's solutions**
- Using an item means using **their quirks**, not yours
- Creates **contextual value**: no universal "best"
- Encourages **understanding**, not optimization

## 4. Ledger as Truth, Newspaper as Interpretation

**Hard truth (ledger) is separated from soft truth (newspaper).**

### The Ledger (Hard Truth)

- **Deterministic**: Replayable from seed
- **Never calls LLM**: Pure programmatic logic
- **Records facts**: What happened, which quirks triggered, who's blamed
- **Immutable**: Once written, never changes
- **Source of authority**: All game logic derives from this

### The Newspaper (Soft Truth)

- **Consumes ledger facts**: Reads from hard truth
- **Produces language**: Interprets facts as narrative
- **May vary by context**: Same facts, different stories
- **May contradict itself**: Narratively, not mechanically
- **Disposable**: Can be regenerated without affecting game state

### Example

**Ledger**:
```
Action: fishing
Outcome: failure
Contributing factors: [failing_patience_low, item_quirk_delayed_feedback]
Interpretation: avoidable
Blame weight: 0.8
```

**Newspaper**:
```
"Third time this week a catch slipped from Grindlewick's pole.
Locals blame impatience. Experts disagree."
```

### Why This Matters

- **Determinism** for game logic (never hallucinate mechanics)
- **Creativity** for narrative (use LLMs for language)
- **Replayability**: Same ledger → same mechanics
- **Variety**: Same ledger → different stories

## 5. Resistance to Optimization

**No "best builds," no meta-gaming, no min-maxing.**

### How Optimization Is Resisted

| System | Resistance Mechanism |
|--------|---------------------|
| **Characters** | Uneven attributes, hidden quirks, immutable |
| **Items** | Contextual synergies, maker quirks, discovery-based |
| **Actions** | Multi-axis resolution, quirk interactions |
| **Reputation** | Same action interpreted differently per character |
| **Growth** | Additive, not replaceable; failure is permanent |

### Hidden Quirks

Some quirks are only discovered through **failure**:

- Not shown on character sheet initially
- Revealed when triggered in-game
- Recorded in player notes/journal
- Part of learning "your goblin"

### Contextual Synergies

A quirk that **helps** in one situation **harms** in another:

- "Panics When Watched" → Good for stealth, bad for performance
- "Overcompensates for Errors" → Good for precision, bad for timing
- "Delayed Feedback Tolerance" → Good with patient tasks, bad with urgent ones

### Why This Matters

- **Optimal behavior**: *"I know how this stupid goblin behaves"*
- **Not**: *"This is the best build"*
- Forces **understanding** over **optimization**
- Creates **unique** player experiences
- Prevents **commodification** of content

## Summary Table

| Pillar | Core Idea | Player Impact |
|--------|-----------|---------------|
| **Character Issuance** | You get what you get | Learn your goblin's flaws |
| **Failure as Data** | Six axes, not dice | Understand why you failed |
| **Items as Frozen Decisions** | Maker's quirks embedded | Find what works for you |
| **Ledger vs. Newspaper** | Hard truth vs. soft truth | Trust mechanics, enjoy stories |
| **Resistance to Optimization** | No best builds | Explore, don't optimize |

## The Undertaking Philosophy

> "The Undertaking is not about finding the perfect build.
> It's about understanding your deeply flawed goblin
> and learning to work within their limitations."

## Implementation Status

These pillars are **designed** but most features are **not yet implemented** in the current proof-of-concept.

See the [Implementation Roadmap](../implementation/roadmap.md) for:

- What's currently working
- What's planned
- Implementation priorities

## Further Reading

- [Core Articulation](articulation.md) - Full design document with examples
- [Platform Vision](platform-vision.md) - Engine + Toolkit unified vision
- [Code Examples](../implementation/code-examples.md) - How it works in code
- [Supplementary Examples](../implementation/supplementary-examples.md) - Content libraries

---

These five pillars guide every design decision in The Undertaking.
