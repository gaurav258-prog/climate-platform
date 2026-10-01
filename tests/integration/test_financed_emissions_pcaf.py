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
      WACI            = (s1+s2+s3)/(rev/1e6)          = 10,000,000 / 10,000 = 1000
        (Annex I Table 1 defines investee GHG intensity as Scope 1+2+3)
      attribution     = mv/EVIC                       = 5e6 / 5e10 = 1e-4
      financed total  = attribution × (s1+s2+s3)      = 1e-4 × 10,000,000 = 1,000
      carbon footprint= financed / (total fund mv/1e6) = 1,000 / 5 = 200
        (single fully-covered position, so total fund value == EVIC-covered value)
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
        assert p["pai_3_waci_tco2e_per_meur"] == 1000.0
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
        assert pai["pai"]["pai_3_waci_s12_tco2e_per_meur"] is not None   # WACI on the scopes it states (1+2) computable
        assert pai["pai"]["pai_3_waci_tco2e_per_meur"] is None           # scope 3 not stated → never read as 0 (E76)
        assert pai["pai"]["pai_1_financed_emissions_tco2e"] is None      # no EVIC → no financed figure
        assert pai["financed_emissions_coverage_pct"] == 0.0
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
            s.execute(text("DELETE FROM securities WHERE isin='DE00NOEVIC01'"))
            s.execute(text("DELETE FROM issuers WHERE name='NoEVIC Issuer' AND issuer_type='corporate'"))


@pytest.mark.integration
def test_waci_denominator_is_total_fund_value_not_covered_subset():
    """Annex I Table 1's indicator-3 (WACI) formula denominator is 'current value of ALL investments'
    (verified verbatim against the actual Official Journal text) — the same total-fund-value denominator
    PAI 2/8/9 already correctly use, NOT the emissions-covered subset. Two holdings, only one with
    emissions data, chosen so the two possible denominators give different, hand-checkable answers:
        Holding A: s1=1,000,000  s2=0  s3=0  revenue=€10,000m  mv=€4m  (has emissions)
        Holding B: mv=€6m  (no emissions data at all — e.g. issuer hasn't reported)
        total_mv = €10m, covered_mv = €4m
        intensity_A = 1,000,000 / 10,000 = 100 tCO2e/€M
        WACI (correct, total_mv denominator)   = (4m × 100) / 10m = 40.0
        WACI (old, wrong, covered_mv denominator) = (4m × 100) / 4m = 100.0
    """
    created = {}
    with get_session() as s:
        fid = str(s.execute(text(
            "INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
            "VALUES (:o,'TEST WACI Denominator Fund','fund','article_8') RETURNING fund_id"),
            {"o": DEMO_ORG}).scalar())
        iid_a = str(s.execute(text(
            "INSERT INTO issuers (name,issuer_type,country,source) "
            "VALUES ('WACI Denom Issuer A','corporate','DE','manual') RETURNING issuer_id")).scalar())
        iid_b = str(s.execute(text(
            "INSERT INTO issuers (name,issuer_type,country,source) "
            "VALUES ('WACI Denom Issuer B','corporate','DE','manual') RETURNING issuer_id")).scalar())
        sid_a = str(s.execute(text(
            "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
            "VALUES ('DE00WACIDEN1','WACI Denom Sec A',:i,'equity','manual') RETURNING security_id"),
            {"i": iid_a}).scalar())
        sid_b = str(s.execute(text(
            "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
            "VALUES ('DE00WACIDEN2','WACI Denom Sec B',:i,'equity','manual') RETURNING security_id"),
            {"i": iid_b}).scalar())
        s.execute(text(
            "INSERT INTO issuer_emissions (issuer_id,reporting_year,scope1_tco2e,scope2_tco2e,scope3_tco2e,revenue_eur,source) "
            "VALUES (:i,2023,1000000,0,0,10000000000,'disclosed')"), {"i": iid_a})     # s2 = s3 = 0, STATED (E76)
        # Issuer B deliberately has NO issuer_emissions row — not held.
        s.execute(text(
            "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
            "VALUES (:f,:s,4000000,40,'2026-07-12')"), {"f": fid, "s": sid_a})
        s.execute(text(
            "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
            "VALUES (:f,:s,6000000,60,'2026-07-12')"), {"f": fid, "s": sid_b})
        created = {"fid": fid, "iid_a": iid_a, "iid_b": iid_b}
    try:
        with get_session() as s:
            pai = fund_pai(s, created["fid"])
        assert pai["pai"]["pai_3_waci_tco2e_per_meur"] == 40.0
        assert pai["emissions_coverage_pct"] == 40.0
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": created["fid"]})
            s.execute(text("DELETE FROM securities WHERE isin IN ('DE00WACIDEN1','DE00WACIDEN2')"))
            s.execute(text("DELETE FROM issuers WHERE issuer_id = ANY(:ids)"),
                      {"ids": [created["iid_a"], created["iid_b"]]})


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
        # all three scopes stated (scope 3 = 0): the total is over investees stating every scope (E79)
        s.execute(text("INSERT INTO issuer_emissions (issuer_id,reporting_year,scope1_tco2e,scope2_tco2e,scope3_tco2e,revenue_eur,evic_eur,source) VALUES (:i,2023,100000,50000,0,1000000000,2000000,'client')"), {"i": iid})
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
    assert "Not directly comparable" in inds[0]["change_note"] and "None%" not in inds[0]["change_note"]



def test_a_scope_an_investee_does_not_state_is_never_read_as_zero():
    """E76 (pure on fund_pai's rule): WACI sums scopes 1-3, so only investees stating all three enter it; the share of
    value it covers is disclosed. Here the only investee states scopes 1 and 2: WACI is not computed, WACI 1+2 is."""
    from unittest.mock import patch

    from services import fund_disclosure as FD
    rows = [{"mv": 4_000_000.0, "s1": 1_000_000.0, "s2": 0.0, "s3": None, "revenue_eur": 1e10, "evic_eur": None,
             "nace_code": "C24", "emissions_source": "disclosed", "issuer_id": "x", "issuer_name": "X"},
            {"mv": 6_000_000.0, "s1": None, "s2": None, "s3": None, "revenue_eur": None, "evic_eur": None,
             "nace_code": None, "emissions_source": None, "issuer_id": "y", "issuer_name": "Y"}]
    with patch.object(FD, "_positions_with_emissions", return_value=rows):
        p = FD.fund_pai(None, "f", fund_ids=["f"], org_id="o")["pai"]
    assert p["pai_3_waci_tco2e_per_meur"] is None and p["pai_3_coverage_pct"] == 0.0
    assert p["pai_3_waci_s12_tco2e_per_meur"] == 40.0 and p["pai_3_s12_coverage_pct"] == 40.0
    inv = p["pai_1_investee_emissions_tco2e"]
    assert inv["scope_3"] is None and inv["coverage_pct"]["scope_1"] == 40.0


@pytest.mark.integration
def test_each_pai_row_covers_exactly_the_investees_it_sums():
    """E79: an investee stating scope 1 only enters the scope-1 figures, never a total, PAI 2 or PAI 3 — and each
    statement row carries the coverage of the investees it sums (PAI 3 its own, not scope 1's)."""
    from ml.regulatory.sfdr_pai import _mandatory_indicator_rows
    from services.fund_disclosure import fund_pai
    with get_session() as s:
        fid = str(s.execute(text("INSERT INTO funds (org_id,name,fund_type) VALUES (:o,'TEST PAI COVER','fund') RETURNING fund_id"), {"o": DEMO_ORG}).scalar())
        for name, isin, mv, scopes in (("Cover Full Co", "DE00COVFULL", 6_000_000, (1000, 500, 2000)),
                                       ("Cover S1 Co", "DE00COVS1", 4_000_000, (3000, None, None))):
            iid = str(s.execute(text("INSERT INTO issuers (name,issuer_type,country,source) VALUES (:n,'corporate','DE','manual') RETURNING issuer_id"), {"n": name}).scalar())
            sid = str(s.execute(text("INSERT INTO securities (isin,name,issuer_id,asset_class,source) VALUES (:x,'x',:i,'equity','manual') RETURNING security_id"), {"x": isin, "i": iid}).scalar())
            s.execute(text("""INSERT INTO issuer_emissions (issuer_id,reporting_year,scope1_tco2e,scope2_tco2e,scope3_tco2e,revenue_eur,evic_eur,source)
                              VALUES (:i,2023,:a,:b,:c,100000000,60000000,'client')"""), {"i": iid, "a": scopes[0], "b": scopes[1], "c": scopes[2]})
            s.execute(text("INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) VALUES (:f,:s,:m,50,'2026-07-12')"),
                      {"f": fid, "s": sid, "m": mv})
    try:
        with get_session() as s:
            pai = fund_pai(s, fid)
        p = pai["pai"]
        fin = p["pai_1_financed_emissions_tco2e"]
        assert fin["scope_1"] == round(0.1 * 1000 + 4 / 60 * 3000) and fin["scope_2"] == 50
        assert fin["total"] == 350                                  # the full investee only: 0.1 × 3500
        assert fin["coverage_pct"] == {"scope_1": 100.0, "scope_2": 60.0, "scope_3": 60.0, "total": 60.0}
        assert p["pai_1_investee_emissions_tco2e"]["total"] == 3500
        assert p["pai_2_carbon_footprint_tco2e_per_meur"] == 35.0   # 350 / €10m — never mixing in scope 1 alone
        assert p["pai_3_coverage_pct"] == 60.0 and pai["emissions_coverage_pct"] == 100.0

        rows = {r["number"]: r for r in _mandatory_indicator_rows(pai, {})[0]}
        assert rows[1]["coverage_pct"] == 60.0 and rows[1]["coverage_by_scope"]["scope_1"] == 100.0
        assert rows[2]["coverage_pct"] == 60.0 and rows[2]["method"] == "partial"
        assert rows[3]["coverage_pct"] == 60.0 and rows[3]["method"] == "partial"
        assert "remaining 40.0%" in rows[3]["input_required"]
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
            s.execute(text("DELETE FROM securities WHERE isin IN ('DE00COVFULL','DE00COVS1')"))
            s.execute(text("DELETE FROM issuers WHERE name IN ('Cover Full Co','Cover S1 Co')"))
