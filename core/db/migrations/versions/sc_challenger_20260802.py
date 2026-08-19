"""Independent challenger for ranged crop calibrations — model-risk corroboration.

A ranged crop publishes a euro from an OLS line (champion) fitted on its per-year (hazard score,
climate-attributable loss) panel, gated at r²_oos ≥ 0.40. That is ONE method. This stores the verdict of
an INDEPENDENT second method — an isotonic (monotone, shape-agnostic) regression on the SAME panel — so a
published figure is corroborated, not single-method. Agreement is judged against the champion's own residual
scale (RMSE): agree / partial / diverge. A diverge is a real red flag and caps the confidence grade.

Derived (never typeable): the row is written only by scripts/compute_challengers.py from the stored panel.

Revision ID: sc_challenger_202608
Revises: webhooks_202608
"""
from alembic import op

revision = "sc_challenger_202608"
down_revision = "webhooks_202608"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS sc_commodity_challenger (
    commodity_id           UUID NOT NULL,
    origin                 VARCHAR(8) NOT NULL,
    hazard_driver          VARCHAR(24) NOT NULL,
    method                 VARCHAR(32) NOT NULL,
    n_years                INTEGER NOT NULL,
    mean_abs_divergence_pp NUMERIC(6,2),
    tolerance_pp           NUMERIC(6,2),
    ref_score              NUMERIC(5,1),
    champion_at_ref_pct    NUMERIC(7,2),
    challenger_at_ref_pct  NUMERIC(7,2),
    verdict                VARCHAR(12) NOT NULL CHECK (verdict IN ('agree','partial','diverge','insufficient')),
    challenger_version     VARCHAR(40) NOT NULL,
    computed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (commodity_id, origin, hazard_driver)
);
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sc_commodity_challenger")
