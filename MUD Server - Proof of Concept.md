# MUD Server - Proof of Concept

A simple Multi-User Dungeon (MUD) server built with Python, FastAPI backend, Gradio frontend, and SQLite database. This is a proof-of-concept implementation designed to demonstrate core MUD functionality with multi-user support, basic chat, and world exploration.

## Features

- **Multi-User Support**: Multiple players can connect simultaneously and interact in the same world
- **Persistent World**: SQLite database stores player data, inventory, and chat history
- **JSON-Based World Data**: Easy-to-modify world structure with rooms, items, and exits
- **Web-Based Client**: Gradio frontend provides an intuitive browser-based interface
- **Basic Chat System**: Players can communicate with others in the same room
- **Inventory System**: Pick up and drop items from the world
- **Cardinal Navigation**: Move north, south, east, and west between zones

## Project Structure

```
mud_project/
├── server.py              # FastAPI backend server
├── client.py              # Gradio frontend client
├── mud_engine.py          # Game logic and world management
├── database.py            # SQLite database management
├── world_data.json        # World definition (rooms, items, exits)
├── mud.db                 # SQLite database (created on first run)
├── venv/                  # Python virtual environment
├── run.sh                 # Startup script for both services
└── README.md              # This file
```

## Installation

### Prerequisites

- Python 3.11+ (Python 3.12 recommended)
- pip package manager
- ~500MB disk space for dependencies

### Setup

1. **Create and activate virtual environment**:
   ```bash
   cd /home/ubuntu/mud_project
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install gradio fastapi uvicorn python-socketio python-multipart aiosqlite requests
   ```

3. **Initialize database**:
   ```bash
   python3 database.py
   ```

## Running the Application

### Option 1: Using the startup script (Recommended)

```bash
cd /home/ubuntu/mud_project
chmod +x run.sh
./run.sh
```

This will start both the server and client, with logs saved to `logs/` directory.

### Option 2: Manual startup

**Terminal 1 - Start the server**:
```bash
cd /home/ubuntu/mud_project
source venv/bin/activate
export MUD_HOST="0.0.0.0"
export MUD_PORT=8000
python3 server.py
```

**Terminal 2 - Start the client**:
```bash
cd /home/ubuntu/mud_project
source venv/bin/activate
export MUD_SERVER_URL="http://localhost:8000"
python3 client.py
```

## Accessing the Application

### Local Access

- **Client (Web Interface)**: http://localhost:7860
- **Server (API)**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

### Network Access

To access from another machine on your internal network:

1. Find your machine's IP address:
   ```bash
   hostname -I
   ```

2. Access from another machine:
   - **Client**: http://<your-ip>:7860
   - **Server API**: http://<your-ip>:8000

## Game Commands

### Movement
- `north` or `n` - Move north
- `south` or `s` - Move south
- `east` or `e` - Move east
- `west` or `w` - Move west

### Exploration
- `look` - Examine current room
- `who` - List active players
- `help` - Display help information

### Inventory
- `inventory` or `inv` - View your items
- `get <item>` or `take <item>` - Pick up an item
- `drop <item>` - Drop an item from inventory

### Communication
- `say <message>` or `chat <message>` - Send a message to the room

## World Map

The world consists of a central spawn zone with 4 cardinal exits:

```
                    [Enchanted Forest]
                            |
                          North
                            |
[Crystalline Lake] - West - [Spawn Zone] - East - [Snow-Capped Mountain]
                            |
                          South
                            |
                      [Golden Desert]
```

### Locations

- **Spawn Zone**: Starting location with basic items (torch, rope)
- **Enchanted Forest** (North): Glowing mushrooms and forest berries
- **Golden Desert** (South): Sand bottles and cactus flowers
- **Snow-Capped Mountain** (East): Ice crystals and mountain stones
- **Crystalline Lake** (West): Water lilies and pearls

## API Endpoints

### Authentication
- `POST /login` - Create account or login
  ```json
  {"username": "player_name"}
  ```

- `POST /logout` - Logout
  ```json
  {"session_id": "uuid", "command": "logout"}
  ```

### Game Commands
- `POST /command` - Execute a game command
  ```json
  {"session_id": "uuid", "command": "north"}
  ```

### Information
- `GET /chat/{session_id}` - Get room chat history
- `GET /status/{session_id}` - Get player status
- `GET /health` - Server health check

## Database Schema

### Players Table
- `id`: Auto-incrementing primary key
- `username`: Unique username
- `current_room`: Current room ID
- `inventory`: JSON array of item IDs
- `created_at`: Account creation timestamp
- `last_login`: Last login timestamp

### Chat Messages Table
- `id`: Auto-incrementing primary key
- `username`: Message author
- `message`: Message content
- `room`: Room ID where message was sent
- `timestamp`: Message timestamp

### Sessions Table
- `id`: Auto-incrementing primary key
- `username`: Unique username
- `session_id`: Unique session identifier
- `connected_at`: Connection timestamp
- `last_activity`: Last activity timestamp

## Customization

### Adding New Rooms

Edit `world_data.json` to add new rooms:

```json
{
  "rooms": {
    "new_room": {
      "id": "new_room",
      "name": "Room Name",
      "description": "Room description here",
      "exits": {
        "north": "spawn",
        "south": "another_room"
      },
      "items": ["item_id_1", "item_id_2"]
    }
  }
}
```

### Adding New Items

Add items to the items section in `world_data.json`:

```json
{
  "items": {
    "new_item": {
      "id": "new_item",
      "name": "Item Display Name",
      "description": "Item description"
    }
  }
}
```

## Troubleshooting

### Port Already in Use

If port 8000 or 7860 is already in use:

```bash
# Find process using port
lsof -i :8000
lsof -i :7860

# Kill the process
kill -9 <PID>

# Or change ports in environment variables
export MUD_PORT=8001
export MUD_SERVER_URL="http://localhost:8001"
```

### Database Locked

If you get a "database is locked" error, ensure only one instance of the server is running:

```bash
ps aux | grep python3
# Kill any duplicate server processes
```

### Connection Refused

If the client cannot connect to the server:

1. Ensure the server is running: `curl http://localhost:8000/health`
2. Check the `MUD_SERVER_URL` environment variable
3. Verify firewall settings allow connections on ports 8000 and 7860

## Performance Notes

- This is a proof-of-concept implementation
- SQLite is suitable for small to medium player counts (~50-100 concurrent players)
- For larger deployments, consider migrating to PostgreSQL
- Chat history is limited to 50 messages per room by default

## Future Enhancements

Potential features for future development:

- Combat system with NPCs
- Experience and leveling system
- More complex inventory with equipment slots
- Persistent player homes/housing
- Quest system
- Real-time notifications with WebSockets
- Admin commands and moderation tools
- Mobile app client
- Database migration to PostgreSQL
- Clustering for horizontal scaling

## License

This is a proof-of-concept project created for educational purposes.

## Support

For issues or questions:

1. Check the logs in the `logs/` directory
2. Verify all dependencies are installed
3. Ensure database is initialized with `python3 database.py`
4. Check that ports 8000 and 7860 are available

## Example Gameplay Session

1. Open http://localhost:7860 in your browser
2. Enter a username (e.g., "adventurer")
3. Click "Login"
4. Click "Look" to see your current location
5. Click "North" to move to the Enchanted Forest
6. Type "get mushroom" in the command field and click "Execute"
7. Click "Inventory" to verify you have the mushroom
8. Click "South" to return to spawn
9. Type "say Hello!" to chat with other players in the room
10. Click "Who" to see other active players

Enjoy your MUD adventure!
