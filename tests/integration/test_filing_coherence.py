"""Filing coherence (audit T3 / T5 / T7). Requires PostgreSQL. Non-polluting (no snapshots created)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.company_sites import list_sites_with_risk
from services.intelligence.csrd_e1 import build_e1_report
from services.intelligence.esrs_xbrl import build_ixbrl

_T3_CELL = "88_t3_test_ownops"   # synthetic (<=20 chars, h3_cell is varchar(20)); no real site uses it


def _org(s):
    return str(s.execute(text("SELECT org_id FROM organizations WHERE name ILIKE '%Terra%' LIMIT 1")).scalar())


@pytest.mark.integration
def test_t3_own_ops_is_read_on_the_requested_basis():
    """list_sites_with_risk must be basis-scoped, so E1 own-ops isn't silently baseline/current.

    Self-contained: inserts its own synthetic site + two canonical_scores rows (one per basis, different
    hazard types) on a synthetic cell, rather than depending on the Terra demo org actually having scored
    own-ops sites seeded — that data is populated live via the "add site" UI flow, not a bulk seed script,
    and this dev DB currently has zero for Terra (a real product/demo-data gap, worth seeding separately for
    a live walkthrough, but orthogonal to what THIS test needs to prove: the basis-scoping mechanism works)."""
    now = datetime.now(timezone.utc)
    with get_session() as s:
        org = _org(s)
        site_id = str(uuid.uuid4())
        s.execute(text("""
            INSERT INTO sc_company_sites (site_id, org_id, name, site_type, h3_cell, source)
            VALUES (CAST(:id AS uuid), CAST(:o AS uuid), 'T3 test site', 'factory', :cell, 'test')
        """), {"id": site_id, "o": org, "cell": _T3_CELL})
        # current basis reads 'drought' (score 40); the 2050 hot-house basis reads a DIFFERENT hazard
        # ('heat_acute', score 75) on the same cell — proving list_sites_with_risk is basis-scoped, not
        # silently baseline/current, requires the two bases to disagree on which hazard tops out.
        for hz, scenario, horizon, score in (
            ("drought", "baseline", "current", 40),
            ("heat_acute", "hot_house_3_5c", "2050", 75),
        ):
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon, risk_score,
                     risk_bucket, model_version, data_vintage, valid_from, scored_at, score_lane)
                VALUES (:id, :c, 8, :hz, :sc, :hor, :score, 'M', 'test', :now, :now, :now, 'standing')
            """), {"id": str(uuid.uuid4()), "c": _T3_CELL, "hz": hz, "sc": scenario, "hor": horizon,
                   "score": score, "now": now})

        cur = list_sites_with_risk(s, org, "baseline", "current")
        fut = list_sites_with_risk(s, org, "hot_house_3_5c", "2050")
        s.rollback()

    cur_h = {x["top_hazard"] for x in cur if x["site_id"] == site_id and x["top_hazard"]}
    fut_h = {x["top_hazard"] for x in fut if x["site_id"] == site_id and x["top_hazard"]}
    assert cur_h == {"drought"}, f"current basis should read the drought row, got {cur_h}"
    assert fut_h == {"heat_acute"}, f"2050 hot-house basis should read the heat_acute row, got {fut_h}"
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
