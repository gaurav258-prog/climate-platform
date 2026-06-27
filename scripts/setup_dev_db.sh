#!/usr/bin/env bash
# Reproducible local dev database for the climate platform.
#
# Brings up the canonical dev DB so the schema always matches the Alembic
# migration chain (the single source of truth). Idempotent: safe to re-run.
#
#   role:   climate_app
#   db:     climate_platform
#   driver: psycopg3  (postgresql+psycopg://)  — matches .env / requirements.txt
#
# Requires a running PostgreSQL on localhost:5432 and a superuser you can connect
# as (defaults to the current OS user). Run from the repo root:
#
#   ./scripts/setup_dev_db.sh            # create role+db if missing, migrate to head
#   ./scripts/setup_dev_db.sh --rebuild  # DROP the schema first (destroys all data)
#
set -euo pipefail
export LC_ALL=C

ADMIN_USER="${PGADMIN_USER:-$(whoami)}"
HOST="${PGHOST:-127.0.0.1}"
PORT="${PGPORT:-5432}"
APP_ROLE="climate_app"
APP_DB="climate_platform"
PSQL="$(command -v psql || echo /opt/homebrew/opt/postgresql@16/bin/psql)"
ADMIN="postgresql://${ADMIN_USER}@${HOST}:${PORT}/postgres"

echo "→ ensuring role ${APP_ROLE} and database ${APP_DB} exist"
"$PSQL" "$ADMIN" -tAc "SELECT 1 FROM pg_roles WHERE rolname='${APP_ROLE}'" 2>/dev/null | grep -q 1 \
  || "$PSQL" "$ADMIN" -c "CREATE ROLE ${APP_ROLE} LOGIN PASSWORD 'devpassword'"
"$PSQL" "$ADMIN" -tAc "SELECT 1 FROM pg_database WHERE datname='${APP_DB}'" | grep -q 1 \
  || "$PSQL" "$ADMIN" -c "CREATE DATABASE ${APP_DB} OWNER ${APP_ROLE}"

APP_DB_URL="postgresql://${ADMIN_USER}@${HOST}:${PORT}/${APP_DB}"

if [[ "${1:-}" == "--rebuild" ]]; then
  echo "→ --rebuild: dropping and recreating public schema (DESTROYS DATA)"
  "$PSQL" "$APP_DB_URL" -v ON_ERROR_STOP=1 -c \
    "DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION ${APP_ROLE}; GRANT ALL ON SCHEMA public TO public;"
fi

# Ensure the app role owns the schema so migrations (and the app) can write.
"$PSQL" "$APP_DB_URL" -c "ALTER SCHEMA public OWNER TO ${APP_ROLE}" >/dev/null 2>&1 || true

echo "→ applying migrations (alembic upgrade head)"
.venv/bin/alembic upgrade head

echo "→ done. current revision:"
.venv/bin/alembic current
