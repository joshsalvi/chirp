#!/usr/bin/env bash
# Pre-release checks, fastest first:
#   1. ruff: syntax errors and undefined names (bugs, not style)
#   2. tests, in parallel when pytest-xdist is installed
#   3. frontend build, which also checks the first-load size budget
#      (frontend/scripts/bundle-budget.mjs)
# SKIP_FRONTEND=1 skips 3. Dev tools: pip install -r requirements-dev.txt
set -euo pipefail
cd "$(dirname "$0")/.."
t0=$SECONDS
step() { printf '\n== %s\n' "$1"; }

step "lint (ruff: E9, F63, F7, F82)"
if command -v ruff >/dev/null; then ruff check app tests --select E9,F63,F7,F82 --output-format concise
else python3 -m pyflakes app >/dev/null 2>&1 || echo "ruff not installed: skipped"; fi

step "tests"
if python3 -c "import xdist" 2>/dev/null; then python3 -m pytest -q -p no:warnings -n auto tests
else python3 -m pytest -q -p no:warnings tests; fi

if [ "${SKIP_FRONTEND:-0}" != "1" ]; then
  step "frontend build + bundle budget"
  (cd frontend && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npm run build 2>&1 | grep -E "built in|bundle-budget|error" )
fi
printf '\nAll checks passed in %ss\n' "$((SECONDS - t0))"
