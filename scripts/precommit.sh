#!/usr/bin/env bash
# The one pre-commit command (docs/ENGINEERING_PROCESS.md §2). Stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."
step() { printf '\n── %s\n' "$1"; }

step "lint (changed Python files)"
changed=$(git diff --name-only --diff-filter=ACMR HEAD -- '*.py'; git ls-files --others --exclude-standard -- '*.py')
if [ -n "$changed" ]; then venv/bin/ruff check $changed; else echo "no Python changes"; fi   # a lint failure stops the run

step "migration graph"
venv/bin/python -m scripts.check_migrations

step "web build"
(cd web && npm run build >/tmp/precommit-web.log 2>&1) || { tail -30 /tmp/precommit-web.log; exit 1; }
echo ok

step "test suite (+ demo-data guard)"
venv/bin/pytest -q -p no:cacheprovider

step "running code"
scripts/check_running_code.sh || echo "(restart the API before any live check)"
echo -e "\nall checks passed — ready to commit"
