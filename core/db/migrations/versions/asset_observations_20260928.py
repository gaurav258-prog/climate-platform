"""Intake phase 3: every fact about an asset, per source, with its history — and the differences a person must look at.

asset_observations  append-only: one row each time a source states a fact (client: a file, an edit, the book as first
                    seen; Tellumen: a value we derive ourselves, e.g. the country under the coordinates). The live asset
                    row is the resolved value; this is where each source's own value and its history live.
asset_conflicts     where the client's value and ours differ: open until a person keeps the client's (the default —
                    principle 1), uses ours (a second person approves), or explains it. One open conflict per fact.

Revision ID: asset_observations_20260928
Revises: prior_filing_currency_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "asset_observations_20260928"
down_revision: Union[str, None] = "prior_filing_currency_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS asset_observations (
            observation_id  BIGSERIAL PRIMARY KEY,
            org_id          UUID NOT NULL,
            asset_table     TEXT NOT NULL,
            asset_id        UUID NOT NULL,
            field           TEXT NOT NULL,
            value           JSONB,
            source          TEXT NOT NULL CONSTRAINT ck_asset_obs_source CHECK (source IN ('client', 'tellumen')),
            method          TEXT NOT NULL,
            origin          TEXT,
            as_of           DATE,
            observed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_asset_obs_fact ON asset_observations "
               "(org_id, asset_table, asset_id, field, source, observation_id DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_asset_obs_origin ON asset_observations (origin)")
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_asset_observation_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'asset_observations is the history of what each source stated; % is blocked', TG_OP;
        END; $$ LANGUAGE plpgsql""")
    op.execute("DROP TRIGGER IF EXISTS trg_asset_obs_worm ON asset_observations")
    op.execute("CREATE TRIGGER trg_asset_obs_worm BEFORE UPDATE OR DELETE ON asset_observations "
               "FOR EACH ROW EXECUTE FUNCTION prevent_asset_observation_mutation()")

    op.execute("""
        CREATE TABLE IF NOT EXISTS asset_conflicts (
            conflict_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id                  UUID NOT NULL,
            asset_table             TEXT NOT NULL,
            asset_id                UUID NOT NULL,
            field                   TEXT NOT NULL,
            client_observation_id   BIGINT REFERENCES asset_observations(observation_id),
            tellumen_observation_id BIGINT REFERENCES asset_observations(observation_id),
            client_value            JSONB,
            tellumen_value          JSONB,
            rule                    TEXT NOT NULL,
            status                  TEXT NOT NULL DEFAULT 'open'
                                    CONSTRAINT ck_asset_conflict_status CHECK (status IN ('open', 'awaiting_approval', 'resolved')),
            resolution              TEXT CONSTRAINT ck_asset_conflict_resolution
                                    CHECK (resolution IS NULL OR resolution IN ('client', 'tellumen', 'explained', 'agreed')),
            note                    TEXT,
            resolved_by             UUID,
            resolved_at             TIMESTAMPTZ,
            approval_request_id     UUID,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_asset_conflict_resolved CHECK ((status = 'resolved') = (resolution IS NOT NULL))
        )""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_asset_conflict_open ON asset_conflicts (asset_table, asset_id, field) "
               "WHERE status <> 'resolved'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_asset_conflict_org ON asset_conflicts (org_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS asset_conflicts")
    op.execute("DROP TRIGGER IF EXISTS trg_asset_obs_worm ON asset_observations")
    op.execute("DROP TABLE IF EXISTS asset_observations")
    op.execute("DROP FUNCTION IF EXISTS prevent_asset_observation_mutation()")
