#!/bin/bash
set -e

# Ports - high random ports to avoid conflicts
BACKEND_PORT=16767
FRONTEND_PORT=16768

# Track child PIDs
BACKEND_PID=""
FRONTEND_PID=""
CLEANING_UP=false

# Kill any existing processes on our ports before starting
echo "Clearing ports..."
lsof -ti :$BACKEND_PORT | xargs -r kill -9 2>/dev/null || true
lsof -ti :$FRONTEND_PORT | xargs -r kill -9 2>/dev/null || true
sleep 0.5

cleanup() {
    # Prevent re-entry
    if [ "$CLEANING_UP" = true ]; then
        return
    fi
    CLEANING_UP=true

    # Disable traps to prevent loops
    trap - SIGINT SIGTERM SIGHUP EXIT

    echo ""
    echo "Shutting down..."

    # Kill specific processes we started
    if [ -n "$BACKEND_PID" ]; then
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    fi

    # Give processes a moment to exit gracefully
    sleep 0.5

    # Force kill any remaining processes on our ports
    lsof -ti :$BACKEND_PORT | xargs -r kill -9 2>/dev/null || true
    lsof -ti :$FRONTEND_PORT | xargs -r kill -9 2>/dev/null || true

    echo "Shutdown complete."
    exit 0
}

trap cleanup SIGINT SIGTERM SIGHUP

uvicorn ralphx.api.main:app --reload --port $BACKEND_PORT &
BACKEND_PID=$!

cd frontend && npm run dev &
FRONTEND_PID=$!

wait $BACKEND_PID $FRONTEND_PID
