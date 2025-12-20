"""FastAPI backend server for the MUD."""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mud_server.core.engine import GameEngine
from mud_server.api.routes import register_routes

# Initialize FastAPI app
app = FastAPI(title="MUD Server", version="0.1.0")

# Add CORS middleware to allow Gradio frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize game engine
engine = GameEngine()

# Register all routes
register_routes(app, engine)


if __name__ == "__main__":
    import uvicorn

    # Get host from environment or default to 0.0.0.0 for network access
    host = os.getenv("MUD_HOST", "0.0.0.0")
    port = int(os.getenv("MUD_PORT", 8000))

    uvicorn.run(app, host=host, port=port)
