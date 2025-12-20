# MUD Server - Quick Start Guide

## 30-Second Setup

```bash
cd /home/ubuntu/mud_project
source venv/bin/activate
pip install -r requirements.txt
python3 database.py
./run.sh
```

Then open your browser to:
- **Client**: http://localhost:7860
- **Server API**: http://localhost:8000

## First Steps

1. **Login**: Enter a username and click "Login"
2. **Explore**: Use the arrow buttons to move around
3. **Collect Items**: Use "Get" command to pick up items
4. **Chat**: Type "say Hello!" to chat with others
5. **Check Status**: Click "Inventory" to see what you're carrying

## Network Access

To play from another computer on your network:

1. Find your IP: `hostname -I`
2. Replace `localhost` with your IP address in the URLs
3. Example: `http://192.168.1.100:7860`

## Available Commands

| Command | Description |
|---------|-------------|
| `north`, `south`, `east`, `west` | Move around |
| `n`, `s`, `e`, `w` | Shorthand for directions |
| `look` | Examine current room |
| `inventory` | Check your items |
| `get <item>` | Pick up an item |
| `drop <item>` | Drop an item |
| `say <message>` | Chat with players in your room |
| `who` | List online players |
| `help` | Show all commands |

## World Map

```
        [Forest]
            |
[Lake] - [Spawn] - [Mountain]
            |
        [Desert]
```

## Stopping the Server

Press `Ctrl+C` in the terminal where you ran `./run.sh`

## Troubleshooting

**Can't connect?**
- Make sure the server is running: `curl http://localhost:8000/health`
- Check firewall settings
- Try a different port if 8000/7860 are in use

**Database error?**
- Delete `mud.db` and run `python3 database.py` again

**Port in use?**
- Change ports: `export MUD_PORT=8001` before running

## Multi-Player Testing

Open multiple browser windows/tabs and log in with different usernames to test multi-player functionality!

Enjoy!
