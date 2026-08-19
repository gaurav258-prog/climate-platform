"""PCAF financed-emissions + WACI math, end-to-end against Postgres.

The two headline SFDR carbon figures (PAI 1 financed emissions, PAI 2 carbon
footprint) plus WACI (PAI 3) are the numbers a manager files, so they get an
exact-arithmetic test with hand-checkable inputs. Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.fund_disclosure import fund_pai

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


@pytest.mark.integration
def test_pcaf_financed_emissions_and_waci_exact():
    """One issuer, chosen so the arithmetic is clean:
        scope1=1,000,000  scope2=500,000  scope3=8,500,000
        revenue=€10,000m  EVIC=€50,000m   position mv=€5m
      WACI            = (s1+s2)/(rev/1e6)            = 1,500,000 / 10,000 = 150
      attribution     = mv/EVIC                       = 5e6 / 5e10 = 1e-4
      financed total  = attribution × (s1+s2+s3)      = 1e-4 × 10,000,000 = 1,000
      carbon footprint= financed / (mv/1e6)           = 1,000 / 5 = 200
    """
    created = {}
    with get_session() as s:
        fid = str(s.execute(text(
            "INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
            "VALUES (:o,'TEST PCAF Fund','fund','article_8') RETURNING fund_id"), {"o": DEMO_ORG}).scalar())
        iid = str(s.execute(text(
            "INSERT INTO issuers (name,issuer_type,country,source) "
            "VALUES ('PCAF Test Issuer','corporate','DE','manual') RETURNING issuer_id")).scalar())
        sid = str(s.execute(text(
            "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
            "VALUES ('DE00PCAFTST1','PCAF Test Sec',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
        s.execute(text(
            "INSERT INTO issuer_emissions (issuer_id,reporting_year,scope1_tco2e,scope2_tco2e,scope3_tco2e,revenue_eur,evic_eur,source) "
            "VALUES (:i,2023,1000000,500000,8500000,10000000000,50000000000,'disclosed')"), {"i": iid})
        s.execute(text(
            "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
            "VALUES (:f,:s,5000000,100,'2026-07-12')"), {"f": fid, "s": sid})
        created = {"fid": fid, "iid": iid}

    try:
        with get_session() as s:
            pai = fund_pai(s, created["fid"])
        p = pai["pai"]
        assert p["pai_3_waci_tco2e_per_meur"] == 150.0
        assert p["pai_1_financed_emissions_tco2e"]["total"] == 1000
        assert p["pai_2_carbon_footprint_tco2e_per_meur"] == 200.0
        assert pai["financed_emissions_coverage_pct"] == 100.0
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": created["fid"]})
            s.execute(text("DELETE FROM securities WHERE isin='DE00PCAFTST1'"))
            s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": created["iid"]})


@pytest.mark.integration
def test_financed_emissions_partial_without_evic():
    """A holding with emissions but no EVIC contributes to WACI but NOT to
    financed emissions — coverage must reflect that, never silently attribute."""
    with get_session() as s:
        fid = str(s.execute(text(
            "INSERT INTO funds (org_id,name,fund_type) VALUES (:o,'TEST NoEVIC Fund','fund') RETURNING fund_id"),
            {"o": DEMO_ORG}).scalar())
        iid = str(s.execute(text(
            "INSERT INTO issuers (name,issuer_type,country,source) "
            "VALUES ('NoEVIC Issuer','corporate','DE','manual') RETURNING issuer_id")).scalar())
        sid = str(s.execute(text(
            "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
            "VALUES ('DE00NOEVIC01','NoEVIC Sec',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
        s.execute(text(
            "INSERT INTO issuer_emissions (issuer_id,reporting_year,scope1_tco2e,scope2_tco2e,revenue_eur,source) "
            "VALUES (:i,2023,100000,50000,1000000000,'disclosed')"), {"i": iid})
        s.execute(text(
            "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
            "VALUES (:f,:s,1000000,100,'2026-07-12')"), {"f": fid, "s": sid})
    try:
        with get_session() as s:
            pai = fund_pai(s, fid)
        assert pai["pai"]["pai_3_waci_tco2e_per_meur"] is not None       # WACI computable
        assert pai["pai"]["pai_1_financed_emissions_tco2e"] is None      # no EVIC → no financed figure
        assert pai["financed_emissions_coverage_pct"] == 0.0
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
            s.execute(text("DELETE FROM securities WHERE isin='DE00NOEVIC01'"))
            s.execute(text("DELETE FROM issuers WHERE name='NoEVIC Issuer' AND issuer_type='corporate'"))


@pytest.mark.integration
def test_esg_pai_5_to_14_computed():
    """PAI 5-14 compute from issuer_esg_metrics: value-weighted ratios, exposure
    shares for flags, and EVIC-attributed absolutes for water/waste."""
    from services.fund_disclosure import fund_esg_pai
    with get_session() as s:
        fid = str(s.execute(text(
            "INSERT INTO funds (org_id,name,fund_type) VALUES (:o,'TEST ESG PAI Fund','fund') RETURNING fund_id"),
            {"o": DEMO_ORG}).scalar())
        iid = str(s.execute(text(
            "INSERT INTO issuers (name,issuer_type,country,source) "
            "VALUES ('ESG Test Issuer','corporate','DE','manual') RETURNING issuer_id")).scalar())
        sid = str(s.execute(text(
            "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
            "VALUES ('DE00ESGTST1','ESG Sec',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
        s.execute(text(
            "INSERT INTO issuer_emissions (issuer_id,reporting_year,evic_eur,source) "
            "VALUES (:i,2023,50000000000,'disclosed')"), {"i": iid})
        s.execute(text(
            "INSERT INTO issuer_esg_metrics (issuer_id,reporting_year,non_renewable_energy_pct,"
            "biodiversity_sensitive_ops,emissions_to_water_tonnes,gender_pay_gap_pct,board_female_pct,"
            "controversial_weapons,source) VALUES (:i,2023,40,true,1000,15,35,false,'client')"), {"i": iid})
        s.execute(text(
            "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
            "VALUES (:f,:s,5000000,100,'2026-07-12')"), {"f": fid, "s": sid})
    try:
        with get_session() as s:
            esg = fund_esg_pai(s, fid)
        assert esg["pai_5"]["value"] == 40.0 and esg["pai_5"]["coverage_pct"] == 100.0   # energy share
        assert esg["pai_7"]["value"] == 100.0                                            # 100% of value flagged
        assert esg["pai_12"]["value"] == 15.0                                            # pay gap
        assert esg["pai_13"]["value"] == 35.0                                            # board diversity
        assert esg["pai_14"]["value"] == 0.0                                             # no weapons exposure
        # water attributed: (5e6/5e10)×1000 = 0.1 t; per €m invested = 0.1/(5e6/1e6)=0.02
        assert esg["pai_8"]["value"] == 0.02
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
            s.execute(text("DELETE FROM securities WHERE isin='DE00ESGTST1'"))
            s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": iid})


@pytest.mark.integration
def test_evic_attribution_capped_and_positive():
    """Regression (audit #1): a tiny/mis-keyed or non-positive EVIC must not
    inflate or invert financed emissions. Attribution factor is capped at 1.0."""
    from services.fund_disclosure import fund_pai
    with get_session() as s:
        fid = str(s.execute(text("INSERT INTO funds (org_id,name,fund_type) VALUES (:o,'TEST EVIC CAP','fund') RETURNING fund_id"), {"o": DEMO_ORG}).scalar())
        iid = str(s.execute(text("INSERT INTO issuers (name,issuer_type,country,source) VALUES ('EVIC Cap Co','corporate','DE','manual') RETURNING issuer_id")).scalar())
        sid = str(s.execute(text("INSERT INTO securities (isin,name,issuer_id,asset_class,source) VALUES ('DE00EVICCAP','x',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
        # mv 5m, evic 2m → uncapped af = 2.5; capped → 1.0 → financed = full scopes
        s.execute(text("INSERT INTO issuer_emissions (issuer_id,reporting_year,scope1_tco2e,scope2_tco2e,revenue_eur,evic_eur,source) VALUES (:i,2023,100000,50000,1000000000,2000000,'client')"), {"i": iid})
        s.execute(text("INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) VALUES (:f,:s,5000000,100,'2026-07-12')"), {"f": fid, "s": sid})
    try:
        with get_session() as s:
            fe = fund_pai(s, fid)["pai"]["pai_1_financed_emissions_tco2e"]
        assert fe["total"] == 150000  # = scope1+2 with af capped at 1.0 (not 375000 at af=2.5)
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
            s.execute(text("DELETE FROM securities WHERE isin='DE00EVICCAP'"))
            s.execute(text("DELETE FROM issuers WHERE name='EVIC Cap Co'"))


@pytest.mark.integration
def test_yoy_skips_incomparable_methods():
    """Regression (audit #2): a prior-year value of a different method (e.g. PAI 1
    un-attributed vs financed) must NOT produce a bogus change — no fabricated move."""
    from unittest.mock import MagicMock

    from ml.regulatory.sfdr_pai import _attach_prior_year
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = {
        "reference_year": 2022,
        "statement": {"indicators": [{"number": 1, "value": {"total": 40000000}, "method": "partial"}]},
    }
    inds = [{"number": 1, "value": {"total": 180000}, "method": "computed"}]
    meta = _attach_prior_year(session, "fid", 2023, inds)
    assert meta["available"] is True
    assert "change" not in inds[0]           # methods differ → no change computed
    assert inds[0]["prior_value"] == {"total": 40000000}
    assert "not comparable" in inds[0]["change_note"]
