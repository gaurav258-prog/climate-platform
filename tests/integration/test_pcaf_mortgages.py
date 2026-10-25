"""PCAF mortgages through the real intake and the bank's live analytics (Part A, 3rd ed., §5.5): a bank's standard file
with its loan tape and its buildings' energy use lands, and its mortgages carry financed emissions with the data quality
score — or each its named gap. Service level inside a rolled-back transaction, plus the per-loan attributes door."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intake import pipeline, workbooks
from tests.integration.test_intake_every_sector import _org_and_admin
from tests.integration.test_intake_workbook import _filled

pytestmark = pytest.mark.integration
BOOK = {"currency": "EUR", "book_date": "2026-06-30"}


def _loan(ref: str, out: float, *, v0=None, vf=None, floor=None, cp="household", cls="mortgages", **extra) -> dict:
    return {"external_ref": ref, "asset_name": f"TEST-PCAF home {ref}", "asset_type": "residential_real_estate",
            "latitude": 52.52, "longitude": 13.40, "appraised_value_eur": 450_000, "sector": "Households",
            "outstanding_loan_balance_eur": out, "counterparty_sector": cp, "immovable_collateral": "residential",
            "pcaf_asset_class": cls, "property_value_at_origination_eur": v0, "property_value_fixed_eur": vf,
            "floor_area_m2": floor, "country": "DE", **extra}


def _energy(ref, source, basis, *, kwh=None, per_m2=None, buildings=None, ef=None, ef_type=None, year=2025) -> dict:
    return {"loan_ref": ref, "energy_source": source, "energy_basis": basis, "annual_kwh": kwh, "kwh_per_m2": per_m2,
            "buildings": buildings, "emission_factor_kg_per_kwh": ef, "emission_factor_type": ef_type, "energy_year": year}


def _sheet(out: dict, book: str) -> dict:
    return next(r for r in out["sheets"] if r["book"] == book)


def _mortgages(s, org_id) -> tuple[dict, dict]:
    from api.routers.bank import build_disclosure_snapshot
    snap = build_disclosure_snapshot(s, org_id, "baseline", "current")
    return snap["financed_emissions_pcaf"], snap


def test_a_banks_file_with_its_mortgages_and_their_energy_use_gives_financed_emissions_and_the_quality_score(
        session_rolled_back):
    """Three mortgages, by hand:
         A  300,000 / 400,000 at origination = 0.75 × gas 120 kWh/m² (energy label) × 100 m² × 0.2 kg = 2.4 t → 1.8 t, score 3
         B  200,000 / 400,000 fixed instead  = 0.50 × electricity 5,000 kWh metered × 0.4 kg (supplier's) = 2.0 t → 1.0 t, score 1
         C  100,000, no energy stated → the gap 'no energy'
       book: scope 1 = 1.8 → 2 t, scope 2 = 1.0 → 1 t, scope 1+2 = 2.8 → 3 t; covered 500,000 of 600,000 (83.3 %);
       weighted score (300,000 × 3 + 200,000 × 1) / 500,000 = 2.2."""
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "bank")
    a, b, c = f"{tag}-A", f"{tag}-B", f"{tag}-C"
    loans = [_loan(a, 300_000, v0=400_000, floor=100), _loan(b, 200_000, vf=400_000), _loan(c, 100_000, v0=250_000)]
    energy = [_energy(a, "natural_gas", "energy_label", per_m2=120, ef=0.2, ef_type="average"),
              _energy(b, "electricity", "metered", kwh=5_000, ef=0.4, ef_type="supplier_specific")]
    raw = _filled("bank", {"bank_assets": loans, "bank_building_energy": energy})

    checked = workbooks.check(s, org_id, "bank", raw, f"{tag}.xlsx", **BOOK)     # the energy sheet names this file's loans
    assert _sheet(checked, "bank_building_energy")["n_error"] == 0, _sheet(checked, "bank_building_energy")
    out = workbooks.submit(s, org_id, "bank", raw, f"{tag}.xlsx", user_id=user_id, **BOOK)
    assert _sheet(out, "bank_assets")["state"] == "imported", _sheet(out, "bank_assets")
    assert _sheet(out, "bank_building_energy")["state"] == "imported", _sheet(out, "bank_building_energy")

    pcaf, snap = _mortgages(s, org_id)
    m = pcaf["mortgages"]
    assert (m["n_loans"], m["n_with_emissions"], m["outstanding_eur"], m["covered_outstanding_eur"]) == (3, 2, 600_000, 500_000)
    assert (m["scope1"], m["scope2"], m["scope12"], m["coverage_pct"], m["dq_score"]) == (2, 1, 3, 83.3, 2.2)
    assert m["gaps"] == [{"reason": "no_energy", "n": 1, "outstanding_eur": 100_000}]
    assert m["property_value_basis"] == {"at_origination": 2, "latest_fixed": 1}
    per = {x["asset_name"]: x.get("pcaf_mortgage") for x in snap["assets"]}
    got = per[f"TEST-PCAF home {a}"]
    assert (got["attribution_factor"], got["financed_tco2e"], got["dq_option"]) == (0.75, pytest.approx(1.8), "2a")
    # the book's financed emissions now carry the mortgages: their scope 1 and 2 enter the total (§5.5 covers no scope 3)
    before = pcaf["attributed"]
    assert snap["financed_emissions_tco2e"]["scope1"] == (before["scope1"] or 0) + 2
    assert snap["financed_emissions_tco2e"]["total"] == (before["total"] or 0) + 3


def test_the_kri_shows_the_mortgages_figure_and_its_quality_score(session_rolled_back, monkeypatch):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "bank")
    raw = _filled("bank", {"bank_assets": [_loan(f"{tag}-A", 300_000, v0=400_000)],
                           "bank_building_energy": [_energy(f"{tag}-A", "heating_oil", "metered", kwh=10_000, ef=0.3,
                                                            ef_type="average")]})
    workbooks.submit(s, org_id, "bank", raw, f"{tag}.xlsx", user_id=user_id, **BOOK)
    from services.governance import kri_bank
    monkeypatch.setattr("services.intelligence.forward_risk.forward_risk", lambda *a, **k: {})   # not what is tested
    k = next(x for x in kri_bank.book_kri(s, org_id)["kpis"] if x["key"] == "fin_emissions")
    facts = {f["key"]: f["value"] for f in k["facts"]}
    assert facts["mortgages_financed"] == 2                 # 0.75 × 10,000 kWh × 0.3 kg = 2.25 t
    assert facts["mortgages_quality"] == 2.0 and facts["mortgages_with_figure"] == "1 of 1"
    assert k["value"] is not None


def test_a_fixed_property_value_stays_for_the_following_years(session_rolled_back):
    """§5.5: where the value at origination cannot be obtained, the latest value is used and fixed — a re-sent tape
    stating another one is refused for that loan; a blank keeps the one stored."""
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "bank")
    ref = f"{tag}-F"
    first = workbooks.submit(s, org_id, "bank", _filled("bank", {"bank_assets": [_loan(ref, 200_000, vf=400_000)]}),
                             f"{tag}-1.xlsx", user_id=user_id, **BOOK)
    assert _sheet(first, "bank_assets")["state"] == "imported"
    moved = workbooks.check(s, org_id, "bank", _filled("bank", {"bank_assets": [_loan(ref, 190_000, vf=450_000)]}),
                            f"{tag}-2.xlsx", **BOOK)
    said = " ".join(" ".join(e["problems"]) for e in _sheet(moved, "bank_assets")["errors"])
    assert "fixed for this loan at the value first stated (EUR 400,000.00)" in said
    blank = workbooks.submit(s, org_id, "bank", _filled("bank", {"bank_assets": [_loan(ref, 190_000)]}), f"{tag}-3.xlsx",
                             user_id=user_id, **BOOK)
    assert _sheet(blank, "bank_assets")["state"] == "imported"
    kept = s.execute(text("""SELECT CAST(x.property_value_fixed_eur AS FLOAT), CAST(x.outstanding_loan_balance_eur AS FLOAT)
                             FROM ext_banking x JOIN portfolio_entities e ON e.entity_id = x.entity_id
                             WHERE e.org_id = CAST(:o AS uuid) AND e.external_ref = :r"""), {"o": org_id, "r": ref}).one()
    assert tuple(kept) == (400_000.0, 190_000.0)
    no_id = {k: v for k, v in _loan("x", 1, vf=1).items() if k != "external_ref"}
    out = workbooks.check(s, org_id, "bank", _filled("bank", {"bank_assets": [no_id]}), f"{tag}-4.xlsx", **BOOK)
    assert "needs Your asset ID" in " ".join(" ".join(e["problems"]) for e in _sheet(out, "bank_assets")["errors"])


def test_e338_a_companys_mortgage_needs_no_enterprise_value_its_business_loan_does(session_rolled_back):
    """E338: a loan's EVIC was required for every company counterparty — also for a mortgage or a commercial real-estate
    loan, which PCAF attributes by the property's value, never by an enterprise value (§5.4, §5.5; 'no distinction is
    made between private or corporate mortgages', p. 87)."""
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, _ = _org_and_admin(s, "bank")
    company = {"cp": "non_financial_corporation"}
    rows = [_loan(f"{tag}-M", 1e6, v0=2e6, **company), _loan(f"{tag}-R", 1e6, cls="commercial_real_estate", **company),
            _loan(f"{tag}-B", 1e6, cls="business_loans_unlisted_equity", **company), _loan(f"{tag}-U", 1e6, cls=None, **company)]
    out = _sheet(workbooks.check(s, org_id, "bank", _filled("bank", {"bank_assets": rows}), f"{tag}.xlsx", **BOOK),
                 "bank_assets")
    assert out["n_valid"] == 2 and out["n_error"] == 2, out
    assert all("Counterparty EVIC is missing" in " ".join(e["problems"]) for e in out["errors"])
    assert sorted(e["row"] for e in out["errors"]) == [4, 5]          # the business loan and the loan of no class


def test_a_buildings_energy_rows_are_refused_with_a_reason_the_bank_can_act_on(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "bank")
    ref = f"{tag}-E"
    workbooks.submit(s, org_id, "bank", _filled("bank", {"bank_assets": [_loan(ref, 1e5, v0=2e5, floor=80)]}),
                     f"{tag}-1.xlsx", user_id=user_id, **BOOK)
    bad = [_energy(ref, "biomass", "metered", kwh=9_000, ef=0.02, ef_type="average"),
           _energy("NOT-A-LOAN", "electricity", "metered", kwh=1_000),
           _energy(ref, "natural_gas", "metered", per_m2=100),
           _energy(ref, "electricity", "metered", kwh=2_000, ef=0.4),
           _energy(ref, "lpg", "statistics_per_building", kwh=8_000),
           _energy(ref, "district_heating", "statistics_per_m2", per_m2=90, ef=0.15, ef_type="average")]
    out = _sheet(workbooks.check(s, org_id, "bank", _filled("bank", {"bank_building_energy": bad}), f"{tag}-2.xlsx", **BOOK),
                 "bank_building_energy")
    said = {e["row"]: " ".join(e["problems"]) for e in out["errors"]}
    assert "biogenic CO2" in said[2]
    assert "is not in your loan book" in said[3]
    assert "Energy per year (kWh) is required" in said[4]
    assert "say the emission factor type" in said[5]
    assert "Number of buildings is required" in said[6]
    assert out["n_valid"] == 1 and 7 not in said


def test_the_per_loan_attributes_backfill_a_mortgage_and_keep_a_fixed_value(intake_client):
    from services.ingest.portfolio_ingest import ingest_bank_assets
    from tests.integration.test_money_inputs import BANK_ORG
    tag = uuid.uuid4().hex[:8]
    ref = f"{tag}-P"
    base = {"asset_name": f"TEST-PCAF-ATTR-{tag}", "asset_type": "residential_real_estate", "latitude": 52.5,
            "longitude": 13.4, "appraised_value_eur": 4e5, "sector": "Households", "counterparty_sector": "household",
            "outstanding_loan_balance_eur": 2e5, "external_ref": ref}
    with get_session() as s:
        ingest_bank_assets(s, BANK_ORG, [base], dispatch_scoring=False)
        s.commit()
    try:
        up = intake_client.post("/v1/bank/assets/attributes/upload", headers=intake_client.maker, files={"file": (
            "a.csv", (f"external_ref,pcaf_asset_class,property_value_fixed_eur,floor_area_m2,currency,book_date\n"
                      f"{ref},mortgages,500000,85,EUR,2026-06-30\n").encode())})
        assert up.status_code == 200 and up.json()["n_updated"] == 1, up.text
        again = intake_client.post("/v1/bank/assets/attributes/upload", headers=intake_client.maker, files={"file": (
            "a.csv", f"external_ref,property_value_fixed_eur,currency,book_date\n{ref},510000,EUR,2026-06-30\n".encode())})
        assert again.json()["n_refused"] == 1 and "stays for the following years" in again.json()["refused"][0]["reason"]
        with get_session() as s:
            row = s.execute(text("""SELECT x.pcaf_asset_class, CAST(x.property_value_fixed_eur AS FLOAT),
                                           CAST(x.floor_area_m2 AS FLOAT)
                                    FROM ext_banking x JOIN portfolio_entities e ON e.entity_id = x.entity_id
                                    WHERE e.external_ref = :r"""), {"r": ref}).one()
            assert tuple(row) == ("mortgages", 500_000.0, 85.0)
    finally:
        with get_session() as s:
            ids = [r[0] for r in s.execute(text("SELECT entity_id FROM portfolio_entities WHERE external_ref = :r"), {"r": ref})]
            s.execute(text("DELETE FROM ext_banking WHERE entity_id = ANY(:i)"), {"i": ids})
            s.execute(text("DELETE FROM portfolio_entities WHERE entity_id = ANY(:i)"), {"i": ids})
            s.commit()


def test_a_household_loan_of_no_stated_class_is_counted_as_such(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "bank")
    before = _mortgages(s, org_id)[0]["class_not_stated"]["n"]
    workbooks.submit(s, org_id, "bank", _filled("bank", {"bank_assets": [_loan(f"{tag}-H", 1e5, cls=None)]}),
                     f"{tag}.xlsx", user_id=user_id, **BOOK)
    pcaf = _mortgages(s, org_id)[0]
    assert pcaf["class_not_stated"]["n"] == before + 1 and pcaf["mortgages"]["n_loans"] == 0


def test_an_imported_energy_sheet_is_reread_on_approval(session_rolled_back):
    """A sheet sent to a second person is re-read from the stored file: the building rows still find their loan."""
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "bank")
    ref = f"{tag}-Q"
    workbooks.submit(s, org_id, "bank", _filled("bank", {"bank_assets": [_loan(ref, 1e5, v0=2e5)]}), f"{tag}-1.xlsx",
                     user_id=user_id, **BOOK)
    rows = [_energy(ref, "electricity", "metered", kwh=3_000, ef=0.4, ef_type="average"),
            _energy(ref, "coal", "something else", kwh=1)]                       # a value outside the list: second person
    out = _sheet(workbooks.submit(s, org_id, "bank", _filled("bank", {"bank_building_energy": rows}), f"{tag}-2.xlsx",
                                  user_id=user_id, reason="One basis is written our own way; reviewed", **BOOK),
                 "bank_building_energy")
    assert out["state"] == "awaiting_approval", out
    done = pipeline.decide(s, org_id, out["batch_id"], "approved", user_id, "the electricity row is right")
    assert done["state"] == "imported" and done["n_landed"] == 1


def test_e339_the_financed_emissions_drills_list_each_loan_by_its_part_of_the_figure(session_rolled_back):
    """E339: the KRI's total counts a company only where it states all three scopes, yet its drill-down weighted every
    loan by its scopes with a missing one as 0; and a scope's bar sums attributed emissions, yet the loans under it were
    listed by their counterparty's gross emissions. Each loan is now listed by its part of the figure clicked."""
    from services.governance.kri import _kri_drivers
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "bank")
    half, home = f"{tag}-C", f"{tag}-M"
    company = _loan(half, 1e6, cp="non_financial_corporation", cls=None, counterparty_evic_eur=2e6)    # attribution 0.5
    raw = _filled("bank", {"bank_assets": [company, _loan(home, 300_000, v0=400_000)],
                           "bank_building_energy": [_energy(home, "natural_gas", "metered", kwh=20_000, ef=0.2,
                                                            ef_type="average")]})
    workbooks.submit(s, org_id, "bank", raw, f"{tag}.xlsx", user_id=user_id, **BOOK)
    s.execute(text("""UPDATE ext_banking SET ghg_emissions_scope1_tco2e = 2e9 WHERE entity_id =
                      (SELECT entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND external_ref = :r)"""),
              {"o": org_id, "r": half})                                             # scope 1 only, 2 billion tonnes gross

    def items(**seg):
        d = _kri_drivers(s, org_id, "bank_tcfd", "fin_emissions", **seg) or {"items": []}
        return {i["name"]: i["value"] for i in d["items"]}
    total = items()
    assert f"TEST-PCAF home {half}" not in total                 # one scope stated: not in the total, so not under it
    scope1 = items(seg_type="scope", seg_value="1")
    assert scope1[f"TEST-PCAF home {half}"] == 1_000_000_000       # attributed: 0.5 × 2 billion t, never the gross figure
    assert items(seg_type="scope", seg_value="2").get(f"TEST-PCAF home {half}") is None
