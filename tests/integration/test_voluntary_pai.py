"""Voluntary (additional) PAI — selection + roll-up over supplied issuer values.

SFDR requires ≥1 additional environmental + ≥1 additional social indicator.
Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from ml.regulatory.voluntary_pai import compute_voluntary_pai, validate_keys

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


@pytest.mark.integration
def test_validate_keys_rejects_unknown():
    assert validate_keys(["t3_8", "not_a_key"]) == ["not_a_key"]
    assert validate_keys(["t3_8", "t3_5", "t2_6_1", "t2_13"]) == []
    assert validate_keys(["t2_5", "t2_18_1"]) == ["t2_5", "t2_18_1"]      # a breakdown / real-estate row: not offered


@pytest.mark.integration
def test_voluntary_rollup_weighted_and_share():
    created = {}
    with get_session() as s:
        fid = str(s.execute(text(
            "INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
            "VALUES (:o,'TEST VOL Fund','fund','article_8') RETURNING fund_id"), {"o": DEMO_ORG}).scalar())
        # two issuers, equal €1m weight each
        ids, sids = [], []
        for n in (1, 2):
            iid = str(s.execute(text(
                "INSERT INTO issuers (name,issuer_type,country,source) "
                "VALUES (:n,'corporate','DE','manual') RETURNING issuer_id"), {"n": f"VOL Issuer {n}"}).scalar())
            sid = str(s.execute(text(
                "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
                "VALUES (:isin,'VOL Sec',:i,'equity','manual') RETURNING security_id"),
                {"isin": f"DE00VOLTST0{n}", "i": iid}).scalar())
            s.execute(text(
                "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
                "VALUES (:f,:s,1000000,50,'2026-07-12')"), {"f": fid, "s": sid})
            ids.append(iid); sids.append(sid)
        # adopt one env (numeric) + one social (boolean) indicator
        for key in ("t2_6_1", "t3_5", "t2_13"):
            s.execute(text("INSERT INTO fund_voluntary_pai (fund_id,org_id,indicator_key) VALUES (:f,:o,:k)"),
                      {"f": fid, "o": DEMO_ORG, "k": key})
        # issuer 1: water 100, grievance True ; issuer 2: water 300, grievance False
        s.execute(text("INSERT INTO issuer_voluntary_pai (issuer_id,org_id,indicator_key,reporting_year,value_num) "
                       "VALUES (:i,:o,'t2_6_1',2023,100)"), {"i": ids[0], "o": DEMO_ORG})
        s.execute(text("INSERT INTO issuer_voluntary_pai (issuer_id,org_id,indicator_key,reporting_year,value_num) "
                       "VALUES (:i,:o,'t2_6_1',2023,300)"), {"i": ids[1], "o": DEMO_ORG})
        s.execute(text("INSERT INTO issuer_voluntary_pai (issuer_id,org_id,indicator_key,reporting_year,value_bool) "
                       "VALUES (:i,:o,'t3_5',2023,TRUE)"), {"i": ids[0], "o": DEMO_ORG})
        s.execute(text("INSERT INTO issuer_voluntary_pai (issuer_id,org_id,indicator_key,reporting_year,value_bool) "
                       "VALUES (:i,:o,'t3_5',2023,FALSE)"), {"i": ids[1], "o": DEMO_ORG})
        # waste (T2 no. 13, tonnes per € million invested): issuer 1 emits 50 t with EVIC €10m; issuer 2 has no EVIC
        s.execute(text("INSERT INTO issuer_voluntary_pai (issuer_id,org_id,indicator_key,reporting_year,value_num) "
                       "VALUES (:i,:o,'t2_13',2023,50)"), {"i": ids[0], "o": DEMO_ORG})
        s.execute(text("INSERT INTO issuer_voluntary_pai (issuer_id,org_id,indicator_key,reporting_year,value_num) "
                       "VALUES (:i,:o,'t2_13',2023,80)"), {"i": ids[1], "o": DEMO_ORG})
        s.execute(text("INSERT INTO issuer_emissions (issuer_id,org_id,reporting_year,source,evic_eur) "
                       "VALUES (:i,:o,2023,'disclosed',10000000)"), {"i": ids[0], "o": DEMO_ORG})
        created = {"fid": fid, "ids": ids}

    try:
        with get_session() as s:
            vol = compute_voluntary_pai(s, created["fid"])
        assert vol["adoption_compliant"] is True
        by_key = {i["key"]: i for i in vol["indicators"]}
        assert by_key["t2_6_1"]["row"] == "6.1" and "water consumed" in by_key["t2_6_1"]["metric"]
        # water: value-weighted mean of 100 & 300 at equal weight = 200
        assert by_key["t2_6_1"]["value"] == 200.0
        assert by_key["t2_6_1"]["coverage_pct"] == 100.0
        # grievance: 1 of 2 by value True = 50% of value
        assert by_key["t3_5"]["value"] == 50.0
        # waste: €1m / €10m × 50 t = 5 t attributed, over €2m invested = 2.5 t per € million; half the value covered
        assert by_key["t2_13"]["value"] == 2.5 and by_key["t2_13"]["coverage_pct"] == 50.0
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": created["fid"]})
            s.execute(text("DELETE FROM securities WHERE isin LIKE 'DE00VOLTST0%'"))
            for iid in created["ids"]:
                s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": iid})
