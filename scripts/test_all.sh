#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== Backend unit/API tests =="
PYTHONPATH=backend pytest backend/tests

echo "== Frontend unit tests =="
cd frontend
npm test

echo "== Frontend production build =="
npm run build

echo "== Browser orchestration tests =="
npm run test:e2e

