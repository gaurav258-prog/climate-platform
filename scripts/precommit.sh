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

step "project documents match the code (BACKEND_SCHEMA, TECHNICAL_REQUIREMENTS, APP_FLOW, DESIGN_BRIEF)"
venv/bin/python -m scripts.build_project_docs --check     # schema from its own scratch build at head, never the dev database

step "web build"
(cd web && npm run build >/tmp/precommit-web.log 2>&1) || { tail -30 /tmp/precommit-web.log; exit 1; }

step "web unit tests"
(cd web && npm test >/tmp/precommit-web-test.log 2>&1) || { tail -30 /tmp/precommit-web-test.log; exit 1; }
echo ok

step "data folders and .env the tests read (E194: a worktree links the main checkout's git-ignored data and .env)"
main_root="$(cd "$(git rev-parse --path-format=absolute --git-common-dir)/.." && pwd -P)"
if [ "$main_root" != "$(pwd -P)" ]; then
  lacks=""
  missing=""
  for d in "$main_root"/data/*/; do n="$(basename "$d")"; [ -e "data/$n" ] || missing="$missing $n"; done
  if [ -n "$missing" ]; then
    echo "this worktree lacks git-ignored data folders the main checkout holds:$missing"
    echo "link them (untracked, never staged):  for n in$missing; do ln -s \"$main_root/data/\$n\" \"data/\$n\"; done"
    lacks=1
  fi
  if [ -e "$main_root/.env" ] && [ ! -e .env ]; then    # core/config.py reads its keys (NASS_API_KEY, ...) from .env
    echo "this worktree lacks the git-ignored .env the main checkout holds"
    echo "link it (untracked, never staged):  ln -s \"$main_root/.env\" .env"
    lacks=1
  fi
  [ -z "$lacks" ] || exit 1
fi
echo ok

step "test suite (+ demo-data guard)"
venv/bin/pytest -q -p no:cacheprovider

step "running code"
scripts/check_running_code.sh || echo "(restart the API before any live check)"
echo -e "\nall checks passed — ready to commit"
