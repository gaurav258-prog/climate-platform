"""ESRS E1 and the Taxonomy climate-adaptation objective scope the same asset the same way (audit T8).

Both cover climate-related physical hazards only; a geophysical (seismic/volcanic) worst-hazard site must
not count as materially exposed in either. The regression pins them to one shared CLIMATE scope and asserts
the Taxonomy report never lists a non-climate hazard as materially exposed. Requires PostgreSQL.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence import taxonomy_adaptation
from services.intelligence.hazard_scope import CLIMATE
from services.money.params import Method


def test_reports_share_one_climate_scope():
    # the Taxonomy report must reference the one climate scope — not a copy that can drift
    assert taxonomy_adaptation.CLIMATE is CLIMATE


@pytest.mark.integration
def test_taxonomy_lists_no_non_climate_hazard_as_exposed():
    with get_session() as s:
        orgs = s.execute(text(
            "SELECT org_id FROM organizations WHERE type='agriculture' OR name ILIKE '%Terra%' LIMIT 3"
        )).scalars().all()
        assert orgs, "no org to test against"
        for org in orgs:
            kpi = taxonomy_adaptation.adaptation_kpi(s, str(org), Method.of({("method.at_risk_level", None): 40.0}, date(2025, 12, 31)))
            hazards = kpi["physical_risk"]["hazards"]
            non_climate = [h for h in hazards if h not in CLIMATE]
            assert not non_climate, (
                f"Taxonomy adaptation listed non-climate hazard(s) {non_climate} for org {org} — "
                "must scope to CLIMATE like E1")
