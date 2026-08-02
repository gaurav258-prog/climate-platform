"""Harden v_sc_plot_physical_risk against duplicate active canonical rows (DISTINCT ON).

The financial per-asset views already de-duplicate with DISTINCT ON (...) ORDER BY scored_at DESC, so a
stray duplicate active canonical_scores row (e.g. a non-atomic check-then-insert race in an on-demand
point scorer) can never double-count there. The plot view was a plain JOIN and lacked that guard, so
one duplicate surfaced as a doubled (plot,hazard,scenario,horizon) row. Add the same DISTINCT ON guard
— it picks the most-recent canonical row per key and the crop-calendar overlay joins 1:1 onto it.

(The underlying duplicate rows were cleaned by retiring all but the latest per key. The durable
enforcement — a unique partial index on active rows + making every scorer retire/ON-CONFLICT — is a
tracked follow-on that needs a full writer audit; this view guard closes the surface now.)

Revision ID: sc_plot_distinct_202608
Revises: coastal_exposure_202608
"""
from alembic import op

revision = "sc_plot_distinct_202608"
down_revision = "coastal_exposure_202608"
branch_labels = None
depends_on = None

_WITH_DISTINCT = """
CREATE VIEW v_sc_plot_physical_risk AS
SELECT DISTINCT ON (p.plot_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       p.org_id, p.plot_id, p.supplier_id, p.commodity_id, p.h3_cell,
       cs.hazard_type,
       COALESCE(cal.risk_score, cs.risk_score)::double precision        AS physical_risk_score,
       cs.scenario, cs.time_horizon,
       COALESCE(cal.model_version, cs.model_version)                    AS model_version,
       COALESCE(cal.scored_at, cs.scored_at)                            AS scored_at,
       COALESCE(cal.score_ci_lower, cs.score_ci_lower)::double precision AS physical_risk_ci_lower,
       COALESCE(cal.score_ci_upper, cs.score_ci_upper)::double precision AS physical_risk_ci_upper
FROM sc_sourcing_plots p
JOIN canonical_scores cs
  ON cs.h3_cell::text = p.h3_cell::text AND cs.valid_to IS NULL AND cs.score_lane::text = 'standing'::text
LEFT JOIN sc_crop_calendar_score cal
  ON cal.h3_cell::text = p.h3_cell::text AND cal.commodity_id = p.commodity_id
 AND cal.origin::text = p.country::text AND cal.hazard_type::text = cs.hazard_type::text
 AND cal.scenario::text = cs.scenario::text AND cal.time_horizon::text = cs.time_horizon::text
 AND cal.valid_to IS NULL
ORDER BY p.plot_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;
"""

_WITHOUT_DISTINCT = """
CREATE VIEW v_sc_plot_physical_risk AS
SELECT p.org_id, p.plot_id, p.supplier_id, p.commodity_id, p.h3_cell,
       cs.hazard_type,
       COALESCE(cal.risk_score, cs.risk_score)::double precision        AS physical_risk_score,
       cs.scenario, cs.time_horizon,
       COALESCE(cal.model_version, cs.model_version)                    AS model_version,
       COALESCE(cal.scored_at, cs.scored_at)                            AS scored_at,
       COALESCE(cal.score_ci_lower, cs.score_ci_lower)::double precision AS physical_risk_ci_lower,
       COALESCE(cal.score_ci_upper, cs.score_ci_upper)::double precision AS physical_risk_ci_upper
FROM sc_sourcing_plots p
JOIN canonical_scores cs
  ON cs.h3_cell::text = p.h3_cell::text AND cs.valid_to IS NULL AND cs.score_lane::text = 'standing'::text
LEFT JOIN sc_crop_calendar_score cal
  ON cal.h3_cell::text = p.h3_cell::text AND cal.commodity_id = p.commodity_id
 AND cal.origin::text = p.country::text AND cal.hazard_type::text = cs.hazard_type::text
 AND cal.scenario::text = cs.scenario::text AND cal.time_horizon::text = cs.time_horizon::text
 AND cal.valid_to IS NULL;
"""


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_sc_plot_physical_risk;")
    op.execute(_WITH_DISTINCT)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_sc_plot_physical_risk;")
    op.execute(_WITHOUT_DISTINCT)
