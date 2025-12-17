#!/bin/bash
# Start VAUCDA Backend with Fine-Tuned Model

echo "Starting VAUCDA backend with fine-tuned model..."

# Load environment variables from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | grep -v '^[[:space:]]*$' | xargs)
fi

# Default to port 8000 if API_PORT is not set
API_PORT=${API_PORT:-8000}

echo "Using port: $API_PORT"

# Activate virtual environment
source venv/bin/activate

# Clear old logs
> logs/backend.log

# Start backend in background
nohup uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT} --reload > logs/backend.log 2>&1 &

# Save PID
echo $! > ../.backend.pid

echo "Backend starting (PID: $(cat ../.backend.pid))"
echo "Waiting for initialization..."

# Wait for startup
sleep 10

# Check if it's running
if lsof -ti:${API_PORT} >/dev/null 2>&1; then
    echo ""
    echo "✓ Backend started successfully!"
    echo ""
    echo "Check logs with: tail -f logs/backend.log"
    echo "API available at: http://localhost:${API_PORT}"
    echo ""

    # Show model loading status
    echo "Model loading status:"
    tail -50 logs/backend.log | grep -E "(PEFT|HuggingFace|LoRA|adapter|fine-tuned|Application startup complete)" | tail -10
else
    echo ""
    echo "✗ Backend failed to start"
    echo "Check logs: tail -f logs/backend.log"
    exit 1
fi
