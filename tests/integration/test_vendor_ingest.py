"""Vendor feed connector — map + match + reconcile, with own > vendor precedence.

Requires PostgreSQL.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.fund_disclosure import fund_pai
from services.reference.vendor_ingest import ingest_vendor_extract

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


@pytest.mark.integration
def test_vendor_ingest_matches_and_client_wins():
    org = str(uuid.uuid4())
    created = {}
    with get_session() as s:
        s.execute(text("INSERT INTO organizations (org_id,name,type,country) "
                       "VALUES (:o,'Vendor Mgr','asset_manager','LU')"), {"o": org})
        fid = str(s.execute(text("INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
                                 "VALUES (:o,'Vendor Fund','fund','article_8') RETURNING fund_id"), {"o": org}).scalar())
        iid = str(s.execute(text("INSERT INTO issuers (name,issuer_type,country,source) "
                                 "VALUES ('Vendor Issuer','corporate','DE','manual') RETURNING issuer_id")).scalar())
        sid = str(s.execute(text("INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
                                 "VALUES ('DE00VEND0001','S',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
        # manager's OWN client figure: WACI = 1,000,000 / (10,000m/1e6... ) → s1=1,000,000, rev=10,000m → WACI 100
        s.execute(text("INSERT INTO issuer_emissions (issuer_id,org_id,reporting_year,scope1_tco2e,scope2_tco2e,revenue_eur,source) "
                       "VALUES (:i,:o,2023,1000000,0,10000000000,'client')"), {"i": iid, "o": org})
        s.execute(text("INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
                       "VALUES (:f,:s,5000000,100,'2026-07-12')"), {"f": fid, "s": sid})
        created = {"fid": fid, "iid": iid, "org": org}

    try:
        with get_session() as s:
            # vendor extract (MSCI profile) supplies a DIFFERENT scope1 for the same issuer + a new one that won't match
            rep = ingest_vendor_extract(s, org, [
                {"ISIN": "DE00VEND0001", "CARBON_EMISSIONS_SCOPE_1": 9999999, "SALES_EUR": 10000000000},
                {"ISIN": "XX00NOMATCH0", "CARBON_EMISSIONS_SCOPE_1": 5},
            ], profile="msci", reporting_year=2023)
            assert rep["matched_issuers"] == 1
            assert rep["unmatched_count"] == 1
            assert rep["client_conflicts"] == 1     # manager already had their own figure
            # precedence: client figure still wins → WACI stays 100, not the vendor's 1000
            pai = fund_pai(s, created["fid"])
        assert pai["pai"]["pai_3_waci_tco2e_per_meur"] == 100.0
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": created["fid"]})
            s.execute(text("DELETE FROM securities WHERE isin='DE00VEND0001'"))
            s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": created["iid"]})
            s.execute(text("DELETE FROM organizations WHERE org_id=:o"), {"o": created["org"]})


@pytest.mark.integration
def test_vendor_fills_when_no_client_figure():
    org = str(uuid.uuid4())
    created = {}
    with get_session() as s:
        s.execute(text("INSERT INTO organizations (org_id,name,type,country) "
                       "VALUES (:o,'Vendor Mgr2','asset_manager','LU')"), {"o": org})
        fid = str(s.execute(text("INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
                                 "VALUES (:o,'VF2','fund','article_8') RETURNING fund_id"), {"o": org}).scalar())
        iid = str(s.execute(text("INSERT INTO issuers (name,issuer_type,country,source) "
                                 "VALUES ('VI2','corporate','DE','manual') RETURNING issuer_id")).scalar())
        sid = str(s.execute(text("INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
                                 "VALUES ('DE00VEND0002','S',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
        s.execute(text("INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
                       "VALUES (:f,:s,5000000,100,'2026-07-12')"), {"f": fid, "s": sid})
        created = {"fid": fid, "iid": iid, "org": org}
    try:
        with get_session() as s:
            ingest_vendor_extract(s, org, [
                {"ISIN": "DE00VEND0002", "CARBON_EMISSIONS_SCOPE_1": 2000000, "SALES_EUR": 10000000000},
            ], profile="msci", reporting_year=2023)
            pai = fund_pai(s, created["fid"])
        # no client figure → vendor fills: WACI = 2,000,000 / 10,000 = 200
        assert pai["pai"]["pai_3_waci_tco2e_per_meur"] == 200.0
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": created["fid"]})
            s.execute(text("DELETE FROM securities WHERE isin='DE00VEND0002'"))
            s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": created["iid"]})
            s.execute(text("DELETE FROM organizations WHERE org_id=:o"), {"o": created["org"]})
