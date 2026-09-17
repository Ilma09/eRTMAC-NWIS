#!/bin/bash
# start.sh - one command to launch both the backend (FastAPI) and frontend
# (Vite/React), each in its own separate console window (more reliable on
# Windows than backgrounding inside this script's own console - a background
# job here can get killed by Windows' console signal handling even though it
# looks "detached"). Waits until both are actually responding, then opens the
# app in your default browser. Run with: bash start.sh

cd "$(dirname "$0")"
ROOT="$(pwd -W 2>/dev/null || pwd)"

echo "Starting backend (FastAPI on :8000) in its own window..."
cmd.exe //c start "eRTMAC Backend" cmd //k "cd /d "$ROOT\\backend" && venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo "Starting frontend (Vite on :5173) in its own window..."
cmd.exe //c start "eRTMAC Frontend" cmd //k "cd /d "$ROOT\\ertmac-nwis" && npm run dev"

echo "Waiting for both servers to come up..."
until curl -s -o /dev/null http://localhost:8000/api/corpus; do sleep 1; done
until curl -s -o /dev/null http://localhost:5173; do sleep 1; done

echo "Both servers are up - opening the app..."
explorer.exe "http://localhost:5173"

echo ""
echo "Backend and frontend are each running in their own window - watch those directly for live output/errors."
echo "Close this terminal any time; the two server windows keep running independently."
echo "To stop both: close their windows, or run stop.sh."
