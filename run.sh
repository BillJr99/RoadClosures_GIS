#!/usr/bin/env bash
#
# run.sh — start the backend (FastAPI/uvicorn) and frontend (Vite) dev servers.
#
# Backend:  http://localhost:8001  (API under /api)
# Frontend: http://localhost:5173
#
# Both processes run in the background; PIDs are recorded so stop.sh can shut
# them down. Logs are written to backend.log and frontend.log (both gitignored).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BACKEND_HOST="0.0.0.0"
BACKEND_PORT="8001"
FRONTEND_PORT="5173"

# Prefer the project virtualenv if present.
if [[ -x "$ROOT/.venv/bin/uvicorn" ]]; then
  UVICORN="$ROOT/.venv/bin/uvicorn"
else
  UVICORN="uvicorn"
fi

already_running() {
  local pidfile="$1"
  [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

if already_running "$ROOT/backend.pid"; then
  echo "Backend already running (PID $(cat "$ROOT/backend.pid")). Run ./stop.sh first."
  exit 1
fi
if already_running "$ROOT/frontend.pid"; then
  echo "Frontend already running (PID $(cat "$ROOT/frontend.pid")). Run ./stop.sh first."
  exit 1
fi

echo "Starting backend on http://localhost:${BACKEND_PORT} ..."
PYTHONPATH=backend "$UVICORN" app.main:app \
  --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
  > "$ROOT/backend.log" 2>&1 &
echo $! > "$ROOT/backend.pid"

echo "Starting frontend on http://localhost:${FRONTEND_PORT} ..."
( cd frontend && npm run dev -- --port "$FRONTEND_PORT" ) \
  > "$ROOT/frontend.log" 2>&1 &
echo $! > "$ROOT/frontend.pid"

echo
echo "Backend  (PID $(cat "$ROOT/backend.pid")):  http://localhost:${BACKEND_PORT}/api/health  -> backend.log"
echo "Frontend (PID $(cat "$ROOT/frontend.pid")): http://localhost:${FRONTEND_PORT}/            -> frontend.log"
echo
echo "Stop both with ./stop.sh"
