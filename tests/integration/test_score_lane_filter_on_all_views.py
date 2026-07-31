"""Every view that turns canonical_scores into a published/portfolio number MUST filter score_lane.

Audit finding F1: four physical-risk views (v_portfolio_entity, v_issuer_facility, v_insurance_policy,
v_assetmgmt_holding) joined canonical_scores on `valid_to IS NULL` only, picking `ORDER BY scored_at
DESC`. With a live nowcast row present, the nowcast (scored today) would win over the calibrated
standing climatology, making a bank haircut / SFDR climate-VaR a function of ingestion timing — the exact
bug the score_lane invariant exists to prevent. This test asserts the filter is present on *every* such
view, so a new view can't silently reintroduce the gap. Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session


@pytest.mark.integration
def test_all_physical_risk_views_filter_score_lane():
    with get_session() as s:
        rows = s.execute(text("""
            SELECT viewname, (definition ILIKE '%score_lane%') AS has_lane
            FROM pg_views
            WHERE schemaname = 'public'
              AND definition ILIKE '%canonical_scores%'
              AND viewname LIKE 'v_%physical_risk'
            ORDER BY viewname
        """)).all()
    assert rows, "no physical-risk views found over canonical_scores — schema changed?"
    missing = [name for name, has_lane in rows if not has_lane]
    assert not missing, (
        "these views over canonical_scores do NOT filter score_lane, so a live nowcast can "
        f"override the standing climatology in a published number: {missing}"
    )
