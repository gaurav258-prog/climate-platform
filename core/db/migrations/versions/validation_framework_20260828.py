"""Validation / backtesting framework — the append-only, immutable validation track record.

Two tables — validation_run (one backtest result, full provenance) and validation_sample (per-sample
predicted/observed drill-down) — plus an immutability trigger so no run can be altered or deleted after the
fact. This is the audit-grade record that turns the honesty gate from a posture into published, reproducible
proof. See ml/validation/metrics.py and services/validation/engine.py.

Revision ID: validation_framework_20260828
Revises: mlops_governance_20260828
"""
from alembic import op

revision = "validation_framework_20260828"
down_revision = "mlops_governance_20260828"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS validation_run (
            run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            model_id uuid REFERENCES model_registry(model_id),
            hazard_type varchar(50) NOT NULL,
            scope varchar(80),
            horizon varchar(20),
            kind varchar(20) NOT NULL,
            method varchar(30) NOT NULL,
            target_source varchar(120) NOT NULL,
            n_samples integer NOT NULL,
            metrics jsonb NOT NULL,
            skill_grade varchar(20) NOT NULL,
            passed_gate boolean NOT NULL,
            gate varchar(60),
            notes text,
            code_version varchar(60),
            data_vintage varchar(60),
            created_by varchar(255),
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_validation_run_hazard ON validation_run(hazard_type, created_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS validation_sample (
            sample_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id uuid NOT NULL REFERENCES validation_run(run_id),
            label varchar(120),
            predicted numeric(12,4),
            observed numeric(12,4),
            meta jsonb
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_validation_sample_run ON validation_sample(run_id)")
    # ── immutability: a validation record is audit evidence — no UPDATE, no DELETE ──
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_validation_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'validation records are append-only (audit evidence): % on % is not allowed',
                TG_OP, TG_TABLE_NAME;
        END; $$ LANGUAGE plpgsql;
    """)
    for t in ("validation_run", "validation_sample"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_immutable ON {t}")
        op.execute(f"CREATE TRIGGER trg_{t}_immutable BEFORE UPDATE OR DELETE ON {t} "
                   f"FOR EACH ROW EXECUTE FUNCTION prevent_validation_mutation()")


def downgrade() -> None:
    for t in ("validation_run", "validation_sample"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_immutable ON {t}")
    op.execute("DROP FUNCTION IF EXISTS prevent_validation_mutation()")
    op.execute("DROP TABLE IF EXISTS validation_sample")
    op.execute("DROP TABLE IF EXISTS validation_run")
