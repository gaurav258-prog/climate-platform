"""A loss result carries its range and its standing (E171).

The held-out test of the first measured damage curve (US residential flood, data/reference/vulnerability/
nfip_measured.json) passed on its range but failed on event totals, so a loss figure is not one number with one
status: it is a range (the curve's 10th–90th percentile band around the central value) and a standing under
data/reference/loss_protocol.json —

  published   the curve passed both tests on losses it was not built from
  held        the curve was tested and failed: the figure is shown with the test, never used
  untested    no observed losses exist to test the curve where the asset is: shown as a wide range, the gap named

  loss_results  + standing, eal_low_eur, eal_high_eur; loss_at_rp holds {rp: {low, central, high}}

Downgrade refuses while a loss result is recorded.

Revision ID: loss_band_20261006
Revises: loss_found_20261006
"""
from typing import Sequence, Union

from alembic import op

revision: str = "loss_band_20261006"
down_revision: Union[str, None] = "loss_found_20261006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-000000000171', 'refusal probe', 'reit', 'DE');
                INSERT INTO loss_runs (org_id, book, scenario, time_horizon, as_of, engine_version, inputs, n_assets, n_gaps)
                VALUES ('0bbe0bbe-0000-4000-8000-000000000171', 'realestate', 'baseline', 'current', '2026-10-06', 'probe', '{}', 1, 1);
                INSERT INTO loss_results (run_id, asset_kind, asset_id, peril, gap)
                SELECT run_id, 'portfolio_entity', gen_random_uuid(), 'flood', 'probe' FROM loss_runs WHERE engine_version = 'probe';""",
    "cleanup": """ALTER TABLE loss_results DISABLE TRIGGER trg_loss_results_guard;
                  ALTER TABLE loss_runs DISABLE TRIGGER trg_loss_runs_guard;
                  DELETE FROM loss_results WHERE run_id IN (SELECT run_id FROM loss_runs WHERE engine_version = 'probe');
                  DELETE FROM loss_runs WHERE engine_version = 'probe';
                  ALTER TABLE loss_results ENABLE TRIGGER trg_loss_results_guard;
                  ALTER TABLE loss_runs ENABLE TRIGGER trg_loss_runs_guard;
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-000000000171';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE loss_results
            ADD COLUMN standing     varchar(12) CHECK (standing IN ('published', 'held', 'untested')),
            ADD COLUMN eal_low_eur  numeric(18,2) CHECK (eal_low_eur >= 0),
            ADD COLUMN eal_high_eur numeric(18,2) CHECK (eal_high_eur >= 0),
            ADD CONSTRAINT ck_loss_results_standing CHECK ((gap IS NULL) = (standing IS NOT NULL)),
            ADD CONSTRAINT ck_loss_results_range CHECK (gap IS NOT NULL OR
                (eal_low_eur IS NOT NULL AND eal_high_eur IS NOT NULL AND eal_low_eur <= eal_eur AND eal_eur <= eal_high_eur));
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM loss_results) THEN
                RAISE EXCEPTION 'loss results are recorded — their range and standing cannot be removed';
            END IF;
        END $$;
        ALTER TABLE loss_results DROP CONSTRAINT ck_loss_results_range, DROP CONSTRAINT ck_loss_results_standing,
            DROP COLUMN eal_high_eur, DROP COLUMN eal_low_eur, DROP COLUMN standing;
    """)
