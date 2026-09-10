"""v_portfolio_entity_physical_risk without DISTINCT ON — the per-organisation filter now pushes into the join.

Current standing scores are unique per (h3_cell, hazard_type, scenario, time_horizon, score_lane) by the partial unique
index the scorers write against (valid_to IS NULL), so the DISTINCT ON the view carried was a defence against a
duplicate that cannot exist — and it forced Postgres to materialise and sort every entity's rows before applying
the caller's org/vertical filter (72k rows, an external sort, ~2.4 s per query). The plain join lets the filter
reach the indexes.

Revision ID: prisk_view_pushdown_20260910
Revises: scores_cell_scored_at_20260910
"""
from typing import Sequence, Union

from alembic import op

revision: str = "prisk_view_pushdown_20260910"
down_revision: Union[str, None] = "scores_cell_scored_at_20260910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLAIN = """
    CREATE OR REPLACE VIEW v_portfolio_entity_physical_risk AS
    SELECT e.org_id, e.entity_id, e.vertical, e.h3_cell, cs.hazard_type,
           cs.risk_score::double precision AS physical_risk_score, cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at,
           cs.score_ci_lower::double precision AS physical_risk_ci_lower, cs.score_ci_upper::double precision AS physical_risk_ci_upper,
           COALESCE(hr.headline, TRUE) AS headline_eligible
    FROM portfolio_entities e
    JOIN canonical_scores cs ON cs.h3_cell::text = e.h3_cell::text AND cs.valid_to IS NULL AND cs.score_lane::text = 'standing'::text
    LEFT JOIN hazard_relevance hr ON hr.hazard_type = cs.hazard_type::text AND hr.asset_class = 'buildings'
"""
_DISTINCT = """
    CREATE OR REPLACE VIEW v_portfolio_entity_physical_risk AS
    SELECT DISTINCT ON (e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon) e.org_id, e.entity_id, e.vertical, e.h3_cell, cs.hazard_type,
           cs.risk_score::double precision AS physical_risk_score, cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at,
           cs.score_ci_lower::double precision AS physical_risk_ci_lower, cs.score_ci_upper::double precision AS physical_risk_ci_upper,
           COALESCE(hr.headline, TRUE) AS headline_eligible
    FROM portfolio_entities e
    JOIN canonical_scores cs ON cs.h3_cell::text = e.h3_cell::text AND cs.valid_to IS NULL AND cs.score_lane::text = 'standing'::text
    LEFT JOIN hazard_relevance hr ON hr.hazard_type = cs.hazard_type::text AND hr.asset_class = 'buildings'
    ORDER BY e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC
"""


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_portfolio_entity_physical_risk")
    op.execute(_PLAIN)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_portfolio_entity_physical_risk")
    op.execute(_DISTINCT)
