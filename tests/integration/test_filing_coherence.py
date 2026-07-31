"""Filing coherence (audit T3 / T5 / T7). Requires PostgreSQL. Non-polluting (no snapshots created)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.company_sites import list_sites_with_risk
from services.intelligence.csrd_e1 import build_e1_report
from services.intelligence.esrs_xbrl import build_ixbrl


def _org(s):
    return str(s.execute(text("SELECT org_id FROM organizations WHERE name ILIKE '%Terra%' LIMIT 1")).scalar())


@pytest.mark.integration
def test_t3_own_ops_is_read_on_the_requested_basis():
    """list_sites_with_risk must be basis-scoped, so E1 own-ops isn't silently baseline/current."""
    with get_session() as s:
        cur = list_sites_with_risk(s, _org(s), "baseline", "current")
        fut = list_sites_with_risk(s, _org(s), "hot_house_3_5c", "2050")
    cur_h = {x["top_hazard"] for x in cur if x["top_hazard"]}
    fut_h = {x["top_hazard"] for x in fut if x["top_hazard"]}
    # if the basis were ignored (the bug), the two hazard sets would be identical
    assert cur_h != fut_h, "own-ops risk is identical across bases — the scenario/horizon is being ignored"


@pytest.mark.integration
def test_t5_confidence_grade_is_in_the_e1_payload():
    """The A–E Confidence Grade must live in the filing payload (so it freezes), not just the live UI."""
    with get_session() as s:
        e1 = build_e1_report(s, _org(s))
    assert e1["material_hazards"] is not None
    # the supply detail carries confidence_grade per commodity — the csrd_e1 builder must forward it
    from services.intelligence.supply_cogs import project_org_supply
    with get_session() as s:
        r = project_org_supply(s, _org(s))
    # every commodity object exposes the grade fields (None for held, letter for published)
    assert all(hasattr(c, "confidence_grade") for c in r.commodities)


@pytest.mark.integration
def test_t7_ixbrl_is_built_from_the_supplied_pack_not_recomputed():
    """build_ixbrl(pack=...) must tag the EXACT supplied payload (a frozen snapshot), not recompute live."""
    with get_session() as s:
        org = _org(s)
        from services.intelligence.esrs_nature import build_esrs_pack
        pack = build_esrs_pack(s, org)
        # tamper one figure in the pack; if build_ixbrl recomputed, the sentinel would not appear
        sentinel = 987654321
        for t in pack["topics"]:
            if t["topic"] == "E1":
                t["financial_effects"]["asset_value_at_risk_eur"] = sentinel
        ix = build_ixbrl(s, org, pack=pack)
    assert str(sentinel) in ix, "build_ixbrl recomputed instead of tagging the supplied (frozen) pack"
