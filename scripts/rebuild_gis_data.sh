#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ONLY="${1:-all}"
EXTRA_ARGS=()

if [[ "$ONLY" != "all" && "$ONLY" != "roads" && "$ONLY" != "hydrants" ]]; then
  echo "Usage: $0 [all|roads|hydrants] [--skip-graph]" >&2
  exit 2
fi

shift || true
EXTRA_ARGS=("$@")

PYTHONPATH=backend python3 -m app.scripts.build_layers --only "$ONLY" "${EXTRA_ARGS[@]}"

