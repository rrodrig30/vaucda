#!/bin/bash

##############################################################################
# VAUCDA Shutdown Script
# Stops backend (FastAPI) and frontend (Vite) services gracefully
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
echo -e "${BLUE}║                  VAUCDA - Stopping Services                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

SERVICES_STOPPED=0

##############################################################################
# Stop Backend Service
##############################################################################

echo -e "${YELLOW}[1/2] Stopping Backend Service${NC}"

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

    rm "$BACKEND_PID_FILE"
else
    echo -e "${YELLOW}⚠ Backend PID file not found (service not running?)${NC}"
fi

echo ""

##############################################################################
# Stop Frontend Service
##############################################################################

echo -e "${YELLOW}[2/2] Stopping Frontend Service${NC}"

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

    rm "$FRONTEND_PID_FILE"
else
    echo -e "${YELLOW}⚠ Frontend PID file not found (service not running?)${NC}"
fi

echo ""

##############################################################################
# Cleanup Orphaned Processes
##############################################################################

echo -e "${YELLOW}[3/3] Checking for orphaned processes${NC}"

# Check for any remaining uvicorn processes on port 8002
ORPHAN_BACKEND=$(lsof -ti:8002 2>/dev/null || true)
if [ ! -z "$ORPHAN_BACKEND" ]; then
    echo -e "${YELLOW}⚠ Found orphaned backend process on port 8002 (PID: $ORPHAN_BACKEND)${NC}"
    kill -9 $ORPHAN_BACKEND 2>/dev/null || true
    echo -e "${GREEN}✓ Cleaned up orphaned backend process${NC}"
fi

# Check for any remaining vite processes on port 5173
ORPHAN_FRONTEND=$(lsof -ti:5173 2>/dev/null || true)
if [ ! -z "$ORPHAN_FRONTEND" ]; then
    echo -e "${YELLOW}⚠ Found orphaned frontend process on port 5173 (PID: $ORPHAN_FRONTEND)${NC}"
    kill -9 $ORPHAN_FRONTEND 2>/dev/null || true
    echo -e "${GREEN}✓ Cleaned up orphaned frontend process${NC}"
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
