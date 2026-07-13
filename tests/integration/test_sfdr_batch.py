"""SFDR batch orchestration — run statements across many funds, resumably.

Requires PostgreSQL.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.sfdr_batch import create_batch, run_batch, batch_status

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


@pytest.mark.integration
def test_batch_runs_and_is_resumable():
    org = str(uuid.uuid4())
    fund_ids = []
    with get_session() as s:
        s.execute(text("INSERT INTO organizations (org_id,name,type,country) "
                       "VALUES (:o,'Batch Mgr','asset_manager','LU')"), {"o": org})
        for n in range(3):
            fid = str(s.execute(text(
                "INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
                "VALUES (:o,:n,'fund','article_8') RETURNING fund_id"), {"o": org, "n": f"Batch Fund {n}"}).scalar())
            iid = str(s.execute(text(
                "INSERT INTO issuers (name,issuer_type,country,nace_code,source) "
                "VALUES (:n,'corporate','DE','35.11','manual') RETURNING issuer_id"), {"n": f"BI{n}"}).scalar())
            sid = str(s.execute(text(
                "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
                "VALUES (:x,'S',:i,'equity','manual') RETURNING security_id"),
                {"x": f"DE00BATCH0{n}", "i": iid}).scalar())
            s.execute(text("INSERT INTO issuer_emissions (issuer_id,org_id,reporting_year,scope1_tco2e,scope2_tco2e,revenue_eur,source) "
                           "VALUES (:i,:o,2023,1000,0,1000000000,'disclosed')"), {"i": iid, "o": org})
            s.execute(text("INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
                           "VALUES (:f,:s,1000000,100,'2026-07-12')"), {"f": fid, "s": sid})
            fund_ids.append((fid, iid, f"DE00BATCH0{n}"))

    try:
        with get_session() as s:
            bid = create_batch(s, org, 2023)
            # process only 2 of 3 first (chunked/resumable)
            r1 = run_batch(s, bid, limit=2)
            assert r1["progress"]["done"] == 2
            assert r1["status"] == "running"        # one still pending
            # resume — finishes the rest, recomputes nothing already done
            r2 = run_batch(s, bid)
            assert r2["progress"]["done"] == 3
            assert r2["status"] == "completed"
            st = batch_status(s, bid)
            assert st["total_funds"] == 3
            assert len(st["items"]) == 3
    finally:
        with get_session() as s:
            for fid, iid, isin in fund_ids:
                s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
                s.execute(text("DELETE FROM securities WHERE isin=:x"), {"x": isin})
                s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": iid})
            s.execute(text("DELETE FROM organizations WHERE org_id=:o"), {"o": org})
