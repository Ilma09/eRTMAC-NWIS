#!/bin/bash
# stop.sh - shuts down both the backend (port 8000) and frontend (port 5173)
# started by start.sh. Run with: bash stop.sh

for PORT in 8000 5173; do
  PID=$(netstat -ano | grep ":$PORT" | grep LISTENING | awk '{print $5}' | head -1)
  if [ -n "$PID" ]; then
    taskkill //PID "$PID" //F
    echo "Stopped process on port $PORT (PID $PID)"
  else
    echo "Nothing listening on port $PORT"
  fi
done
