"""Model governance — lifecycle, drift and audit on the model registry.

Adds the governance lifecycle to `model_registry` (candidate → approved → active → retired, + challenger),
enforced by the publish gate (r² ≥ 0.40) in services/mlops/model_governance.py, plus two append-only tables:
`model_status_event` (transition audit / rollback trail) and `model_drift_observation` (drift monitoring).

Revision ID: mlops_governance_20260828
Revises: merge_heads_20260828
"""
from alembic import op

revision = "mlops_governance_20260828"
down_revision = "merge_heads_20260828"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE model_registry
          ADD COLUMN IF NOT EXISTS lifecycle_status varchar(20) NOT NULL DEFAULT 'candidate',
          ADD COLUMN IF NOT EXISTS r2_oos numeric(5,4),
          ADD COLUMN IF NOT EXISTS calibration_note text,
          ADD COLUMN IF NOT EXISTS approved_at timestamptz,
          ADD COLUMN IF NOT EXISTS approved_by varchar(255),
          ADD COLUMN IF NOT EXISTS retired_at timestamptz,
          ADD COLUMN IF NOT EXISTS superseded_by uuid
    """)
    # seed lifecycle for pre-existing rows: whatever is already active is 'active', the rest 'candidate'
    op.execute("UPDATE model_registry SET lifecycle_status = CASE WHEN is_active THEN 'active' ELSE 'candidate' END "
               "WHERE lifecycle_status = 'candidate'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS model_status_event (
            event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            model_id uuid NOT NULL REFERENCES model_registry(model_id),
            hazard_type varchar(50) NOT NULL,
            from_status varchar(20),
            to_status varchar(20) NOT NULL,
            actor varchar(255),
            reason text,
            r2_oos numeric(5,4),
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_model_status_event_model ON model_status_event(model_id, created_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS model_drift_observation (
            obs_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            model_id uuid NOT NULL REFERENCES model_registry(model_id),
            hazard_type varchar(50) NOT NULL,
            kind varchar(20) NOT NULL,
            metric varchar(40) NOT NULL,
            value numeric(10,5) NOT NULL,
            threshold numeric(10,5),
            breached boolean NOT NULL DEFAULT false,
            drift_window varchar(40),
            note text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_model_drift_hazard ON model_drift_observation(hazard_type, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_drift_observation")
    op.execute("DROP TABLE IF EXISTS model_status_event")
    op.execute("ALTER TABLE model_registry "
               "DROP COLUMN IF EXISTS lifecycle_status, DROP COLUMN IF EXISTS r2_oos, "
               "DROP COLUMN IF EXISTS calibration_note, DROP COLUMN IF EXISTS approved_at, "
               "DROP COLUMN IF EXISTS approved_by, DROP COLUMN IF EXISTS retired_at, "
               "DROP COLUMN IF EXISTS superseded_by")
