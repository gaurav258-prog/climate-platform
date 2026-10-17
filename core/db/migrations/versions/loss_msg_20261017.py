"""Loss results carry message codes (UI standard, product owner 2026-10-16; core/messages.py).

A reason a figure is missing, the defence basis and the publisher's caution are codes of the message catalogue with
their values; the screen renders the customer label and its detail from them. The text columns keep the label (new rows)
or the original wording (rows written before this revision, which stay as they were recorded).

  loss_results  + gap_code, gap_params (jsonb), protection_code, caution_code

Downgrade refuses while a code is recorded.

Revision ID: loss_msg_20261017
Revises: loss_prot_20261016
"""
from typing import Sequence, Union

from alembic import op

revision: str = "loss_msg_20261017"
down_revision: Union[str, None] = "loss_prot_20261016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORG = "0bbe0bbe-0000-4000-8000-0000000105e1"
RUN = "0bbe0bbe-0000-4000-8000-0000000105e2"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{ORG}', 'refusal probe', 'insurer', 'DE');
                INSERT INTO loss_runs (run_id, org_id, book, scenario, time_horizon, as_of, engine_version, inputs, n_assets, n_gaps)
                VALUES ('{RUN}', '{ORG}', 'insurance', 'baseline', 'current', '2026-10-17', 'probe', '{{}}', 1, 1);
                INSERT INTO loss_results (run_id, asset_kind, asset_id, peril, gap, gap_code)
                VALUES ('{RUN}', 'portfolio_entity', gen_random_uuid(), 'flood', 'No location', 'loss.gap.no_location');""",
    "cleanup": f"""ALTER TABLE loss_results DISABLE TRIGGER trg_loss_results_guard;
                  ALTER TABLE loss_runs DISABLE TRIGGER trg_loss_runs_guard;
                  DELETE FROM loss_results WHERE run_id = '{RUN}';
                  DELETE FROM loss_runs WHERE run_id = '{RUN}';
                  ALTER TABLE loss_runs ENABLE TRIGGER trg_loss_runs_guard;
                  ALTER TABLE loss_results ENABLE TRIGGER trg_loss_results_guard;
                  DELETE FROM organizations WHERE org_id = '{ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE loss_results
            ADD COLUMN gap_code        varchar(80),
            ADD COLUMN gap_params      jsonb,
            ADD COLUMN protection_code varchar(60),
            ADD COLUMN caution_code    varchar(60),
            ADD CONSTRAINT loss_results_gap_code_with_gap CHECK (gap_code IS NULL OR gap IS NOT NULL);
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM loss_results WHERE gap_code IS NOT NULL OR protection_code IS NOT NULL
                       OR caution_code IS NOT NULL) THEN
                RAISE EXCEPTION 'loss results carry message codes — they cannot be removed';
            END IF;
        END $$;
        ALTER TABLE loss_results DROP CONSTRAINT loss_results_gap_code_with_gap,
            DROP COLUMN caution_code, DROP COLUMN protection_code, DROP COLUMN gap_params, DROP COLUMN gap_code;
    """)
