"""Pillar 3 Templates 2, 6, 7, 8, 9.1-9.3 against their specification — a golden book with hand-worked answers, run
under every adopted version. Rules (Annex XL + the spec's declared readings):

  T7 rows by FINREP counterparty, sub-sector and instrument; NFCs only when their NFRD status is stated; row 50 is the
     whole book; rows under 'excluded' headings carry the gross carrying amount only
  General-purpose lending to an undertaking is valued by the counterparty's turnover KPIs ('based on the turnover
     alignment of the counterparty for the general purpose lending part only', Annex XL Template 8 para 4 — the one
     valuation in services.governance.taxonomy_valuation); households and specific-purpose lending by their own status
  CCM / CCA columns only where the objective is stated (the counterparty's KPI or the exposure's own objective)
  T8 = T7 amount ÷ T7 row 45 (covered assets); flows = exposures originated in the reporting year
  T2 = loans by immovable collateral, EU / non-EU (Eurostat membership), EP-score buckets and EPC labels
"""
from datetime import date

import pytest

import services.regspec as R
from services.governance import pillar3_gar as G

ADOPTED = [s["version"] for s in R.versions("bank_p3esg") if s["status"] == "adopted"]
PE = date(2025, 12, 31)


def _a(gross, **kw):
    return {"outstanding_loan_balance_eur": gross, "country": kw.pop("country", "DE"), "hazards": [], **kw}


BOOK = [
    # credit institution, general-purpose loan, originated in 2025; the counterparty's turnover-based GAR (its KPI):
    # wholly CCM-aligned and enabling
    _a(100, nace_code="64.19", counterparty_sector="credit_institution", loan_origination_date="2025-03-01",
       counterparty_taxonomy_kpi={"turnover:ccm": {"eligible": 100, "aligned": 100, "enabling": 100}}),
    # NFRD corporate, equity (general purpose); the counterparty's turnover is wholly CCA-eligible, alignment not stated
    _a(200, nace_code="35.11", counterparty_sector="non_financial_corporation", nfrd_subject=True,
       instrument_type="equity_instruments", counterparty_taxonomy_kpi={"turnover:cca": {"eligible": 100}}),
    # household mortgage on residential property, EPC B, EP score 80, estimated
    _a(300, asset_type="residential_real_estate", counterparty_sector="household", immovable_collateral="residential",
       epc_label="B", ep_score_kwh_m2=80, ep_score_estimated=True, taxonomy_status="not_eligible"),
    # EU SME not subject to NFRD, commercial property collateral, EP score 250 → BTAR
    _a(400, nace_code="68.20", counterparty_sector="non_financial_corporation", nfrd_subject=False,
       immovable_collateral="commercial", ep_score_kwh_m2=250),
    # non-EU corporate not subject to NFRD
    _a(50, nace_code="10.11", counterparty_sector="non_financial_corporation", nfrd_subject=False, country="US"),
    # central government bond → excluded from both numerator and denominator
    _a(70, nace_code="84.11", counterparty_sector="general_government", counterparty_govt_level="central",
       instrument_type="debt_securities"),
    # a corporate that does not state NFRD status → in Total assets only
    _a(30, nace_code="25.11"),
]


@pytest.mark.parametrize("version", ADOPTED)
def test_template7_golden_book(version):
    t7 = G.build(R.load("bank_p3esg", version), BOOK, PE)["T7"]
    assert (t7["3"]["a"], t7["4"]["a"]) == (100, 100)                   # credit institution, loans and advances
    assert (t7["20"]["a"], t7["23"]["a"]) == (200, 200)                 # NFRD corporate, equity instruments
    assert (t7["24"]["a"], t7["25"]["a"]) == (300, 300)                 # household, residential collateral
    assert t7["1"]["a"] == 600 and t7["32"]["a"] == 600
    assert (t7["33"]["a"], t7["37"]["a"]) == (400, 50)                  # non-NFRD: EU and non-EU
    assert t7["45"]["a"] == 1050 and t7["46"]["a"] == 70 and t7["49"]["a"] == 70
    assert t7["50"]["a"] == 1150                                        # every asset, incl. the unclassified 30
    assert (t7["32"]["b"], t7["32"]["c"], t7["32"]["f"]) == (100, 100, 100)     # CCM eligible / aligned / enabling
    assert (t7["32"]["g"], t7["32"]["h"]) == (200, 0)                   # CCA eligible; the row's alignment is established elsewhere
    assert t7["20"]["m"] is None and t7["20"]["l"] == 200               # eligible only: alignment unknown, blank — never 0
    assert (t7["32"]["l"], t7["32"]["m"]) == (300, 100)                 # TOTAL eligible / aligned
    assert t7["33"]["b"] is None and t7["33"].get("_gross_only")        # excluded rows: gross only


@pytest.mark.parametrize("version", ADOPTED)
def test_template8_6_and_btar_follow_from_the_amounts(version):
    g = G.build(R.load("bank_p3esg", version), BOOK, PE)
    r1 = g["T8"]["1"]
    assert r1["k"] == round(100 * 300 / 1050, 2)                       # TOTAL eligible ÷ covered assets (T7 col l)
    assert r1["l"] == round(100 * 100 / 1050, 2)                       # of which aligned: the GAR (T7 col m; T6 reads it)
    assert r1["p"] == round(100 * 1050 / 1150, 2)                      # covered over total assets
    assert r1["ab"] == 100.0                                            # flow: the 2025 loan is aligned, all new covered
    assert g["T6"]["r1"]["c3"] == r1["l"] and g["T6"]["r2"]["c4"] == r1["af"]
    t91 = g["T9_1"]
    assert t91["1"]["a"] == 600 and (t91["2"]["a"], t91["4"]["a"], t91["8"]["a"]) == (400, 400, 50)
    assert t91["12"]["a"] == 1050 and t91["19"]["a"] == 1150


@pytest.mark.parametrize("version", ADOPTED)
def test_template2_golden_book(version):
    t2 = G.build(R.load("bank_p3esg", version), BOOK, PE)["T2"]
    assert (t2["1"]["a"], t2["2"]["a"], t2["3"]["a"]) == (700, 400, 300)   # EU: all, commercial, residential
    assert (t2["1"]["b"], t2["1"]["d"]) == (300, 400)                   # EP ≤ 100 and 200-300 buckets
    assert (t2["1"]["i"], t2["1"]["o"]) == (300, 400)                   # EPC B; without an EPC label
    assert t2["5"]["a"] == 300 and t2["1"]["p"] == 300                  # EP score estimated
    assert t2["6"]["a"] == 0                                            # nothing collateralised outside the EU
