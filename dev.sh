#!/bin/bash
set -e

# Track child PIDs
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "Shutting down..."

    # Kill specific processes we started
    if [ -n "$BACKEND_PID" ]; then
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    fi

    # Also kill any uvicorn/node processes on our ports
    lsof -ti :4445 | xargs -r kill -9 2>/dev/null || true
    lsof -ti :4444 | xargs -r kill -9 2>/dev/null || true

    # Kill entire process group as fallback
    kill -- -$$ 2>/dev/null || true

    wait 2>/dev/null || true
    echo "Shutdown complete."
}

trap cleanup SIGINT SIGTERM SIGHUP EXIT

uvicorn ralphx.api.main:app --reload --port 4445 &
BACKEND_PID=$!

cd frontend && npm run dev &
FRONTEND_PID=$!

wait $BACKEND_PID $FRONTEND_PID
