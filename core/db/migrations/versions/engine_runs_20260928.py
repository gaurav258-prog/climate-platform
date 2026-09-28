"""Intake phase 4: every engine run that produces a filing records exactly what it read and what it checked.

engine_runs  append-only: the input manifest (the book in scope — how many assets, their total, a fingerprint of every
             fact the engine read; the last data batch and fact statement it saw; the hazard scores' vintage; the
             differences still undecided), the output figures, the output checks and their verdict. A frozen snapshot
             names its run (report_snapshots.run_id), so a filing can later be compared with the book as it is now.

Revision ID: engine_runs_20260928
Revises: asset_observations_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "engine_runs_20260928"
down_revision: Union[str, None] = "asset_observations_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS engine_runs (
            run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL,
            report_type     TEXT NOT NULL,
            purpose         TEXT NOT NULL,
            entity_ids      JSONB,
            view            TEXT NOT NULL DEFAULT 'joint',
            basis           JSONB NOT NULL,
            inputs          JSONB NOT NULL,
            inputs_sha256   TEXT NOT NULL,
            outputs         JSONB NOT NULL,
            checks          JSONB NOT NULL,
            status          TEXT NOT NULL CONSTRAINT ck_engine_run_status CHECK (status IN ('pass', 'warn')),
            created_by      UUID,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_engine_runs_org ON engine_runs (org_id, report_type, created_at DESC)")
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_engine_run_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'engine_runs is the record of what a filing was computed from; % is blocked', TG_OP;
        END; $$ LANGUAGE plpgsql""")
    op.execute("DROP TRIGGER IF EXISTS trg_engine_run_worm ON engine_runs")
    op.execute("CREATE TRIGGER trg_engine_run_worm BEFORE UPDATE OR DELETE ON engine_runs "
               "FOR EACH ROW EXECUTE FUNCTION prevent_engine_run_mutation()")
    op.execute("ALTER TABLE report_snapshots ADD COLUMN IF NOT EXISTS run_id UUID REFERENCES engine_runs(run_id)")


def downgrade() -> None:
    op.execute("ALTER TABLE report_snapshots DROP COLUMN IF EXISTS run_id")
    op.execute("DROP TRIGGER IF EXISTS trg_engine_run_worm ON engine_runs")
    op.execute("DROP TABLE IF EXISTS engine_runs")
    op.execute("DROP FUNCTION IF EXISTS prevent_engine_run_mutation()")
