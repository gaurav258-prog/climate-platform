"""hazard_relevance — which hazard scales are a standing risk for buildings and for agriculture (mirror of
core.hazard_relevance), and `headline_eligible` on the portfolio physical-risk view.

Revision ID: hazard_relevance_20260909
Revises: grc_remaining_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "hazard_relevance_20260909"
down_revision: Union[str, None] = "grc_remaining_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy.orm import Session

    from core.hazard_relevance import sync_table
    with Session(bind=op.get_bind()) as s:
        sync_table(s); s.commit()
    # the engine's view gains the eligibility flag for buildings (every portfolio vertical is a built asset)
    op.execute("""
        CREATE OR REPLACE VIEW v_portfolio_entity_physical_risk AS
        SELECT DISTINCT ON (e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon) e.org_id, e.entity_id, e.vertical, e.h3_cell, cs.hazard_type,
               cs.risk_score::double precision AS physical_risk_score, cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at,
               cs.score_ci_lower::double precision AS physical_risk_ci_lower, cs.score_ci_upper::double precision AS physical_risk_ci_upper,
               COALESCE(hr.headline, TRUE) AS headline_eligible
        FROM portfolio_entities e
        JOIN canonical_scores cs ON cs.h3_cell::text = e.h3_cell::text AND cs.valid_to IS NULL AND cs.score_lane::text = 'standing'::text
        LEFT JOIN hazard_relevance hr ON hr.hazard_type = cs.hazard_type::text AND hr.asset_class = 'buildings'
        ORDER BY e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW v_portfolio_entity_physical_risk AS
        SELECT DISTINCT ON (e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon) e.org_id, e.entity_id, e.vertical, e.h3_cell, cs.hazard_type,
               cs.risk_score::double precision AS physical_risk_score, cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at,
               cs.score_ci_lower::double precision AS physical_risk_ci_lower, cs.score_ci_upper::double precision AS physical_risk_ci_upper
        FROM portfolio_entities e
        JOIN canonical_scores cs ON cs.h3_cell::text = e.h3_cell::text AND cs.valid_to IS NULL AND cs.score_lane::text = 'standing'::text
        ORDER BY e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC
    """)
    op.execute("DROP TABLE IF EXISTS hazard_relevance")
