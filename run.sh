#!/bin/bash

# MUD Server and Client Startup Script

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

# Set environment variables
export MUD_HOST="0.0.0.0"
export MUD_PORT=8000
export MUD_SERVER_URL="http://localhost:8000"

# Create a temporary directory for logs
mkdir -p "$SCRIPT_DIR/logs"

echo "Starting MUD Server and Client..."
echo "=================================="
echo ""
echo "Server will be available at: http://0.0.0.0:8000"
echo "Client will be available at: http://0.0.0.0:7860"
echo ""
echo "To access from another machine on your network:"
echo "- Find your machine's IP address (e.g., 192.168.x.x)"
echo "- Server: http://<your-ip>:8000"
echo "- Client: http://<your-ip>:7860"
echo ""
echo "Press Ctrl+C to stop both services"
echo ""

# Start the server in the background
echo "[$(date)] Starting FastAPI server..."
python3 "$SCRIPT_DIR/server.py" > "$SCRIPT_DIR/logs/server.log" 2>&1 &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"

# Wait a moment for server to start
sleep 2

# Start the client
echo "[$(date)] Starting Gradio client..."
python3 "$SCRIPT_DIR/client.py" > "$SCRIPT_DIR/logs/client.log" 2>&1 &
CLIENT_PID=$!
echo "Client PID: $CLIENT_PID"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "[$(date)] Shutting down..."
    kill $SERVER_PID 2>/dev/null
    kill $CLIENT_PID 2>/dev/null
    wait $SERVER_PID 2>/dev/null
    wait $CLIENT_PID 2>/dev/null
    echo "[$(date)] Shutdown complete"
}

# Set trap to cleanup on script exit
trap cleanup EXIT INT TERM

# Wait for both processes
wait $SERVER_PID $CLIENT_PID
