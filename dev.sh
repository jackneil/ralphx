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

# The browser talks to the Vite dev server, which proxies /api to the backend.
# Allow the Vite origin through the backend's Origin check.
export RALPHX_ALLOWED_ORIGINS="http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"

uvicorn ralphx.api.main:app --reload --reload-dir=ralphx --host 127.0.0.1 --port $BACKEND_PORT &
BACKEND_PID=$!

echo ""
echo "Dashboard login: $(python -m ralphx.cli dashboard-url --host localhost --port $FRONTEND_PORT)"
echo ""

cd frontend && npm run dev &
FRONTEND_PID=$!

wait $BACKEND_PID $FRONTEND_PID
