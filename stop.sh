#!/bin/bash

##############################################################################
# VAUCDA Shutdown Script
# Stops backend (FastAPI) and frontend (Vite) services gracefully
##############################################################################

# Don't exit on error - we want to clean up as much as possible
set +e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# PID file locations
BACKEND_PID_FILE=".backend.pid"
FRONTEND_PID_FILE=".frontend.pid"

# Default ports (will be overridden from .env if available)
DEFAULT_BACKEND_PORT=8027
DEFAULT_FRONTEND_PORT=3005

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                  VAUCDA - Stopping Services                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

SERVICES_STOPPED=0

# Read actual ports from .env files
if [ -f "backend/.env" ]; then
    BACKEND_PORT=$(grep "^API_PORT=" backend/.env 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "$DEFAULT_BACKEND_PORT")
fi
if [ -z "$BACKEND_PORT" ]; then
    BACKEND_PORT=$DEFAULT_BACKEND_PORT
fi

# Try to get frontend port from logs or use default
if [ -f "frontend/logs/frontend.log" ]; then
    FRONTEND_PORT=$(grep -oP '(?<=Local:   https?://localhost:)\d+' frontend/logs/frontend.log 2>/dev/null | tail -1)
fi
if [ -z "$FRONTEND_PORT" ]; then
    FRONTEND_PORT=$DEFAULT_FRONTEND_PORT
fi

##############################################################################
# Stop Backend Service
##############################################################################

echo -e "${YELLOW}[1/3] Stopping Backend Service${NC}"

if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")

    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo -e "${BLUE}  Sending SIGTERM to backend (PID: $BACKEND_PID)...${NC}"
        kill "$BACKEND_PID"

        # Wait for graceful shutdown (max 10 seconds)
        for i in {1..10}; do
            if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
                echo -e "${GREEN}✓ Backend stopped gracefully${NC}"
                SERVICES_STOPPED=$((SERVICES_STOPPED + 1))
                break
            fi
            if [ $i -eq 10 ]; then
                echo -e "${YELLOW}⚠ Backend didn't stop gracefully, forcing...${NC}"
                kill -9 "$BACKEND_PID" 2>/dev/null || true
                echo -e "${GREEN}✓ Backend force-stopped${NC}"
                SERVICES_STOPPED=$((SERVICES_STOPPED + 1))
            fi
            sleep 1
        done
    else
        echo -e "${YELLOW}⚠ Backend process not running (PID: $BACKEND_PID)${NC}"
    fi

    rm -f "$BACKEND_PID_FILE"
else
    echo -e "${YELLOW}⚠ Backend PID file not found (service not running?)${NC}"
fi

echo ""

##############################################################################
# Stop Frontend Service
##############################################################################

echo -e "${YELLOW}[2/3] Stopping Frontend Service${NC}"

if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")

    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo -e "${BLUE}  Sending SIGTERM to frontend (PID: $FRONTEND_PID)...${NC}"
        kill "$FRONTEND_PID"

        # Wait for graceful shutdown (max 10 seconds)
        for i in {1..10}; do
            if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
                echo -e "${GREEN}✓ Frontend stopped gracefully${NC}"
                SERVICES_STOPPED=$((SERVICES_STOPPED + 1))
                break
            fi
            if [ $i -eq 10 ]; then
                echo -e "${YELLOW}⚠ Frontend didn't stop gracefully, forcing...${NC}"
                kill -9 "$FRONTEND_PID" 2>/dev/null || true
                echo -e "${GREEN}✓ Frontend force-stopped${NC}"
                SERVICES_STOPPED=$((SERVICES_STOPPED + 1))
            fi
            sleep 1
        done
    else
        echo -e "${YELLOW}⚠ Frontend process not running (PID: $FRONTEND_PID)${NC}"
    fi

    rm -f "$FRONTEND_PID_FILE"
else
    echo -e "${YELLOW}⚠ Frontend PID file not found (service not running?)${NC}"
fi

echo ""

##############################################################################
# Cleanup Orphaned Processes
##############################################################################

echo -e "${YELLOW}[3/3] Checking for orphaned processes${NC}"

# Check for any remaining uvicorn processes on the backend port
if command -v lsof &> /dev/null; then
    ORPHAN_BACKEND=$(lsof -ti:$BACKEND_PORT 2>/dev/null || true)
    if [ -n "$ORPHAN_BACKEND" ]; then
        echo -e "${YELLOW}⚠ Found orphaned process on port $BACKEND_PORT (PID: $ORPHAN_BACKEND)${NC}"
        kill -9 $ORPHAN_BACKEND 2>/dev/null || true
        echo -e "${GREEN}✓ Cleaned up orphaned backend process${NC}"
    fi

    # Check for any remaining vite/node processes on the frontend port
    ORPHAN_FRONTEND=$(lsof -ti:$FRONTEND_PORT 2>/dev/null || true)
    if [ -n "$ORPHAN_FRONTEND" ]; then
        echo -e "${YELLOW}⚠ Found orphaned process on port $FRONTEND_PORT (PID: $ORPHAN_FRONTEND)${NC}"
        kill -9 $ORPHAN_FRONTEND 2>/dev/null || true
        echo -e "${GREEN}✓ Cleaned up orphaned frontend process${NC}"
    fi

    # Also check common alternative ports
    for port in 8027 8000 8001 8002 3000 3005 5173; do
        if [ "$port" != "$BACKEND_PORT" ] && [ "$port" != "$FRONTEND_PORT" ]; then
            ORPHAN=$(lsof -ti:$port 2>/dev/null || true)
            if [ -n "$ORPHAN" ]; then
                # Check if it's a VAUCDA-related process
                PROC_NAME=$(ps -p $ORPHAN -o comm= 2>/dev/null || true)
                if [[ "$PROC_NAME" == *"uvicorn"* ]] || [[ "$PROC_NAME" == *"node"* ]] || [[ "$PROC_NAME" == *"npm"* ]]; then
                    echo -e "${YELLOW}⚠ Found potential VAUCDA process on port $port (PID: $ORPHAN, $PROC_NAME)${NC}"
                    echo -e "${YELLOW}  Run 'kill -9 $ORPHAN' manually if this is a VAUCDA orphan${NC}"
                fi
            fi
        fi
    done
else
    echo -e "${YELLOW}⚠ lsof not available, skipping orphan detection${NC}"
fi

# Kill any stray npm processes that might be from frontend
STRAY_NPM=$(pgrep -f "npm.*run.*dev" 2>/dev/null | head -5 || true)
if [ -n "$STRAY_NPM" ]; then
    for pid in $STRAY_NPM; do
        # Check if it's in the frontend directory
        PROC_CWD=$(readlink /proc/$pid/cwd 2>/dev/null || true)
        if [[ "$PROC_CWD" == *"vaucda/frontend"* ]]; then
            echo -e "${YELLOW}⚠ Found stray npm dev process (PID: $pid)${NC}"
            kill -9 $pid 2>/dev/null || true
            echo -e "${GREEN}✓ Cleaned up stray npm process${NC}"
        fi
    done
fi

echo -e "${GREEN}✓ Cleanup complete${NC}"
echo ""

##############################################################################
# Summary
##############################################################################

if [ $SERVICES_STOPPED -eq 2 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              All VAUCDA Services Stopped!                  ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
elif [ $SERVICES_STOPPED -gt 0 ]; then
    echo -e "${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║          Some VAUCDA Services Stopped                      ║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
else
    echo -e "${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║          No VAUCDA Services Were Running                   ║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
fi

echo ""
echo -e "${BLUE}To restart services:${NC}"
echo -e "  ${YELLOW}./start.sh${NC}"
echo ""
