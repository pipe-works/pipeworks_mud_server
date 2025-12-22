# Quick Start Guide

Get The Undertaking running in 30 seconds.

## Prerequisites

- Python 3.12+
- pip
- Git

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/pipeworks_mud_server.git
cd pipeworks_mud_server
```

### 2. Set Up Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Initialize Database

```bash
PYTHONPATH=src python3 -m mud_server.db.database
```

!!! warning "Default Credentials"
    A default superuser is created with:

    - **Username**: `admin`
    - **Password**: `admin123`

    **Change this password immediately after first login!**

### 5. Start the Server

```bash
./run.sh
```

The script starts both services:

- **FastAPI Server**: http://localhost:8000
- **Gradio Client**: http://localhost:7860

!!! tip "Stopping the Server"
    Press `Ctrl+C` in the terminal to stop both services.

## Access the Game

1. Open your web browser
2. Navigate to http://localhost:7860
3. Log in or register a new account
4. Start exploring!

## First Commands

Try these commands to get started:

| Command | Description |
|---------|-------------|
| `look` | Examine your current room |
| `north`, `south`, `east`, `west` | Move between rooms |
| `inventory` | Check what you're carrying |
| `get <item>` | Pick up an item |
| `say Hello!` | Chat with other players |
| `who` | See who's online |

## World Map

The default world has a simple layout:

```
        [Forest]
            |
[Lake] - [Spawn] - [Mountain]
            |
        [Desert]
```

You start in the **Spawn** room (central hub).

## Network Access

To allow other computers on your network to connect:

### Find Your IP Address

```bash
# Linux/Mac
hostname -I

# Windows
ipconfig
```

### Update the URLs

Replace `localhost` with your IP address:

- Client: `http://192.168.1.100:7860`
- Server: `http://192.168.1.100:8000`

### Configure Firewall

Make sure ports 8000 and 7860 are open in your firewall.

## Environment Variables

Customize the server configuration:

```bash
# Server host (default: 0.0.0.0)
export MUD_HOST="0.0.0.0"

# Server port (default: 8000)
export MUD_PORT=8000

# Server URL for client (default: http://localhost:8000)
export MUD_SERVER_URL="http://localhost:8000"
```

## Troubleshooting

### Can't Connect to Server?

Check if the server is running:

```bash
curl http://localhost:8000/health
```

Expected response: `{"status":"healthy","timestamp":"..."}`

### Database Error?

Delete the database and reinitialize:

```bash
rm data/mud.db
PYTHONPATH=src python3 -m mud_server.db.database
```

!!! warning
    This deletes all player data!

### Port Already in Use?

Change the port before starting:

```bash
export MUD_PORT=8001
./run.sh
```

### Permission Denied?

Make sure the run script is executable:

```bash
chmod +x run.sh
```

### Module Not Found?

Ensure you're using `PYTHONPATH=src` when running Python modules directly:

```bash
PYTHONPATH=src python3 -m mud_server.api.server
```

## Multi-Player Testing

Test multi-player features by:

1. Opening multiple browser windows/tabs
2. Logging in with different usernames
3. Moving to the same room
4. Chatting with each other

## Health Check

Verify the server is running correctly:

```bash
# Check server health
curl http://localhost:8000/health

# Check API documentation
open http://localhost:8000/docs  # Opens FastAPI Swagger UI
```

## Next Steps

Now that you're up and running:

- Read the [User Guide](../guide/playing.md) to learn gameplay mechanics
- Explore the [Commands Reference](../guide/commands.md) for all available commands
- Check out the [Architecture Overview](../architecture/overview.md) to understand the system
- Review the [Design Vision](../design/articulation.md) to understand the philosophy

Enjoy The Undertaking!
