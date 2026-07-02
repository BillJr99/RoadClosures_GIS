#!/usr/bin/env bash
#
# stop.sh — shut down the backend and frontend dev servers started by run.sh.
#
# Uses the PID files written by run.sh. Each recorded PID is the parent process
# for that service; this script walks the process tree from it and terminates
# every descendant too (e.g. npm -> vite, or a uvicorn reloader), so no orphaned
# server keeps holding its port.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Print the given PID and all of its descendants, deepest first, so children are
# signalled before their parents.
descendants_deep_first() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    descendants_deep_first "$child"
  done
  echo "$pid"
}

stop_one() {
  local name="$1" pidfile="$2"
  if [[ ! -f "$pidfile" ]]; then
    echo "$name: no PID file, not running."
    return
  fi
  local root_pid
  root_pid="$(cat "$pidfile")"
  if ! [[ "$root_pid" =~ ^[0-9]+$ ]] || ! kill -0 "$root_pid" 2>/dev/null; then
    echo "$name: PID ${root_pid:-?} not running."
    rm -f "$pidfile"
    return
  fi

  local pids
  pids="$(descendants_deep_first "$root_pid")"

  echo "Stopping $name (PID $root_pid and children) ..."
  local pid
  for pid in $pids; do
    kill -TERM "$pid" 2>/dev/null || true
  done

  # Give the tree a few seconds to exit gracefully.
  for _ in 1 2 3 4 5; do
    kill -0 "$root_pid" 2>/dev/null || break
    sleep 1
  done

  # Force-kill anything still alive.
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done

  rm -f "$pidfile"
}

stop_one "frontend" "$ROOT/frontend.pid"
stop_one "backend"  "$ROOT/backend.pid"

echo "Done."
