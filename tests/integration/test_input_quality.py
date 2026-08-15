"""Input-quality fail-safe signals reach the filing gate (audit T4b). Requires PostgreSQL.

Three signals — coarse geocode (low_confidence), located-but-unscored (insufficient_data), rule-based
fallback (degraded) — must be flagged so a degraded input is fixed before filing, not filed silently.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.input_quality import input_quality_status
from services.intelligence.company_sites import list_sites_with_risk


@pytest.mark.integration
def test_list_sites_exposes_input_quality_flags():
    with get_session() as s:
        org = s.execute(text("SELECT org_id FROM sc_company_sites GROUP BY org_id "
                             "ORDER BY count(*) DESC LIMIT 1")).scalar()
        assert org, "no org with sites"
        rows = list_sites_with_risk(s, str(org))
        assert rows and all("low_confidence" in r and "insufficient_data" in r for r in rows)


@pytest.mark.integration
def test_coarse_geocode_is_flagged_and_gate_fails():
    with get_session() as s:
        org = str(s.execute(text("SELECT org_id FROM sc_company_sites GROUP BY org_id "
                                 "ORDER BY count(*) DESC LIMIT 1")).scalar())
        assert input_quality_status(s, org)["all_clear"], "demo baseline should be filing-grade"
        sid = str(uuid.uuid4())
        s.execute(text("""
            INSERT INTO sc_company_sites (site_id, org_id, name, site_type, latitude, longitude, h3_cell,
                                          confidence, geocode_precision, source)
            VALUES (:i, :o, 'T4b coarse test', 'other', 40.0, -3.7, '88abc', 0.3, 'country', 'test')
        """), {"i": sid, "o": org})
        try:
            st = input_quality_status(s, org)
            assert not st["all_clear"] and st["low_confidence_count"] >= 1
            assert any(x["name"] == "T4b coarse test" for x in st["low_confidence"])
        finally:
            s.execute(text("DELETE FROM sc_company_sites WHERE site_id=:i"), {"i": sid})
            s.commit()
