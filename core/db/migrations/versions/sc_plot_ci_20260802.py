"""Expose the CMIP6 projection band (score_ci_lower/upper) on v_sc_plot_physical_risk.

WS4 (projections & uncertainty). canonical_scores already carries score_ci_lower/upper;
the projection path (scripts/score_crop_drought.py) now writes an honest CMIP6
model-disagreement band on every projected scenario×horizon (NULL on baseline/current,
where no warming is applied — an honest point, not a fabricated band). The plot view
dropped those columns, so nothing downstream could see the band. Re-create the view
carrying them through. Purely additive: same rows, two more (often-NULL) columns.

Revision ID: sc_plot_ci_202608
Revises: plot_irrigation_202608
"""
from alembic import op

revision = "sc_plot_ci_202608"
down_revision = "plot_irrigation_202608"
branch_labels = None
depends_on = None

_WITH_CI = """
CREATE OR REPLACE VIEW v_sc_plot_physical_risk AS
SELECT p.org_id,
       p.plot_id,
       p.supplier_id,
       p.commodity_id,
       p.h3_cell,
       cs.hazard_type,
       cs.risk_score::double precision       AS physical_risk_score,
       cs.scenario,
       cs.time_horizon,
       cs.model_version,
       cs.scored_at,
       cs.score_ci_lower::double precision    AS physical_risk_ci_lower,
       cs.score_ci_upper::double precision    AS physical_risk_ci_upper
FROM sc_sourcing_plots p
JOIN canonical_scores cs
  ON cs.h3_cell::text = p.h3_cell::text
 AND cs.valid_to IS NULL
 AND cs.score_lane::text = 'standing'::text;
"""

_WITHOUT_CI = """
CREATE OR REPLACE VIEW v_sc_plot_physical_risk AS
SELECT p.org_id,
       p.plot_id,
       p.supplier_id,
       p.commodity_id,
       p.h3_cell,
       cs.hazard_type,
       cs.risk_score::double precision AS physical_risk_score,
       cs.scenario,
       cs.time_horizon,
       cs.model_version,
       cs.scored_at
FROM sc_sourcing_plots p
JOIN canonical_scores cs
  ON cs.h3_cell::text = p.h3_cell::text
 AND cs.valid_to IS NULL
 AND cs.score_lane::text = 'standing'::text;
"""


def upgrade() -> None:
    op.execute(_WITH_CI)


def downgrade() -> None:
    op.execute(_WITHOUT_CI)
