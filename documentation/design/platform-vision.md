# The Undertaking: A Creative Platform for Procedural World-Building

## 1. The Manifesto: The Magic of Tinkering

Modern games have changed. They are often polished, closed systems designed for consumption. But there was a magic to old-school games—a magic born from tinkering. They gave you tools, not just rules. They invited you to break things, to build things, and to make the world your own.

**The Undertaking** is a return to that magic. It is not a game you play; it is a platform you inhabit, shape, and extend. It is built on a simple but profound premise: **the best games are the ones that give players the same tools the developers used to create the world.**

You begin as a cog in a bureaucratic machine, an issued goblin with flaws you cannot hide. But as you learn the system, you earn the right to change it. You graduate from functionary to creator. You are not just surviving in the world; you are building it.

This is a game for the curious, the creative, and the ones who miss the joy of lifting the hood and making the engine their own.

---

## 2. The Two Pillars: Engine and Toolkit

The Undertaking is built on two core components, each validated by its own proof-of-concept:

| Pillar | Proof-of-Concept | Purpose |
| :--- | :--- | :--- |
| **The Undertaking Engine** | MUD Server (FastAPI + Gradio) | The core simulation: character issuance, axis-based resolution, and the ledger/narrative system. It creates the world and its rules. |
| **The Creator's Toolkit** | Chat Translator (LLM + WebSockets) | The extensibility layer: tools that allow players to create their own content, from in-character speech to new rooms, items, and NPCs. |

These are not separate systems. They are two halves of a single vision. The Engine provides the **framework**, and the Toolkit provides the **freedom**.

---

## 3. Pillar One: The Undertaking Engine

This is the heart of the simulation, the bureaucratic machine that governs the world. Its design is based on the principles of procedural generation, systemic failure, and narrative interpretation.

### Character Issuance, Not Creation

Players are not given a character sheet; they are handed a personnel file. You choose a sex, and the system issues you a complete, unchangeable goblin identity:

- **Uneven Attributes**: Some goblins are smart. Some are strong. Most are mediocre. None are balanced.
- **Mandatory Quirks**: Mechanical traits that affect how you interact with the world.
- **Persistent Failings**: Inherent flaws that never go away.
- **Useless Specializations**: Things you are good at that are rarely helpful.
- **Inherited Reputation**: What the world thinks of you before you’ve done anything.

### Axis-Based Resolution

Actions are not resolved with a single dice roll. They are interpreted through a series of axes (Timing, Precision, Stability, etc.). Your attributes and quirks don’t determine success; they determine **how you fail**. High cunning doesn’t prevent failure—it lets you blame someone else.

### The Ledger and the Newspaper

Every action is recorded in two places:

- **The Ledger (Hard Truth)**: An immutable, deterministic record of what actually happened.
- **The Newspaper (Soft Truth)**: A biased, narrative interpretation of the event, influenced by reputation and luck.

Failure is not a punishment; it is **data** that feeds the narrative engine of the world.

---

## 4. Pillar Two: The Creator's Toolkit

This is where The Undertaking transcends from a game to a platform. The Creator's Toolkit gives players the power to extend the world.

### The Chat Translator: A Case Study in Player Creation

Your second proof-of-concept, the LLM-powered chat translator, is the perfect example of this pillar. It is not a feature; it is a **player-facing tool**. A player can:

1.  **Use It**: Translate their chat into the voice of an angry, devious, or whimsical goblin.
2.  **Modify It**: Tweak the prompts to create a new personality.
3.  **Create with It**: Build an NPC that uses a custom-designed personality filter.
4.  **Share It**: Give their new tool to other players.

This demonstrates the core loop of the Creator's Toolkit: **Use, Modify, Create, Share**.

### The Gradio Authoring Environment

The MUD server’s Gradio interface is not just a developer tool; it is the **foundation of the Creator's Toolkit**. It can be extended to provide a visual, interactive environment for players to build their own content:

-   **Quirk Studio**: Design new quirks and test their mechanical effects.
-   **Item Forge**: Create items with unique properties and histories.
-   **Room Builder**: Design new rooms and link them to the existing world.
-   **NPC Scripter**: Write dialogue and behavior for custom NPCs using the chat translator framework.
-   **Newspaper Editor**: Write and publish your own interpretations of world events.

Players are not just living in the world; they are actively participating in its creation.

---

## 5. The Player's Journey: From Functionary to Creator

The long-term progression arc of The Undertaking is not about gaining power; it is about gaining **agency**. The player’s journey has three stages:

### Stage 1: The Functionary (Survive)

As a new player, you are an issued goblin. Your goal is to survive. You learn the systems, you discover your flaws, and you figure out how to work within your constraints. You are a cog in the machine.

### Stage 2: The Tinkerer (Understand)

As you gain experience, you unlock access to the Creator's Toolkit. You start to tinker. You modify your chat filter. You build a custom item. You write a story for the newspaper. You are learning to lift the hood.

### Stage 3: The Creator (Build)

At the highest level, you are a world-builder. You can create new rooms, design complex NPCs, and introduce new mechanics. You are no longer just a player; you are a developer, using the same tools that built the world to extend it. Your creations become part of the game for other players to experience.

---

## 6. The Unified Architecture

The two proof-of-concepts are not separate ideas; they are a single, cohesive architecture.

```
+----------------------------------------------------+
|                   Player Interface                   |
|           (Web Client, Terminal, etc.)             |
+-------------------------+--------------------------+
                          |                          
                          | HTTP/WebSockets
                          |                          
+-------------------------v--------------------------+
|                 API Gateway (FastAPI)                |
| (Handles all incoming player requests)             |
+-------------------------+--------------------------+
                          |                          
        +-----------------+-----------------+        
        |                                 |
+-------v----------+             +----------v-------+
| The Undertaking  |             | The Creator's    |
|      Engine      |             |     Toolkit      |
| (Game Simulation)  |             | (Content Tools)  |
+------------------+             +------------------+
| - Character Gen  |             | - Gradio Authoring |
| - Resolution     |             | - LLM Integration  |
| - Ledger/Narrative |             | - Player Scripting |
+------------------+             +------------------+
        |                                 |
        | (Reads/Writes)                  | (Reads/Writes)
        +-----------------+-----------------+
                          |
+-------------------------v--------------------------+
|                Persistence Layer (SQLite)            |
| (Ledger, World Data, Player Content, Accounts)     |
+----------------------------------------------------+
```

-   The **Engine** runs the core simulation.
-   The **Toolkit** allows players to add new content and logic to the simulation.
-   The **Persistence Layer** stores both the core game data and the player-created content, blurring the line between the two.

## 7. Conclusion: A Game That Grows With Its Players

The Undertaking is more than a game about failure; it is a platform for creativity. By giving players the tools to build, you are creating a world that can grow and evolve in unexpected ways. You are capturing the magic of old-school games—the magic of tinkering—and bringing it to a new generation of players.

This is not a niche game. It is a **foundational game**—one that can inspire a community of creators who will build things you never imagined.
