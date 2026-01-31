# PipeWorks MUD Examples

Demo applications showcasing the MUD server's REST API.

## ASCII Movement Demo (`ascii_demo.html`)

A minimal browser-based client with retro terminal aesthetics demonstrating
keyboard-controlled movement through the game world.

### Features

- **ASCII Map**: 5 rooms in a cross pattern (spawn + 4 cardinal directions)
- **Keyboard Controls**: WASD or Arrow keys for movement
- **Visual Feedback**: Current room highlighted, keys light up on press
- **Room Descriptions**: Updates dynamically as you move
- **Login/Logout**: Full authentication via REST API

### World Layout

```text
              [FOREST]
                 |
    [LAKE] -- [SPAWN] -- [MOUNTAIN]
                 |
              [DESERT]
```

### Running

1. **Start the MUD server:**

   ```bash
   mud-server run
   ```

2. **Configure CORS** (add to `config/server.ini` if not present):

   ```ini
   cors_origins = http://localhost:7860, http://localhost:8000, http://localhost:8080
   ```

3. **Serve the demo:**

   ```bash
   python -m http.server 8080 -d examples
   ```

4. **Open in browser:**
   <http://localhost:8080/ascii_demo.html>

5. **Login and play!**
   Use WASD or arrow keys to move between rooms.

### API Endpoints Used

| Method | Endpoint              | Purpose                        |
|--------|----------------------|--------------------------------|
| POST   | `/login`             | Authenticate, get session ID   |
| POST   | `/logout`            | End session                    |
| GET    | `/status/{session_id}` | Get current room and status  |
| POST   | `/command`           | Send movement commands         |

### Troubleshooting

**"Connection failed" error:**

- Ensure the server is running on port 8000
- Check that `http://localhost:8080` is in `cors_origins`
- Restart the server after config changes

**CORS errors in console:**

- Don't open the HTML file directly (`file://` origin won't work)
- Always serve via HTTP: `python -m http.server 8080 -d examples`

### Code Structure

The demo is a single self-contained HTML file:

```text
ascii_demo.html
├── <style>           - Retro terminal CSS (green on black)
├── Login Section     - Server URL, username, password
├── Game Section      - Status bar, ASCII map, description, controls
└── <script>
    ├── State         - sessionId, currentRoom, username
    ├── ROOMS         - Static room data from world_data.json
    ├── apiCall()     - Fetch wrapper for API calls
    ├── login()       - POST /login
    ├── logout()      - POST /logout
    ├── updateStatus()- GET /status/{id}
    ├── move()        - POST /command
    ├── renderMap()   - ASCII map with highlighting
    └── keydown       - WASD/Arrow key handler
```

See the full documentation at [Read the Docs](https://pipeworks-mud-server.readthedocs.io/).
