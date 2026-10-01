#!/usr/bin/env bash
# The one pre-commit command (docs/ENGINEERING_PROCESS.md §2). Stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."
step() { printf '\n── %s\n' "$1"; }

# One gate at a time on the shared database (E102): two runs at once see each other's writes — a demo-data guard or a
# migration step then reports the other run, not this one. Agents' worktrees share the database, so they share the lock.
LOCK=/tmp/climate-platform-gate.lock
until mkdir "$LOCK" 2>/dev/null; do
  holder=$(cat "$LOCK/pid" 2>/dev/null || true)
  if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then rm -rf "$LOCK"; continue; fi   # a run that died
  echo "another gate is running on the shared database (pid ${holder:-?}) — waiting"; sleep 15
done
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

step "lint (whole repository, exactly as CI)"
venv/bin/ruff check .          # linting only changed files let 50 errors pile up and CI stay red (E26)

step "migration graph"
venv/bin/python -m scripts.check_migrations

step "applied migrations match their files (the development database)"
venv/bin/python -m scripts.check_applied_migrations

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
