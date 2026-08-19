"""Entity-level PAI roll-up — one statement across ALL a manager's funds.

Two funds with different issuers; the entity WACI must be the value-weighted blend
across both, and the entity total value the sum. Requires PostgreSQL.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.db.session import get_session
from ml.regulatory.sfdr_pai import entity_pai_statement

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


@pytest.mark.integration
def test_entity_rollup_aggregates_across_funds():
    """Fund A: issuer WACI 100 @ €1m. Fund B: issuer WACI 300 @ €3m.
    Entity WACI = (100·1 + 300·3)/(1+3) = 1000/4 = 250. Entity value = €4m."""
    org = str(uuid.uuid4())
    created = {"funds": [], "issuers": [], "isins": []}
    with get_session() as s:
        s.execute(text("INSERT INTO organizations (org_id,name,type,country) VALUES (:o,'Entity Test Mgr','asset_manager','LU')"),
                  {"o": org})
        for tag, (rev, s1, mv) in {"A": (10_000_000_000, 1_000_000, 1_000_000),
                                    "B": (10_000_000_000, 3_000_000, 3_000_000)}.items():
            fid = str(s.execute(text(
                "INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
                "VALUES (:o,:n,'fund','article_8') RETURNING fund_id"), {"o": org, "n": f"Entity Fund {tag}"}).scalar())
            iid = str(s.execute(text(
                "INSERT INTO issuers (name,issuer_type,country,source) "
                "VALUES (:n,'corporate','DE','manual') RETURNING issuer_id"), {"n": f"Entity Issuer {tag}"}).scalar())
            isin = f"DE00ENT{tag}0001"
            sid = str(s.execute(text(
                "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
                "VALUES (:isin,'Sec',:i,'equity','manual') RETURNING security_id"), {"isin": isin, "i": iid}).scalar())
            # WACI = (s1+s2)/(rev/1e6); with s2=0, rev=10,000m → WACI = s1/10000
            s.execute(text(
                "INSERT INTO issuer_emissions (issuer_id,org_id,reporting_year,scope1_tco2e,scope2_tco2e,revenue_eur,source) "
                "VALUES (:i,:o,2023,:s1,0,:rev,'disclosed')"), {"i": iid, "o": org, "s1": s1, "rev": rev})
            s.execute(text(
                "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
                "VALUES (:f,:s,:mv,100,'2026-07-12')"), {"f": fid, "s": sid, "mv": mv})
            created["funds"].append(fid); created["issuers"].append(iid); created["isins"].append(isin)

    try:
        with get_session() as s:
            ent = entity_pai_statement(s, org)
        assert ent["entity"]["funds_count"] == 2
        assert ent["entity"]["total_value_eur"] == 4_000_000
        waci = next(i for i in ent["indicators"] if i["number"] == 3)["value"]
        assert waci == 250.0
        assert len(ent["per_fund"]) == 2
    finally:
        with get_session() as s:
            for fid in created["funds"]:
                s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
            for isin in created["isins"]:
                s.execute(text("DELETE FROM securities WHERE isin=:x"), {"x": isin})
            for iid in created["issuers"]:
                s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": iid})
            s.execute(text("DELETE FROM organizations WHERE org_id=:o"), {"o": org})
