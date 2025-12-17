#!/bin/bash
# Stop VAUCDA Backend

echo "Stopping backend..."

# Load environment variables from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | grep -v '^[[:space:]]*$' | xargs)
fi

# Default to port 8000 if API_PORT is not set
API_PORT=${API_PORT:-8000}

echo "Checking port: $API_PORT"

# Kill by PID file if it exists
if [ -f "../.backend.pid" ]; then
    PID=$(cat ../.backend.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        echo "Killed backend process (PID: $PID)"
    else
        echo "PID $PID not running"
    fi
fi

# Force kill any remaining processes on the configured port
if lsof -ti:${API_PORT} >/dev/null 2>&1; then
    echo "Force killing processes on port ${API_PORT}..."
    lsof -ti:${API_PORT} | xargs kill -9 2>/dev/null
fi

sleep 2
echo "Backend stopped"
