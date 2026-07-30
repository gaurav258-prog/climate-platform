"""Regulated-side ops hardening: geocode cache + golden-source refresh log.

Two small tables that turn two "demo-grade" corners into production-grade ones:
  - `geocode_cache` — persist resolved addresses so bulk supplier uploads don't hammer the geocoder
    (Nominatim's public instance rate-limits hard). Keyed on (provider, normalized query, limit).
  - `feed_refresh_log` — an append-only record of each golden-source refresh, so a compliance officer
    can see how current the hazard/reference data under a filing is and when it was last pulled.

Revision ID: regside_ops_20260730
Revises: report_snapshots_20260730
"""
from alembic import op

revision = "regside_ops_20260730"
down_revision = "report_snapshots_20260730"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            provider     TEXT NOT NULL,
            query_norm   TEXT NOT NULL,
            limit_n      INTEGER NOT NULL,
            results      JSONB NOT NULL,
            hit_count    INTEGER NOT NULL DEFAULT 0,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (provider, query_norm, limit_n)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS feed_refresh_log (
            refresh_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            feed_key     TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'refreshed',
            note         TEXT,
            actor_user_id UUID REFERENCES users(user_id),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_feed_refresh_log_feed ON feed_refresh_log (feed_key, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feed_refresh_log")
    op.execute("DROP TABLE IF EXISTS geocode_cache")
