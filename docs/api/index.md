# API Reference

Complete API documentation for PipeWorks MUD Server, including auto-generated reference from Python code.

## Overview

PipeWorks MUD Server provides:

- **REST API** - FastAPI backend on port 8000
- **Python Package** - `mud_server` with core game logic
- **Pydantic Models** - Type-safe request/response schemas

## API Documentation

### Interactive API Docs

When the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These provide interactive API exploration with:

- All endpoints listed
- Request/response schemas
- Try-it-out functionality
- Authentication testing

## API Endpoints

### Authentication

- `POST /register` - Register new account
- `POST /login` - Log in and create session
- `POST /logout` - Log out and destroy session

### Game Actions

- `POST /command` - Execute game command
- `GET /status` - Get player status
- `GET /chat` - Get chat messages

### Admin

- `GET /admin/users` - List all users (Admin+)
- `PUT /admin/users/{username}/role` - Change user role (Superuser)
- `PUT /admin/users/{username}/password` - Reset password (Superuser)
- `PUT /admin/users/{username}/status` - Activate/deactivate account (Admin+)

### Health

- `GET /health` - Server health check

## Python Package Reference

Auto-generated documentation for all modules, classes, and functions:

[Browse API Reference](../reference/mud_server/index.md)

## Request/Response Models

All API endpoints use Pydantic models for validation.

### Example: CommandRequest

```python
class CommandRequest(BaseModel):
    """Request model for game commands."""

    session_id: str
    command: str
```

### Example: CommandResponse

```python
class CommandResponse(BaseModel):
    """Response model for game commands."""

    success: bool
    message: str
    room_info: Optional[RoomInfo] = None
```

See [models.py](../reference/mud_server/api/models.md) for all models.

## Authentication

All protected endpoints require a `session_id` in the request body.

### Session Creation

1. **Register**: `POST /register` with username and password
2. **Login**: `POST /login` with credentials
3. **Receive**: Session ID returned in response
4. **Use**: Include session_id in all subsequent requests

### Session Format

Sessions are stored as `(username, role)` tuples:

```python
active_sessions: Dict[str, Tuple[str, str]] = {}
```

Example:

```python
{
    "550e8400-e29b-41d4-a716-446655440000": ("alice", "player"),
    "6ba7b810-9dad-11d1-80b4-00c04fd430c8": ("admin", "superuser")
}
```

## Role-Based Access

Four user roles with hierarchical permissions:

| Role | Permissions |
|------|-------------|
| **Player** | Play game, chat, manage own inventory |
| **WorldBuilder** | Player + create/edit rooms and items |
| **Admin** | WorldBuilder + user management (limited) |
| **Superuser** | Admin + role management, full system access |

See [permissions.py](../reference/mud_server/api/permissions.md) for details.

## Error Handling

### HTTP Status Codes

- `200 OK` - Request succeeded
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Invalid or missing session
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

### Error Response Format

```json
{
    "detail": "Error message describing what went wrong"
}
```

## Rate Limiting

Currently not implemented. Future versions will include:

- Per-user rate limits
- Per-IP rate limits
- Exponential backoff for auth failures

## CORS Configuration

Development mode allows all origins (`*`).

For production, restrict origins in `server.py`:

```python
CORS_ORIGINS = [
    "https://yourdomain.com",
    "https://www.yourdomain.com"
]
```

## WebSocket Support (Future)

Planned for real-time features:

- Live chat updates
- Player movement notifications
- Room event broadcasting

Currently uses HTTP polling.

## Further Reading

- [Architecture Overview](../architecture/overview.md) - System design
- [API Design](../architecture/api-design.md) - Detailed API design
- [Developer Guide](../developer/contributing.md) - Contributing to the API
