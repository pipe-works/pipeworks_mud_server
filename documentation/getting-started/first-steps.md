# First Steps

Your first actions in The Undertaking.

## Logging In

### Create an Account

1. Navigate to http://localhost:7860
2. Click the **Register** tab
3. Enter a username (2-20 characters)
4. Enter a password (minimum 8 characters)
5. Confirm your password
6. Click **Register**

### Log In

1. Go to the **Login** tab
2. Enter your username
3. Enter your password
4. Click **Login**

You'll be redirected to the **Game** tab.

## Understanding the Interface

The game interface has several sections:

### Status Panel

Shows your current information:

- **Username**: Your character name
- **Current Room**: Where you are
- **Online Players**: Who's online

### Game Display

The main text area showing:

- Room descriptions
- Action results
- Chat messages
- System notifications

### Command Input

Two ways to send commands:

1. **Text Input**: Type commands and press Enter
2. **Quick Buttons**: Click directional arrows or action buttons

### Chat Area

At the bottom:

- **Chat History**: Recent messages from your room
- **Say Input**: Type messages and click "Send" to chat

## Your First Room

When you log in, you start in the **Spawn** room (central hub).

### Look Around

Click the **Look** button or type `look` to examine the room:

```
You are at Spawn
A central meeting place with paths leading in all directions.

Items here: wooden_sword, healing_potion

Players here: (none)

Exits: north (forest), south (desert), east (mountain), west (lake)
```

### Understanding Room Descriptions

- **Room Name**: Where you are
- **Description**: What the room looks like
- **Items**: Objects you can pick up
- **Players**: Other players in the room
- **Exits**: Directions you can move

## Moving Around

### Use Directional Commands

Click the arrow buttons or type:

- `north` or `n` - Go north
- `south` or `s` - Go south
- `east` or `e` - Go east
- `west` or `w` - Go west

Example:

```
> north
You moved to forest

You are at Forest
Dense trees surround you. The path continues north and south.

Items here: rope, wooden_bow

Players here: alice, bob

Exits: south (spawn)
```

### The World Map

```
        [Forest]
            |
[Lake] - [Spawn] - [Mountain]
            |
        [Desert]
```

Explore each room to discover items and meet other players!

## Picking Up Items

### Get Command

Use `get <item>` to pick up items:

```
> get wooden_sword
You picked up wooden_sword
```

### Check Your Inventory

Click **Inventory** or type `inventory`:

```
You are carrying: wooden_sword
```

### Drop Items

Use `drop <item>` to drop items:

```
> drop wooden_sword
You dropped wooden_sword
```

!!! note "Item Behavior"
    In the current proof-of-concept:

    - Items remain in rooms after you pick them up
    - Multiple players can pick up the same item
    - This behavior may change in future versions

## Chatting with Others

### Send a Message

Two ways to chat:

1. **Quick Chat**: Type in the chat input at bottom and click "Send"
2. **Say Command**: Type `say Hello!` in the command input

Example:

```
> say Hello, everyone!
You say: Hello, everyone!
```

### View Chat History

Chat messages appear in:

1. The main game display
2. The chat history panel (bottom right)

!!! tip "Room-Based Chat"
    You only see messages from players in your current room.

## Who's Online

Use the `who` command to see all connected players:

```
> who
Online players: alice, bob, charlie, you
```

## Getting Help

### In-Game Help

Type `help` to see available commands:

```
> help
Available commands:
- north/south/east/west: Move in a direction
- look: Examine your surroundings
- inventory: Check your items
- get <item>: Pick up an item
- drop <item>: Drop an item
- say <message>: Chat with others
- who: List online players
- help: Show this message
```

### Documentation

- Click the **Help** tab in the interface
- Visit the [Commands Reference](../guide/commands.md)
- Read the [User Guide](../guide/playing.md)

## Common Commands Summary

| Command | Shortcut | Description |
|---------|----------|-------------|
| `north` | `n` | Move north |
| `south` | `s` | Move south |
| `east` | `e` | Move east |
| `west` | `w` | Move west |
| `look` | - | Examine room |
| `inventory` | `i` | Check items |
| `get <item>` | - | Pick up item |
| `drop <item>` | - | Drop item |
| `say <message>` | - | Chat |
| `who` | - | List players |
| `help` | `?` | Show help |

## Tips for New Players

### 1. Explore Thoroughly

Visit all rooms to discover:

- Different items
- Unique room descriptions
- Other players

### 2. Use the Quick Buttons

The arrow buttons and action buttons are faster than typing.

### 3. Check Your Status

Click **Inventory** regularly to track what you're carrying.

### 4. Communicate

Use chat to:

- Greet other players
- Ask questions
- Coordinate actions

### 5. Read Room Descriptions

Pay attention to:

- Available exits
- Items in the room
- Other players present

## Multi-Player Testing

Want to test multi-player features by yourself?

1. Open multiple browser windows or tabs
2. Log in with different usernames in each
3. Move characters to the same room
4. Test chatting between them

## What's Next?

Now that you know the basics:

- **Learn More Commands**: [Commands Reference](../guide/commands.md)
- **Understand the Design**: [Design Vision](../design/articulation.md)
- **Explore the World**: Visit all rooms and collect items
- **Meet Players**: Chat with others and explore together

## Current Limitations

This is a proof-of-concept. Some features are not yet implemented:

- ❌ Character issuance (quirks, failings, attributes)
- ❌ Axis-based action resolution
- ❌ Ledger and newspaper system
- ❌ Item quirks and maker profiles
- ❌ Reputation system

See the [Implementation Roadmap](../implementation/roadmap.md) for planned features.

---

Enjoy exploring The Undertaking!
