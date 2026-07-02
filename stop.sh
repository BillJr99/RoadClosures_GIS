#!/usr/bin/env bash
#
# stop.sh — shut down the backend and frontend dev servers started by run.sh.
#
# Uses the PID files written by run.sh. Terminates each process group so child
# processes (e.g. Vite's esbuild, uvicorn reloader) are cleaned up too.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

stop_one() {
  local name="$1" pidfile="$2"
  if [[ ! -f "$pidfile" ]]; then
    echo "$name: no PID file, not running."
    return
  fi
  local pid
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $name (PID $pid) ..."
    # Kill the whole process group; fall back to the single PID.
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "  still alive, sending KILL ..."
      kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    fi
  else
    echo "$name: PID $pid not running."
  fi
  rm -f "$pidfile"
}

stop_one "frontend" "$ROOT/frontend.pid"
stop_one "backend"  "$ROOT/backend.pid"

echo "Done."
