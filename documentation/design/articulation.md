# The Undertaking: Design Articulation

## Executive Summary

**The Undertaking** is a procedurally-generated, ledger-driven multiplayer interactive fiction system where players do not build characters—they receive them. Characters are issued as complete, immutable packages: uneven attributes, mandatory quirks, persistent failings, useless specializations, and inherited reputations. Success is not about optimisation; it is about understanding how *this specific goblin* fails, and learning to work within those constraints.

The game's core innovation is separating **resolution** (what actually happens) from **interpretation** (how it is recorded and narrated). A character fails not because of random chance, but because of who they are. That failure is then recorded in a ledger, reinterpreted by a newspaper, and becomes permanent narrative data that shapes future interactions.

This is not a traditional MMO. It is closer to a bureaucratic simulation where you are a low-level functionary trying to survive a system designed by people who were worse at maths than you are.

---

## Design Pillars

### 1. **Character Issuance, Not Creation**

Players choose only their character's sex. Everything else is generated and sealed:

- **Name**: Pulled from weighted pools of given names, family names, and optional honorifics. Names are often embarrassing, too long, or bureaucratically awkward.
- **Attributes**: Seven core stats (Cunning, Grip Strength, Patience, Spatial Sense, Stamina, Book Learning, Luck (Administrative)) distributed unevenly by design. Some goblins are naturally competent; others are not.
- **Quirks**: 2–4 mandatory traits that affect how actions resolve. Quirks are not flavour—they are mechanical modifiers that trigger conditionally.
- **Failings**: Persistent deficiencies that apply even on "success." A goblin with poor numeracy will miscalculate resources even when the task succeeds.
- **Useless Bits**: Specializations that sound helpful but rarely are. An expert in obsolete measurement systems or someone who knows every bridge by name but not where they go.
- **Starting Reputation**: Inherited bias before the player has done anything. Rumours, clerical errors, family assumptions, and guild expectations.

Once sealed, a character is immutable. Growth is additive. Failure is permanent.

### 2. **Failure as Data, Not Punishment**

The Undertaking does not punish failure—it records it.

Every meaningful action passes through three checks:

1. **Intent**: Quirks and failings bias the action before it starts.
2. **Capability**: Attributes and tools determine how the action resolves.
3. **Interpretation**: Reputation, luck, and name determine how the outcome is narrated and blamed.

The resolution system uses a **translation layer** of fixed axes:

| Axis | What It Controls |
|------|------------------|
| **Timing** | When something happens in an action |
| **Precision** | How exact an action must be |
| **Stability** | How tolerant the system is to deviation |
| **Visibility** | How observable an error is |
| **Interpretability** | How outcomes are judged |
| **Recovery Cost** | Effort to correct or undo |

Attributes do not add success—they change **how bad failure looks**. A goblin with high cunning doesn't prevent failure; they get a *different kind* of failure, one that is easier to reinterpret as someone else's problem.

### 3. **Items as Frozen Decisions**

Items are not upgrades. They are the **frozen decision-making of another goblin**.

A fishing pole carries:
- The maker's habits
- Their shortcuts
- Their grudges
- Their cleverness
- Their mistakes

Items have quirks just like characters do. A pole with "Delayed Tension Response" doesn't make you fish better—it changes *when* you detect a bite, which interacts unpredictably with your patience and the river conditions.

Two goblins using the same item fail **differently**, because the item's quirks interact with their quirks in ways that are contextual and often surprising.

### 4. **Ledger as Truth, Narrative as Interpretation**

The game maintains two layers of truth:

**The Ledger Layer** (Hard Truth):
- Deterministic, replayable from seed
- Never calls an LLM
- Records facts: what happened, which attributes were consulted, which quirks triggered, what the outcome was

**The Interpretation Layer** (Soft Truth):
- Consumes ledger facts and produces language
- May vary per context
- May contradict itself narratively
- Is disposable and can be regenerated

The newspaper pulls from the ledger but tells a story. The ledger remembers the truth. The player remembers their goblin.

Example:
- **Ledger**: "Action: fishing. Outcome: failure. Contributing factors: [failing_patience_low, item_quirk_delayed_feedback]. Interpretation: avoidable. Blame weight: high."
- **Newspaper**: "Third time this week a catch slipped from Grindlewick's pole. Locals blame impatience. Experts disagree."

### 5. **Resistance to Optimisation**

There is no "best build." There is no "best item." There is no meta.

Optimisation is resisted at every level:

- **Character variance**: Uneven attributes mean no two goblins are built the same way.
- **Hidden quirks**: Some quirks are only discovered after failure.
- **Contextual synergies**: A quirk that helps in one situation harms you in another.
- **Item discovery**: You don't know how a tool behaves until you use it repeatedly.
- **Reputation bias**: The same action is interpreted differently depending on who performs it.

The optimal player behaviour becomes: *"I know how this stupid goblin behaves."* Not: *"This is the best build."*

---

## How This Differs From Traditional Design

### Character Creation

| Aspect | Traditional MMO | The Undertaking |
|--------|-----------------|-----------------|
| **Player Agency** | Full control; design your ideal character | One choice (sex); everything else assigned |
| **Fairness** | Balanced starting conditions | Deliberately uneven; some goblins are worse |
| **Optimisation** | Rewarded; builds are theorycrafted | Resisted; builds emerge from failure history |
| **Identity** | Chosen; expresses player preference | Issued; imposes identity on player |
| **Progression** | Increases power | Increases understanding |

### Failure

| Aspect | Traditional MMO | The Undertaking |
|--------|-----------------|-----------------|
| **Consequence** | Setback; retry or avoid | Data; recorded and remembered |
| **Visibility** | Private (you know you failed) | Public (newspaper writes about it) |
| **Permanence** | Forgotten after retry | Permanent in ledger |
| **Narrative** | Mechanical | Interpreted through reputation |

### Items

| Aspect | Traditional MMO | The Undertaking |
|--------|-----------------|-----------------|
| **Function** | Numerical bonuses; clear upgrades | Quirks and hidden behaviours |
| **Optimisation** | Best-in-slot gear | No clear "best" item |
| **Discovery** | Stats visible immediately | Quirks discovered through use |
| **History** | None; items are interchangeable | Items carry maker's decisions |

---

## Core Mechanics: How JSON Becomes Play

### Character JSON as a Contract

The character JSON is not a character sheet. It is a **capability and liability contract** that answers:

1. What can this goblin attempt?
2. How likely are they to fail?
3. How is that failure interpreted by the world?
4. What gets written down later?

Every field must earn its keep by answering at least one of these questions.

### Resolution in Practice

When a goblin attempts an action:

1. **Intent Phase**: Quirks and failings bias the axes before the action starts. A goblin with "Panics When Watched" has reduced stability if an NPC is observing.

2. **Setup Phase**: Item quirks reorder which axis matters first. A pole with "Delayed Feedback" shifts the timing axis.

3. **Execution Phase**: Attributes determine the magnitude of deviation. Low patience means you act too early; low grip strength means your hands slip.

4. **Outcome Phase**: Stability determines if deviation cascades into failure.

5. **Interpretation Phase**: Reputation and luck determine how the failure is narrated. A goblin named "Grindlewick Thrum-of-Three-Keys (Acting)" gets more scrutiny than "Mib Gristlewick."

6. **Ledger Phase**: Everything is recorded with contributing factors, interpretation, and blame weight.

### Example: Fishing

**Setup**:
- Goblin: Low Patience, Moderate Cunning
- Item: Fishing pole with *Delayed Feedback*
- Environment: Fast river

**Axis Effects**:
- Timing: Skewed late (quirk + item)
- Precision: Neutral
- Stability: Reduced (low patience)
- Visibility: Medium
- Interpretability: Favourable (cunning)

**Resolution**:
- Bite detected late (delayed feedback)
- Reel too early (low patience + late detection)
- Fish escapes (stability cascade)

**Ledger**:
```json
{
  "action": "fish",
  "outcome": "failure",
  "contributing_factors": ["failing_patience", "item_quirk_delayed_feedback"],
  "interpretation": "avoidable",
  "blame_weight": "high"
}
```

**Newspaper**:
> "Third time this week a catch slipped from Grindlewick's pole. Locals blame impatience. Experts disagree."

---

## Design Philosophy: Why This Works

### Removes Optimisation Anxiety

Players cannot min-max their way to success. This removes the paralysis of character creation. You are not agonising over stat allocation; you are accepting a goblin and learning how to work with them.

### Encourages Role Acceptance

You do not ask: *"Is this build viable?"*

You ask: **"How do I survive as this goblin?"**

This shifts the player's mental model from system mastery to character understanding.

### Makes Failure Interesting

Failure is not a setback to retry. It is a story. It is data. It is part of who this goblin is.

A goblin who fails at fishing because of a delayed-feedback pole is not a failure of the game—it is a feature of the relationship between this goblin and this tool.

### Fits Perfectly With Bureaucratic Narrative

The ledger, the newspaper, the reputation system, the paperwork errors—these all reinforce a single tone: **you are a low-level functionary in a system that does not care about you.**

This is deeply Goblin.

### Creates Emergent Specialisation

Without optimisation, specialisation emerges from failure history. A goblin who fails repeatedly at fishing but succeeds at salvage becomes *the salvage goblin*, not because they were built that way, but because that is what happened.

---

## Technical Implementation: Ledger + Interpretation

### The Two-Layer Model

**Layer 1: The Ledger Layer (Hard Truth)**
- Deterministic, replayable from seed
- Never calls an LLM
- Records facts: character_id, action, outcome, contributing_factors, interpretation, blame_weight
- Source of authority for all game logic

**Layer 2: The Interpretation Layer (Soft Truth)**
- Consumes ledger facts
- Produces language: descriptions, explanations, newspaper copy
- May vary per context
- May contradict itself narratively (intentionally)
- Is disposable and can be regenerated

### Hybrid Generation Model

**Programmatic Systems Are Authoritative For**:
- Names (structure, uniqueness, cadence)
- Stats & distributions
- Quirks, failings, useless bits (IDs, triggers, effects)
- Items, item quirks, provenance
- Resolution math
- Ledger truth

**LLMs Are Non-Authoritative and Used Only For**:
- Descriptions
- Explanations
- Tone
- In-world paperwork language
- Newspaper copy
- NPC dialogue gloss
- "Tell the truth without lying" summaries

This separation prevents hallucinated mechanics, balance drift, and schema corruption.

---

## What The Undertaking Is Not

- **Not a roguelike**: Characters are not rerolled; they are issued once and persist.
- **Not a traditional MMO**: There is no character creation screen with sliders.
- **Not a narrative game**: The story emerges from simulation, not authored scenes.
- **Not a pure simulation**: Interpretation is a game mechanic, not just an output.
- **Not fair**: Fairness is not a design goal. Specificity is.

---

## What The Undertaking Is

A **procedural accountability system** where:
- Characters are issued, not built
- Failure is recorded as data
- Interpretation is a game mechanic
- Optimisation is resisted
- Ledgers are truth
- Newspapers are stories
- Goblins are specific, flawed, and yours

It is a game about learning to survive as yourself, not about becoming powerful.
