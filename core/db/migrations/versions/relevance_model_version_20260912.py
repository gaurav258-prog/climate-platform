"""hazard_relevance keyed by model version — a scale belongs to a model, not to a hazard id.

Adds `model_version_prefix` ('' = the hazard's default scale; a non-empty prefix overrides it for model versions that
start with it), the SQL function `hazard_headline_eligible(hazard_type, asset_class, model_version)` (most specific
match wins; unknown hazards default to eligible, as before), and re-creates `v_portfolio_entity_physical_risk` so
`headline_eligible` is decided per row's model version. First override: subsidence under the observed EGMS model
(a measured intensity) may headline; the Herrera susceptibility class still never does.

Revision ID: relevance_model_version_20260912
Revises: tide_gauge_extremes_20260910
"""
from typing import Sequence, Union

from alembic import op

revision: str = "relevance_model_version_20260912"
down_revision: Union[str, None] = "tide_gauge_extremes_20260910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FUNCTION = """
    CREATE OR REPLACE FUNCTION hazard_headline_eligible(hz TEXT, cls TEXT, mv TEXT) RETURNS BOOLEAN
    LANGUAGE sql STABLE AS $$
        SELECT COALESCE(
            (SELECT headline FROM hazard_relevance
             WHERE hazard_type = hz AND asset_class = cls
               AND (model_version_prefix = '' OR (mv IS NOT NULL AND mv LIKE model_version_prefix || '%'))
             ORDER BY length(model_version_prefix) DESC LIMIT 1),
            TRUE)
    $$
"""
_VIEW = """
    CREATE OR REPLACE VIEW v_portfolio_entity_physical_risk AS
    SELECT e.org_id, e.entity_id, e.vertical, e.h3_cell, cs.hazard_type,
           cs.risk_score::double precision AS physical_risk_score, cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at,
           cs.score_ci_lower::double precision AS physical_risk_ci_lower, cs.score_ci_upper::double precision AS physical_risk_ci_upper,
           hazard_headline_eligible(cs.hazard_type::text, 'buildings', cs.model_version::text) AS headline_eligible
    FROM portfolio_entities e
    JOIN canonical_scores cs ON cs.h3_cell::text = e.h3_cell::text AND cs.valid_to IS NULL AND cs.score_lane::text = 'standing'::text
"""
_VIEW_BEFORE = """
    CREATE OR REPLACE VIEW v_portfolio_entity_physical_risk AS
    SELECT e.org_id, e.entity_id, e.vertical, e.h3_cell, cs.hazard_type,
           cs.risk_score::double precision AS physical_risk_score, cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at,
           cs.score_ci_lower::double precision AS physical_risk_ci_lower, cs.score_ci_upper::double precision AS physical_risk_ci_upper,
           COALESCE(hr.headline, TRUE) AS headline_eligible
    FROM portfolio_entities e
    JOIN canonical_scores cs ON cs.h3_cell::text = e.h3_cell::text AND cs.valid_to IS NULL AND cs.score_lane::text = 'standing'::text
    LEFT JOIN hazard_relevance hr ON hr.hazard_type = cs.hazard_type::text AND hr.asset_class = 'buildings' AND hr.model_version_prefix = ''
"""


def upgrade() -> None:
    op.execute("ALTER TABLE hazard_relevance ADD COLUMN IF NOT EXISTS model_version_prefix TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE hazard_relevance DROP CONSTRAINT IF EXISTS hazard_relevance_pkey")
    op.execute("ALTER TABLE hazard_relevance ADD PRIMARY KEY (hazard_type, asset_class, model_version_prefix)")
    op.execute(_FUNCTION)
    op.execute("DROP VIEW IF EXISTS v_portfolio_entity_physical_risk")
    op.execute(_VIEW)
    from sqlalchemy.orm import Session

    from core.hazard_relevance import sync_table
    sync_table(Session(bind=op.get_bind()))


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_portfolio_entity_physical_risk")
    op.execute(_VIEW_BEFORE)
    op.execute("DROP FUNCTION IF EXISTS hazard_headline_eligible(TEXT, TEXT, TEXT)")
    op.execute("DELETE FROM hazard_relevance WHERE model_version_prefix <> ''")
    op.execute("ALTER TABLE hazard_relevance DROP CONSTRAINT IF EXISTS hazard_relevance_pkey")
    op.execute("ALTER TABLE hazard_relevance ADD PRIMARY KEY (hazard_type, asset_class)")
