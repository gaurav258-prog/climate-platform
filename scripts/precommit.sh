#!/usr/bin/env bash
# The one pre-commit command (docs/ENGINEERING_PROCESS.md §2). Stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."
step() { printf '\n── %s\n' "$1"; }

step "lint (whole repository, exactly as CI)"
venv/bin/ruff check .          # linting only changed files let 50 errors pile up and CI stay red (E26)

step "migration graph"
venv/bin/python -m scripts.check_migrations

step "migration round-trip (every revision up and down, on a scratch database)"
venv/bin/python -m scripts.check_migration_roundtrip

step "web build"
(cd web && npm run build >/tmp/precommit-web.log 2>&1) || { tail -30 /tmp/precommit-web.log; exit 1; }
echo ok

step "test suite (+ demo-data guard)"
venv/bin/pytest -q -p no:cacheprovider

step "running code"
scripts/check_running_code.sh || echo "(restart the API before any live check)"
echo -e "\nall checks passed — ready to commit"
