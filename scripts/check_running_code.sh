#!/usr/bin/env bash
# Guard (error log E4): is the local API running the code in this checkout? A server started before the last change
# serves old code — a live check against it proves nothing. Exit 1 when it is stale.
set -euo pipefail
cd "$(dirname "$0")/.."
running=$(curl -s localhost:8001/health | python3 -c 'import sys,json; print(json.load(sys.stdin).get("code_version") or "")')
head=$(git rev-parse --short HEAD)
dirty=$(git status --porcelain -- api services ml core | head -1)
if [ "$running" != "$head" ] || [ -n "$dirty" ]; then
  echo "STALE: API runs ${running:-unknown}, checkout is ${head}${dirty:+ with uncommitted backend changes} — restart it before any live check." >&2
  exit 1
fi
echo "API is running ${head}"
