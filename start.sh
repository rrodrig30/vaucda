#!/bin/bash

##############################################################################
# VAUCDA Startup Script
# Starts backend (FastAPI) and frontend (Vite) services
##############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# PID file locations
BACKEND_PID_FILE=".backend.pid"
FRONTEND_PID_FILE=".frontend.pid"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           VAUCDA - VA Urology Clinical Documentation      ║${NC}"
echo -e "${BLUE}║                    Starting Services...                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

##############################################################################
# Pre-flight Checks
##############################################################################

echo -e "${YELLOW}[1/6] Pre-flight Checks${NC}"

# Check if already running
if [ -f "$BACKEND_PID_FILE" ] && kill -0 $(cat "$BACKEND_PID_FILE") 2>/dev/null; then
    echo -e "${RED}✗ Backend already running (PID: $(cat $BACKEND_PID_FILE))${NC}"
    echo -e "${YELLOW}  Run ./stop.sh first to stop existing services${NC}"
    exit 1
fi

if [ -f "$FRONTEND_PID_FILE" ] && kill -0 $(cat "$FRONTEND_PID_FILE") 2>/dev/null; then
    echo -e "${RED}✗ Frontend already running (PID: $(cat $FRONTEND_PID_FILE))${NC}"
    echo -e "${YELLOW}  Run ./stop.sh first to stop existing services${NC}"
    exit 1
fi

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 not found. Please install Python 3.10+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓ Python ${PYTHON_VERSION}${NC}"

# Check Node.js version
if ! command -v node &> /dev/null; then
    echo -e "${RED}✗ Node.js not found. Please install Node.js 18+${NC}"
    exit 1
fi

NODE_VERSION=$(node --version)
echo -e "${GREEN}✓ Node.js ${NODE_VERSION}${NC}"

# Check npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}✗ npm not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Pre-flight checks passed${NC}"
echo ""

##############################################################################
# Check Environment Variables
##############################################################################

echo -e "${YELLOW}[2/6] Checking Environment Variables${NC}"

# Check for .env file
if [ ! -f "backend/.env" ]; then
    echo -e "${YELLOW}⚠ backend/.env not found. Creating from template...${NC}"
    if [ -f "backend/.env.example" ]; then
        cp backend/.env.example backend/.env
        echo -e "${YELLOW}  Please edit backend/.env and add your API keys${NC}"
    else
        echo -e "${RED}✗ backend/.env.example not found${NC}"
        exit 1
    fi
fi

if [ ! -f "frontend/.env" ]; then
    echo -e "${YELLOW}⚠ frontend/.env not found. Creating from template...${NC}"
    # Get server IP address for network access
    SERVER_IP=$(hostname -I | awk '{print $1}')
    cat > frontend/.env << EOF
VITE_API_BASE_URL=http://${SERVER_IP}:8002
EOF
    echo -e "${GREEN}✓ Created frontend/.env with server IP: ${SERVER_IP}${NC}"
fi

# Check for HUGGINGFACE_TOKEN (optional but recommended)
if ! grep -q "HUGGINGFACE_TOKEN=" backend/.env || grep -q "HUGGINGFACE_TOKEN=your_token_here" backend/.env; then
    echo -e "${YELLOW}⚠ HUGGINGFACE_TOKEN not set in backend/.env${NC}"
    echo -e "${YELLOW}  Speaker diarization will be disabled${NC}"
    echo -e "${YELLOW}  Get token from: https://huggingface.co/settings/tokens${NC}"
else
    echo -e "${GREEN}✓ HUGGINGFACE_TOKEN configured${NC}"
fi

echo ""

##############################################################################
# Install/Update Dependencies
##############################################################################

echo -e "${YELLOW}[3/6] Checking Dependencies${NC}"

# Backend dependencies
cd backend
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠ Python virtual environment not found. Creating...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

echo -e "${BLUE}  Activating virtual environment...${NC}"
source venv/bin/activate

# Check if requirements installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}⚠ Installing Python dependencies (this may take a few minutes)...${NC}"
    pip install --upgrade pip
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Python dependencies installed${NC}"
else
    echo -e "${GREEN}✓ Python dependencies already installed${NC}"
fi

# Check for Whisper model (download if needed)
echo -e "${BLUE}  Checking Whisper model...${NC}"
if ! python -c "import whisper; whisper.load_model('medium.en')" 2>/dev/null; then
    echo -e "${YELLOW}⚠ Downloading Whisper model (medium.en) - ~1.5GB...${NC}"
    echo -e "${YELLOW}  This is a one-time download and may take several minutes${NC}"
    python -c "import whisper; whisper.load_model('medium.en')" || {
        echo -e "${RED}✗ Failed to download Whisper model${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Whisper model downloaded${NC}"
else
    echo -e "${GREEN}✓ Whisper model already cached${NC}"
fi

cd ..

# Frontend dependencies
cd frontend
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}⚠ Installing frontend dependencies (this may take a few minutes)...${NC}"
    npm install
    echo -e "${GREEN}✓ Frontend dependencies installed${NC}"
else
    echo -e "${GREEN}✓ Frontend dependencies already installed${NC}"
fi
cd ..

echo ""

##############################################################################
# Initialize Database
##############################################################################

echo -e "${YELLOW}[4/6] Initializing Database${NC}"

# Check if SQLite database exists
if [ ! -f "backend/vaucda.db" ]; then
    echo -e "${YELLOW}⚠ Creating SQLite database...${NC}"
    cd backend
    source venv/bin/activate
    python -c "
from app.database.sqlite_models import Base
from app.database.sqlite_session import engine
Base.metadata.create_all(bind=engine)
print('Database initialized')
" || echo -e "${YELLOW}  Database will be created on first run${NC}"
    cd ..
    echo -e "${GREEN}✓ Database initialized${NC}"
else
    echo -e "${GREEN}✓ Database exists${NC}"
fi

# Check Neo4j (optional) - test actual connectivity
NEO4J_HOST="localhost"
NEO4J_PORT="7687"  # Default Neo4j bolt port

# Try to extract from .env if it exists
if [ -f "backend/.env" ]; then
    NEO4J_URI=$(grep "NEO4J_URI=" backend/.env | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    if [ -n "$NEO4J_URI" ]; then
        NEO4J_PORT=$(echo "$NEO4J_URI" | grep -oP '(?<=:)\d+' | tail -1)
    fi
fi

# Test if Neo4j port is open
if timeout 2 bash -c "echo > /dev/tcp/$NEO4J_HOST/$NEO4J_PORT" 2>/dev/null; then
    echo -e "${GREEN}✓ Neo4j accessible on port $NEO4J_PORT${NC}"
else
    echo -e "${YELLOW}⚠ Neo4j not accessible on port $NEO4J_PORT${NC}"
    echo -e "${YELLOW}  RAG features will be disabled${NC}"
    echo -e "${YELLOW}  Ensure Neo4j is running and accessible${NC}"
fi

echo ""

##############################################################################
# Start Backend Service
##############################################################################

echo -e "${YELLOW}[5/6] Starting Backend Service${NC}"

cd backend
source venv/bin/activate

# Export only HUGGINGFACE_* variables (CORS_ORIGINS will be loaded by pydantic)
echo -e "${BLUE}  Loading HuggingFace environment variables...${NC}"
while IFS='=' read -r key value; do
    # Skip empty lines and comments
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    # Only export HUGGINGFACE_* variables
    if [[ "$key" =~ ^HUGGINGFACE_ ]]; then
        export "$key=$value"
    fi
done < .env

# Log PEFT configuration
if [ "$HUGGINGFACE_PEFT_ENABLED" = "true" ]; then
    echo -e "${GREEN}✓ PEFT provider enabled (device: ${HUGGINGFACE_PEFT_DEVICE})${NC}"
else
    echo -e "${YELLOW}⚠ PEFT provider disabled${NC}"
fi

# Create logs directory
mkdir -p logs

# Check if HTTPS is enabled
USE_HTTPS=$(grep "USE_HTTPS=" .env | cut -d'=' -f2 | tr -d '"' | tr -d "'" | tr '[:upper:]' '[:lower:]')
BACKEND_PORT=$(grep "BACKEND_PORT=" .env | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "8002")

# Start backend in background - conditionally add SSL flags
if [ "$USE_HTTPS" = "true" ]; then
    PROTOCOL="https"
    echo -e "${BLUE}  Starting FastAPI server on https://localhost:${BACKEND_PORT}...${NC}"
    nohup uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT} --reload \
      --ssl-keyfile ../ssl/key.pem \
      --ssl-certfile ../ssl/cert.pem > logs/backend.log 2>&1 &
else
    PROTOCOL="http"
    echo -e "${BLUE}  Starting FastAPI server on http://localhost:${BACKEND_PORT}...${NC}"
    nohup uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT} --reload > logs/backend.log 2>&1 &
fi
BACKEND_PID=$!

# Save PID
echo $BACKEND_PID > ../$BACKEND_PID_FILE

# Wait for backend to start
echo -e "${BLUE}  Waiting for backend to start...${NC}"
for i in {1..30}; do
    if [ "$USE_HTTPS" = "true" ]; then
        if curl -s -k https://localhost:${BACKEND_PORT}/ > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Backend started on HTTPS (PID: $BACKEND_PID)${NC}"
            break
        fi
    else
        if curl -s http://localhost:${BACKEND_PORT}/ > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Backend started on HTTP (PID: $BACKEND_PID)${NC}"
            break
        fi
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Backend failed to start. Check logs/backend.log${NC}"
        cat logs/backend.log
        kill $BACKEND_PID 2>/dev/null
        rm ../$BACKEND_PID_FILE
        exit 1
    fi
    sleep 1
done

cd ..
echo ""

##############################################################################
# Start Frontend Service
##############################################################################

echo -e "${YELLOW}[6/6] Starting Frontend Service${NC}"

cd frontend

# Create logs directory
mkdir -p logs

# Start frontend in background
echo -e "${BLUE}  Starting Vite dev server on http://localhost:5173...${NC}"
nohup npm run dev > logs/frontend.log 2>&1 &
FRONTEND_PID=$!

# Save PID
echo $FRONTEND_PID > ../$FRONTEND_PID_FILE

# Wait for frontend to start
echo -e "${BLUE}  Waiting for frontend to start...${NC}"
FRONTEND_STARTED=false
for i in {1..30}; do
    # Extract port from log file if available
    if [ -f logs/frontend.log ]; then
        if [ "$USE_HTTPS" = "true" ]; then
            VITE_PORT=$(grep -oP '(?<=Local:   https://localhost:)\d+' logs/frontend.log | tail -1)
            if [ -n "$VITE_PORT" ]; then
                if curl -s -k https://localhost:$VITE_PORT > /dev/null 2>&1; then
                    echo -e "${GREEN}✓ Frontend started on HTTPS port $VITE_PORT (PID: $FRONTEND_PID)${NC}"
                    FRONTEND_STARTED=true
                    break
                fi
            fi
        else
            VITE_PORT=$(grep -oP '(?<=Local:   http://localhost:)\d+' logs/frontend.log | tail -1)
            if [ -n "$VITE_PORT" ]; then
                if curl -s http://localhost:$VITE_PORT > /dev/null 2>&1; then
                    echo -e "${GREEN}✓ Frontend started on HTTP port $VITE_PORT (PID: $FRONTEND_PID)${NC}"
                    FRONTEND_STARTED=true
                    break
                fi
            fi
        fi
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Frontend failed to start. Check logs/frontend.log${NC}"
        cat logs/frontend.log
        kill $FRONTEND_PID 2>/dev/null
        rm ../$FRONTEND_PID_FILE
        # Also stop backend
        kill $(cat ../$BACKEND_PID_FILE) 2>/dev/null
        rm ../$BACKEND_PID_FILE
        exit 1
    fi
    sleep 1
done

cd ..
echo ""

##############################################################################
# Success Summary
##############################################################################

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  VAUCDA Started Successfully!              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Services:${NC}"
echo -e "  ${GREEN}✓${NC} Backend:  ${PROTOCOL}://localhost:${BACKEND_PORT}"
if [ -n "$VITE_PORT" ]; then
    echo -e "  ${GREEN}✓${NC} Frontend: ${PROTOCOL}://localhost:$VITE_PORT"
else
    FRONTEND_PORT=$(grep "FRONTEND_PORT=" backend/.env | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "3005")
    echo -e "  ${GREEN}✓${NC} Frontend: ${PROTOCOL}://localhost:${FRONTEND_PORT} (check logs for actual port)"
fi
echo -e "  ${GREEN}✓${NC} API Docs: ${PROTOCOL}://localhost:${BACKEND_PORT}/docs"
echo ""
echo -e "${BLUE}Logs:${NC}"
echo -e "  Backend:  backend/logs/backend.log"
echo -e "  Frontend: frontend/logs/frontend.log"
echo ""
echo -e "${BLUE}Management:${NC}"
echo -e "  Stop services: ${YELLOW}./stop.sh${NC}"
echo -e "  View logs:     ${YELLOW}tail -f backend/logs/backend.log${NC}"
echo -e "  Restart:       ${YELLOW}./stop.sh && ./start.sh${NC}"
echo ""
echo -e "${BLUE}Default Credentials:${NC}"
echo -e "  Email:    ${YELLOW}admin@vaucda.va.gov${NC}"
echo -e "  Password: ${YELLOW}Admin123!${NC}"
echo -e "  ${RED}⚠ Change these in production!${NC}"
echo ""
if [ -n "$VITE_PORT" ]; then
    echo -e "${GREEN}Ready to use! Open ${PROTOCOL}://localhost:$VITE_PORT in your browser.${NC}"
    if [ "$USE_HTTPS" = "true" ]; then
        echo -e "${YELLOW}Note: You'll need to accept the self-signed certificate warning in your browser.${NC}"
    fi
else
    echo -e "${GREEN}Ready to use! Check the logs for the frontend port.${NC}"
    if [ "$USE_HTTPS" = "true" ]; then
        echo -e "${YELLOW}Note: You'll need to accept the self-signed certificate warning in your browser.${NC}"
    fi
fi
echo ""
