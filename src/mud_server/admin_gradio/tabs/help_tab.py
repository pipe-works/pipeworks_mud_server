"""
Help Tab for MUD Client.

This module provides the Help tab with game instructions and command reference.
This tab is visible only when logged in and contains static documentation.
"""

import gradio as gr


def create():
    """
    Create the Help tab with game instructions.

    Returns:
        gr.Tab: Configured Help tab component
    """
    with gr.Tab("Help", visible=False) as help_tab:
        gr.Markdown("""
# MUD Client Help

## Getting Started
1. Enter your username in the Login tab
2. Click Login to create an account or log in
3. Navigate to the Game tab to start playing

## Commands
All commands can use the `/` prefix (e.g., `/look`) but it's optional.

### Movement
- `/north`, `/n` - Move north
- `/south`, `/s` - Move south
- `/east`, `/e` - Move east
- `/west`, `/w` - Move west

### Actions
- `/look`, `/l` - View your current location
- `/inventory`, `/inv`, `/i` - Check your items
- `/get <item>`, `/take <item>` - Pick up an item (e.g., `/get torch`)
- `/drop <item>` - Drop an item from your inventory

### Communication
- `/say <message>` - Send a message to players in your current room
- `/yell <message>` - Yell to current room and adjoining rooms
- `/whisper <player> <message>` - Send private message (only you and target see it)

### Other
- `/who` - See who else is online
- `/help`, `/?` - Display help information

## World
The world consists of a central spawn zone with 4 cardinal directions:
- **North**: Enchanted Forest
- **South**: Golden Desert
- **East**: Snow-Capped Mountain
- **West**: Crystalline Lake

Each zone contains items you can collect.

## Tips
- The game auto-refreshes every 3 seconds
- Chat messages are visible to all players in the same room
- Yells can be heard from any room
- You can pick up items and carry them in your inventory
            """)

    return help_tab
