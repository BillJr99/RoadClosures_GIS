#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend"

DEMO_STEP_MS="${DEMO_STEP_MS:-1200}" \
DEMO_SLOW_MO_MS="${DEMO_SLOW_MO_MS:-250}" \
npx playwright test --config playwright.demo.config.ts --headed --project chromium "$@"

