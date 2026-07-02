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

# FULL implementation: run the backend in the L1-capable venv (Python 3.11 with
# torch + transformers + peft + bitsandbytes AND the full server deps) so the L1
# narrative extractor runs in-process. Falls back to the classic py3.9 venv only
# if .venv-l1 is absent (L1 then degrades gracefully to the deterministic path).
if [ -x "backend/.venv-l1/bin/python" ]; then
    BACKEND_VENV=".venv-l1"
    RUN_FULL_L1=true
else
    BACKEND_VENV="venv"
    RUN_FULL_L1=false
fi

# Default ports (will be overridden from .env if available)
DEFAULT_BACKEND_PORT=8027
DEFAULT_FRONTEND_PORT=3005

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           VAUCDA - VA Urology Clinical Documentation      ║${NC}"
echo -e "${BLUE}║                    Starting Services...                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

##############################################################################
# Pre-flight Checks
##############################################################################

echo -e "${YELLOW}[1/7] Pre-flight Checks${NC}"

# Check if already running — clean up stale PID files, skip live services
SKIP_BACKEND=false
SKIP_FRONTEND=false

if [ -f "$BACKEND_PID_FILE" ]; then
    if kill -0 $(cat "$BACKEND_PID_FILE") 2>/dev/null; then
        echo -e "${GREEN}✓ Backend already running (PID: $(cat $BACKEND_PID_FILE))${NC}"
        SKIP_BACKEND=true
    else
        echo -e "${YELLOW}⚠ Stale backend PID file (process dead). Cleaning up.${NC}"
        rm -f "$BACKEND_PID_FILE"
    fi
fi

if [ -f "$FRONTEND_PID_FILE" ]; then
    if kill -0 $(cat "$FRONTEND_PID_FILE") 2>/dev/null; then
        echo -e "${GREEN}✓ Frontend already running (PID: $(cat $FRONTEND_PID_FILE))${NC}"
        SKIP_FRONTEND=true
    else
        echo -e "${YELLOW}⚠ Stale frontend PID file (process dead). Cleaning up.${NC}"
        rm -f "$FRONTEND_PID_FILE"
    fi
fi

if [ "$SKIP_BACKEND" = true ] && [ "$SKIP_FRONTEND" = true ]; then
    echo -e "${GREEN}Both services already running. Nothing to do.${NC}"
    echo -e "${YELLOW}  Run ./stop.sh first to restart services${NC}"
    exit 0
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

echo -e "${YELLOW}[2/7] Checking Environment Variables${NC}"

# Check for backend .env file
if [ ! -f "backend/.env" ]; then
    echo -e "${YELLOW}⚠ backend/.env not found. Creating from template...${NC}"
    if [ -f "backend/.env.example" ]; then
        cp backend/.env.example backend/.env
        echo -e "${GREEN}✓ Created backend/.env from template${NC}"
        echo -e "${YELLOW}  Please edit backend/.env and configure your settings${NC}"
    else
        echo -e "${RED}✗ backend/.env.example not found${NC}"
        exit 1
    fi
fi

# Read backend port from .env
BACKEND_PORT=$(grep "^API_PORT=" backend/.env 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "$DEFAULT_BACKEND_PORT")
if [ -z "$BACKEND_PORT" ]; then
    BACKEND_PORT=$DEFAULT_BACKEND_PORT
fi

# Check for frontend .env file
if [ ! -f "frontend/.env" ]; then
    echo -e "${YELLOW}⚠ frontend/.env not found. Creating...${NC}"
    # Get server IP address for network access
    SERVER_IP=$(hostname -I | awk '{print $1}')
    cat > frontend/.env << EOF
VITE_API_BASE_URL=http://${SERVER_IP}:${BACKEND_PORT}
EOF
    echo -e "${GREEN}✓ Created frontend/.env with server IP: ${SERVER_IP}${NC}"
fi

echo -e "${GREEN}✓ Environment files configured${NC}"
echo ""

##############################################################################
# Create Required Directories
##############################################################################

echo -e "${YELLOW}[3/7] Creating Required Directories${NC}"

# Create backend directories
mkdir -p backend/data
mkdir -p backend/data/documents
mkdir -p backend/data/templates
mkdir -p backend/logs
mkdir -p logs

# Create frontend logs directory
mkdir -p frontend/logs

echo -e "${GREEN}✓ Directories created${NC}"
echo ""

##############################################################################
# Install/Update Dependencies
##############################################################################

echo -e "${YELLOW}[4/7] Checking Dependencies${NC}"

# Backend dependencies
cd backend
if [ "$RUN_FULL_L1" = true ]; then
    echo -e "${GREEN}✓ FULL mode: using L1 venv (.venv-l1)${NC}"
else
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}⚠ Python virtual environment not found. Creating...${NC}"
        python3 -m venv venv
        echo -e "${GREEN}✓ Virtual environment created${NC}"
    fi
    echo -e "${YELLOW}⚠ .venv-l1 not found — starting WITHOUT the L1 extractor${NC}"
    echo -e "${YELLOW}  (deterministic multi-cancer + fact-guard still active). To enable${NC}"
    echo -e "${YELLOW}  FULL/L1, build backend/.venv-l1 per scripts/l1/README.md.${NC}"
fi

echo -e "${BLUE}  Activating virtual environment ($BACKEND_VENV)...${NC}"
source "$BACKEND_VENV/bin/activate"

# Check core deps are present
if ! python -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}⚠ Installing Python dependencies (this may take a few minutes)...${NC}"
    pip install --upgrade pip
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Python dependencies installed${NC}"
else
    echo -e "${GREEN}✓ Python dependencies already installed${NC}"
fi

# FULL mode: verify the L1 ML stack is importable
if [ "$RUN_FULL_L1" = true ]; then
    if python -c "import torch, transformers, peft, bitsandbytes" 2>/dev/null; then
        echo -e "${GREEN}✓ L1 ML stack present (torch/transformers/peft/bitsandbytes)${NC}"
    else
        echo -e "${YELLOW}⚠ .venv-l1 is missing the L1 ML stack; L1 will degrade to deterministic${NC}"
        RUN_FULL_L1=false
    fi
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

echo -e "${YELLOW}[5/7] Initializing Database${NC}"

cd backend
source "$BACKEND_VENV/bin/activate"

# Check if SQLite database exists
if [ ! -f "data/vaucda.db" ]; then
    echo -e "${YELLOW}⚠ SQLite database not found. Will be created on first run.${NC}"
else
    echo -e "${GREEN}✓ SQLite database exists${NC}"
fi

# Run database migrations to ensure schema is up to date
echo -e "${BLUE}  Running database migrations...${NC}"
if [ -f "database/migrations/add_task_llm_columns.py" ]; then
    python database/migrations/add_task_llm_columns.py 2>/dev/null || echo -e "${YELLOW}  Migration script completed (or database not yet created)${NC}"
fi
if [ -f "database/migrations/add_num_ctx_columns.py" ]; then
    python database/migrations/add_num_ctx_columns.py 2>/dev/null || echo -e "${YELLOW}  num_ctx migration script completed (or database not yet created)${NC}"
fi
if [ -f "database/migrations/add_source_format_column.py" ]; then
    python database/migrations/add_source_format_column.py 2>/dev/null || echo -e "${YELLOW}  source_format migration script completed (or database not yet created)${NC}"
fi
echo -e "${GREEN}✓ Database migrations complete${NC}"

# Check Neo4j (optional) - test actual connectivity
NEO4J_HOST="localhost"
NEO4J_PORT="7687"  # Default Neo4j bolt port

# Try to extract from .env if it exists
if [ -f ".env" ]; then
    NEO4J_URI=$(grep "^NEO4J_URI=" .env | cut -d'=' -f2 | tr -d '"' | tr -d "'")
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
fi

cd ..
echo ""

##############################################################################
# Start Backend Service
##############################################################################

echo -e "${YELLOW}[6/7] Starting Backend Service${NC}"

# Check if HTTPS is enabled (needed for summary even if skipping)
USE_HTTPS=$(grep "^USE_HTTPS=" backend/.env 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'" | tr '[:upper:]' '[:lower:]' || echo "false")
if [ "$USE_HTTPS" = "true" ]; then
    PROTOCOL="https"
else
    PROTOCOL="http"
fi

if [ "$SKIP_BACKEND" = true ]; then
    echo -e "${GREEN}✓ Backend already running — skipping${NC}"
else
    cd backend
    source "$BACKEND_VENV/bin/activate"

    # Create logs directory
    mkdir -p logs

    # torch 2.8 + Python 3.9 does not auto-resolve the bundled nvidia/*/lib
    # wheels (libcudnn.so.9 etc.). Without this, `import torch` fails with:
    #   ImportError: libcudnn.so.9: cannot open shared object file
    # Ask Python where the `nvidia` package actually lives (lib vs lib64
    # varies by platform; site.getsitepackages()[0] is not reliable),
    # then prepend every nvidia/*/lib dir to LD_LIBRARY_PATH so torch
    # loads its bundled cuDNN, cuBLAS, NCCL, etc.
    NVIDIA_DIR=$(python -c "import nvidia, os; print(os.path.dirname(nvidia.__file__))" 2>/dev/null)
    if [ -n "$NVIDIA_DIR" ] && [ -d "$NVIDIA_DIR" ]; then
        NV_LIBS=$(find "$NVIDIA_DIR" -mindepth 2 -maxdepth 3 -type d -name lib 2>/dev/null | tr '\n' ':')
        if [ -n "$NV_LIBS" ]; then
            export LD_LIBRARY_PATH="${NV_LIBS}${LD_LIBRARY_PATH}"
            echo -e "${BLUE}  Prepended $(echo "$NV_LIBS" | tr ':' '\n' | grep -c .) nvidia lib dirs to LD_LIBRARY_PATH${NC}"
        fi
    fi

    # The app mounts a static/ directory at import time — ensure it exists.
    mkdir -p static

    # FULL/L1 runtime env: turn the L1 narrative extractor on and make the gated
    # medgemma base model reachable. HF_TOKEN is read from the repo .env (root or
    # backend). --reload is disabled in FULL mode so the resident 27B model isn't
    # reloaded on every file-watch event.
    RELOAD_FLAG="--reload"
    if [ "$RUN_FULL_L1" = true ]; then
        export VAUCDA_L1=1
        export VAUCDA_L1_MAX_NEW="${VAUCDA_L1_MAX_NEW:-2048}"
        export TOKENIZERS_PARALLELISM=false
        export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
        if [ -z "$HF_TOKEN" ]; then
            for envf in ../.env .env; do
                if [ -f "$envf" ]; then
                    _tok=$(grep -E '^HF_TOKEN=' "$envf" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")
                    [ -n "$_tok" ] && export HF_TOKEN="$_tok" && break
                fi
            done
        fi
        if [ -n "$HF_TOKEN" ]; then
            echo -e "${GREEN}✓ FULL/L1 enabled (VAUCDA_L1=1, HF_TOKEN loaded)${NC}"
        else
            echo -e "${YELLOW}⚠ VAUCDA_L1=1 but HF_TOKEN not found in .env — L1 will degrade to deterministic${NC}"
        fi
        RELOAD_FLAG=""
        echo -e "${YELLOW}  (FULL mode: --reload disabled so the 27B model stays resident)${NC}"
    fi

    # Start backend in background
    # CRITICAL: Exclude data directory from reload watching to prevent restarts during file uploads
    if [ "$USE_HTTPS" = "true" ]; then
        echo -e "${BLUE}  Starting FastAPI server on https://0.0.0.0:${BACKEND_PORT}...${NC}"
        nohup uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT} $RELOAD_FLAG \
          --reload-exclude 'data/*' --reload-exclude 'logs/*' --reload-exclude '*.db' \
          --ssl-keyfile ../ssl/key.pem \
          --ssl-certfile ../ssl/cert.pem > logs/backend.log 2>&1 &
    else
        echo -e "${BLUE}  Starting FastAPI server on http://0.0.0.0:${BACKEND_PORT}...${NC}"
        nohup uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT} $RELOAD_FLAG \
          --reload-exclude 'data/*' --reload-exclude 'logs/*' --reload-exclude '*.db' > logs/backend.log 2>&1 &
    fi
    BACKEND_PID=$!

    # Save PID
    echo $BACKEND_PID > ../$BACKEND_PID_FILE

    # Wait for backend to start
    echo -e "${BLUE}  Waiting for backend to start...${NC}"
    for i in {1..30}; do
        if [ "$USE_HTTPS" = "true" ]; then
            if curl -s -k https://localhost:${BACKEND_PORT}/api/v1/health > /dev/null 2>&1; then
                echo -e "${GREEN}✓ Backend started on HTTPS (PID: $BACKEND_PID)${NC}"
                break
            fi
        else
            if curl -s http://localhost:${BACKEND_PORT}/api/v1/health > /dev/null 2>&1; then
                echo -e "${GREEN}✓ Backend started on HTTP (PID: $BACKEND_PID)${NC}"
                break
            fi
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}✗ Backend failed to start. Check logs/backend.log${NC}"
            tail -50 logs/backend.log
            kill $BACKEND_PID 2>/dev/null
            rm ../$BACKEND_PID_FILE
            exit 1
        fi
        sleep 1
    done

    cd ..
fi
echo ""

##############################################################################
# Start Frontend Service
##############################################################################

echo -e "${YELLOW}[7/7] Starting Frontend Service${NC}"

VITE_PORT=""
if [ "$SKIP_FRONTEND" = true ]; then
    echo -e "${GREEN}✓ Frontend already running — skipping${NC}"
    # Try to detect the port from the running frontend log
    if [ -f "frontend/logs/frontend.log" ]; then
        VITE_PORT=$(grep -oE 'localhost:[0-9]+' frontend/logs/frontend.log 2>/dev/null | head -1 | cut -d':' -f2)
    fi
else
    cd frontend

    # Create logs directory
    mkdir -p logs

    # Start frontend in background
    echo -e "${BLUE}  Starting Vite dev server...${NC}"
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
            # More robust pattern matching - look for localhost:PORT anywhere in line
            VITE_PORT=$(grep -oE 'localhost:[0-9]+' logs/frontend.log 2>/dev/null | head -1 | cut -d':' -f2)
            if [ -n "$VITE_PORT" ]; then
                # Give Vite a moment to fully initialize after logging
                sleep 1
                if curl -s --connect-timeout 2 http://localhost:$VITE_PORT > /dev/null 2>&1; then
                    echo -e "${GREEN}✓ Frontend started on port $VITE_PORT (PID: $FRONTEND_PID)${NC}"
                    FRONTEND_STARTED=true
                    break
                fi
            fi
        fi
        if [ $i -eq 30 ]; then
            # Check if Vite logged that it's ready even if curl failed
            if grep -q "ready in" logs/frontend.log 2>/dev/null; then
                VITE_PORT=$(grep -oE 'localhost:[0-9]+' logs/frontend.log 2>/dev/null | head -1 | cut -d':' -f2)
                if [ -n "$VITE_PORT" ]; then
                    echo -e "${GREEN}✓ Frontend started on port $VITE_PORT (PID: $FRONTEND_PID)${NC}"
                    FRONTEND_STARTED=true
                    break
                fi
            fi
            echo -e "${RED}✗ Frontend failed to start. Check frontend/logs/frontend.log${NC}"
            tail -50 logs/frontend.log
            kill $FRONTEND_PID 2>/dev/null
            rm ../$FRONTEND_PID_FILE
            # Also stop backend
            if [ -f ../$BACKEND_PID_FILE ]; then
                kill $(cat ../$BACKEND_PID_FILE) 2>/dev/null
                rm ../$BACKEND_PID_FILE
            fi
            exit 1
        fi
        sleep 1
    done

    cd ..
fi
echo ""

##############################################################################
# Success Summary
##############################################################################

# Get server IP for network access URLs
SERVER_IP=$(hostname -I | awk '{print $1}')

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  VAUCDA Started Successfully!              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Services:${NC}"
echo -e "  ${GREEN}✓${NC} Backend:  ${PROTOCOL}://localhost:${BACKEND_PORT}"
echo -e "            ${PROTOCOL}://${SERVER_IP}:${BACKEND_PORT} (network)"
if [ -n "$VITE_PORT" ]; then
    echo -e "  ${GREEN}✓${NC} Frontend: http://localhost:$VITE_PORT"
    echo -e "            http://${SERVER_IP}:$VITE_PORT (network)"
else
    echo -e "  ${GREEN}✓${NC} Frontend: Check logs for actual port"
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
    echo -e "${GREEN}Ready to use! Open http://localhost:$VITE_PORT in your browser.${NC}"
else
    echo -e "${GREEN}Ready to use! Check the frontend logs for the port.${NC}"
fi
echo ""
