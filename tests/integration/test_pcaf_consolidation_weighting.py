"""PCAF exposure weighting (2026-09-23 C4 fix): outstanding_loan_balance_eur must be scaled by the same
consolidation weight already applied to primary_value_eur — otherwise a proportionally/equity-consolidated
bank's financed emissions silently overstate its owned share while value-at-risk/taxonomy € on the SAME
frozen snapshot are correctly weighted.

Requires PostgreSQL. Read-only against Meridian Bank's real book (no writes, no rollback needed) — uses
Meridian Leasing GmbH, a real 60%-owned 'proportional' entity in this org's live tree.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance import entities as E
from services.portfolio_engine import fetch_entities_with_risk
from api.routers.bank import EXT_BANKING_COLUMNS, _ltv_kwargs

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _leasing_entity_id(session):
    return session.execute(text(
        "SELECT entity_id::text FROM reporting_entities WHERE org_id=:o AND name='Meridian Leasing GmbH'"),
        {"o": BANK_ORG}).scalar()


@pytest.mark.integration
def test_outstanding_loan_balance_weighted_same_as_primary_value():
    with get_session() as s:
        leasing_id = _leasing_entity_id(s)
        assert leasing_id, "fixture entity missing — Meridian Leasing GmbH should exist in the demo org"

        method, pct = s.execute(text(
            "SELECT consolidation_method, ownership_pct::float FROM reporting_entities WHERE entity_id=:e"),
            {"e": leasing_id}).first()
        assert method == "proportional" and pct == 60.0   # the fixture this test depends on

        unweighted = fetch_entities_with_risk(
            s, BANK_ORG, "banking", "baseline", "current",
            ext_table="ext_banking", ext_columns=EXT_BANKING_COLUMNS, valuation_kwargs=_ltv_kwargs,
            entity_ids=[leasing_id], value_weights=None)
        weighted = fetch_entities_with_risk(
            s, BANK_ORG, "banking", "baseline", "current",
            ext_table="ext_banking", ext_columns=EXT_BANKING_COLUMNS, valuation_kwargs=_ltv_kwargs,
            entity_ids=[leasing_id], value_weights={leasing_id: 0.6})

        assert unweighted and weighted and len(unweighted) == len(weighted)
        by_id_u = {r["entity_id"]: r for r in unweighted}
        by_id_w = {r["entity_id"]: r for r in weighted}
        checked_any = False
        for eid, u in by_id_u.items():
            w = by_id_w[eid]
            if u["outstanding_loan_balance_eur"] is None or not u["outstanding_loan_balance_eur"]:
                continue
            checked_any = True
            # primary_value_eur and outstanding_loan_balance_eur scale by the SAME factor
            assert w["primary_value_eur"] == pytest.approx(u["primary_value_eur"] * 0.6, rel=1e-6)
            assert w["outstanding_loan_balance_eur"] == pytest.approx(
                u["outstanding_loan_balance_eur"] * 0.6, rel=1e-6)
            # counterparty EVIC is NEVER weighted — it's the counterparty's own value, not ours to scale
            if u.get("counterparty_evic_eur"):
                assert w["counterparty_evic_eur"] == u["counterparty_evic_eur"]
            # LTV is a ratio of two now-equally-scaled quantities — invariant under the weighting
            if u["valuation"]["original_ltv_pct"] is not None:
                assert w["valuation"]["original_ltv_pct"] == pytest.approx(
                    u["valuation"]["original_ltv_pct"], rel=1e-6)
        assert checked_any, "no loan-balance-bearing asset found in this fixture — test proves nothing"
