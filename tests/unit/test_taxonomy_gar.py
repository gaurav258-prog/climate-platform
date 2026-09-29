"""Golden book for the credit-institution Taxonomy templates (Annex VI of Del. Reg. 2021/2178), computed by hand from
Annex V's method and checked against services.governance.taxonomy_gar in two versions (2023/2486 and 2026/73).

  A  non-financial undertaking subject to NFRD/CSRD, general-purpose loan 100; its KPIs: turnover CCM eligible 50 %,
     aligned 30 %, transitional 5 %, enabling 10 %; CapEx CCM eligible 60 %, aligned 40 %
  B  the same kind of counterparty, debt security 50; KPIs: turnover CCM aligned 20 %, CapEx CCM aligned 60 %
  C  household mortgage 200, residential collateral, stated aligned to CCM
  D  EU non-financial undertaking NOT subject to NFRD/CSRD, loan 80
  E  derivative with a credit institution, 30
  F  central government, 70
  G  NFRD/CSRD non-financial undertaking, loan 40, no KPIs on file
  H  NFRD/CSRD non-financial undertaking, specialised loan 60, stated aligned to CCM, enabling

Numerator A+B+C+G+H = 450. 2023/2486: D and E are excluded from the numerator (covered 560), F not covered, total 630.
2026/73: derivatives and non-CSRD counterparties leave the denominator — covered 450, not covered D+E+F = 180.
Aligned (all objectives), turnover-based: A 30 + B 10 + C 200 + H 60 = 300 (G unknown). CapEx-based: general lending
uses the turnover KPI (A 30), B uses CapEx (30) → 320.
"""
from datetime import date

import pytest

import services.regspec as R
from services.governance import taxonomy_gar as G
from services.governance import taxonomy_vocabulary as V

NFC = {"counterparty_sector": "non_financial_corporation", "nfrd_subject": True, "csrd_subject": True, "country": "DE",
       "trading_book": False}


def _kpi(**kw):
    return {k.replace("__", ":"): v for k, v in kw.items()}


BOOK = [
    {**NFC, "instrument_type": "loans_and_advances", "outstanding_loan_balance_eur": 100, "nace_code": "25.11",
     "counterparty_taxonomy_kpi": _kpi(turnover__ccm={"eligible": 50, "aligned": 30, "transitional": 5, "enabling": 10},
                                       capex__ccm={"eligible": 60, "aligned": 40})},
    {**NFC, "instrument_type": "debt_securities", "outstanding_loan_balance_eur": 50, "nace_code": "25.11",
     "counterparty_taxonomy_kpi": _kpi(turnover__ccm={"aligned": 20}, capex__ccm={"aligned": 60})},
    {"counterparty_sector": "household", "instrument_type": "loans_and_advances", "immovable_collateral": "residential",
     "outstanding_loan_balance_eur": 200, "country": "DE", "taxonomy_status": "aligned", "taxonomy_objective": "ccm",
     "taxonomy_contribution": "none"},
    {**NFC, "nfrd_subject": False, "csrd_subject": False, "instrument_type": "loans_and_advances",
     "outstanding_loan_balance_eur": 80, "nace_code": "10.71"},
    {"counterparty_sector": "credit_institution", "instrument_type": "derivatives", "outstanding_loan_balance_eur": 30,
     "country": "DE", "nfrd_subject": True, "csrd_subject": True},
    {"counterparty_sector": "general_government", "counterparty_govt_level": "central", "instrument_type": "debt_securities",
     "outstanding_loan_balance_eur": 70, "country": "DE"},
    {**NFC, "instrument_type": "loans_and_advances", "outstanding_loan_balance_eur": 40, "nace_code": "41.20"},
    {**NFC, "instrument_type": "loans_and_advances", "outstanding_loan_balance_eur": 60, "nace_code": "35.11",
     "specialised_lending": True, "taxonomy_status": "aligned", "taxonomy_objective": "ccm", "taxonomy_contribution": "enabling"},
]
V2023, V2026 = "da_2021_2178_as_amended_2023_2486", "da_2021_2178_as_amended_2026_73"


def _build(version, disclosed):
    spec = R.load("bank_taxonomy", version)
    return spec, G.build(spec, BOOK, date(2025, 12, 31), disclosure_date=disclosed)


def _row(spec, tid, last_label):
    return next(r["id"] for r in R.template(spec, tid)["rows"] if r["label"].split(" > ")[-1] == last_label)


def _col(spec, tid, **want):
    """The (first) column whose resolved meaning has these values — ids are the spec's, not typed here."""
    res = V.resolve(spec, tid)
    for c in R.template(spec, tid)["columns"]:
        f = res["columns"][c["id"]]
        if all(f.get(k) == v for k, v in want.items()) and (f.get("period") in (None, "current")):
            return c["id"]
    raise AssertionError(f"no column {want} in {tid}")


@pytest.fixture(scope="module")
def v2023():
    return _build(V2023, date(2025, 4, 30))


@pytest.fixture(scope="module")
def v2026():
    return _build(V2026, date(2026, 4, 30))


def test_every_exposure_is_placed_and_the_denominator_follows_the_version(v2023, v2026):
    (_, a), (_, b) = v2023, v2026
    assert a["counts"]["unclassified"] == 0 and b["counts"]["unclassified"] == 0
    assert (a["counts"]["covered"], a["counts"]["total"]) == (560, 630)      # D and E excluded from the numerator only
    assert (b["counts"]["covered"], b["counts"]["total"]) == (450, 630)      # 2026/73: they leave the denominator


def test_template_1_values_by_counterparty_kpi_and_by_own_status(v2023):
    spec, out = v2023
    nfc, hh, total_gar = _row(spec, "T1", "Non-financial undertakings"), _row(spec, "T1", "Households"), _row(spec, "T1", "Total GAR assets")
    gross = _col(spec, "T1", measure="gross")
    aligned = _col(spec, "T1", objective="ccm", measure="aligned")
    uop = _col(spec, "T1", objective="ccm", measure="use_of_proceeds")
    enabling = _col(spec, "T1", objective="ccm", measure="enabling")
    t, c = out["T1"]["turnover"], out["T1"]["capex"]
    assert t[nfc][gross] == 250 and t[total_gar][gross] == 560
    assert t[nfc][aligned] == pytest.approx(100)          # A 30 + B 10 (turnover) + H 60; G has no KPIs → not counted
    assert c[nfc][aligned] == pytest.approx(120)          # A 30 (general lending → turnover KPI) + B 30 (CapEx) + H 60
    assert t[nfc][uop] == pytest.approx(60)               # only the specialised loan
    assert t[nfc][enabling] == pytest.approx(70)          # A 10 + H 60 (B states no enabling share)
    assert t[hh][aligned] == 200


def test_the_phase_in_leaves_new_objectives_to_eligibility(v2023):
    spec, out = v2023
    wtr_aligned = _col(spec, "T1", objective="wtr", measure="aligned")
    nfc = _row(spec, "T1", "Non-financial undertakings")
    assert out["T1"]["turnover"][nfc][wtr_aligned] == G.NOT_REQUIRED     # Art. 10(7), disclosures in 2024-2025
    assert out["counts"]["phase_in"]["ref"].startswith("Article 10(7)")


def test_template_0_gar_kpis(v2023, v2026):
    spec, out = v2023
    t0 = out["T0"]["all"]["r1"]
    assert t0["c1"] == pytest.approx(300)                          # total environmentally sustainable assets
    assert (t0["c2"], t0["c3"]) == (pytest.approx(53.57), pytest.approx(57.14))   # 300 / 560, 320 / 560
    assert (t0["c4"], t0["c5"], t0["c6"]) == (pytest.approx(88.89), pytest.approx(17.46), pytest.approx(11.11))
    spec, out = v2026
    t0 = out["T0"]["all"]["r1"]
    assert (t0["c1"], t0["c2"]) == (pytest.approx(300), pytest.approx(320))     # turnover-based / CapEx-based amounts
    assert (t0["c3"], t0["c4"]) == (pytest.approx(66.67), pytest.approx(71.11))  # over the 2026 covered assets 450


def test_template_3_ratios_over_covered_assets(v2026):
    spec, out = v2026
    nfc = _row(spec, "T3", "Non-financial undertakings")
    aligned = _col(spec, "T3", measure="aligned", objective="ccm")
    assert out["T3"]["turnover"][nfc][aligned] == pytest.approx(round(100 * 100 / 450, 2))


def test_entered_templates_say_why(v2026):
    _, out = v2026
    assert set(out["inputs"]) >= {"T5", "T6", "T7"} and all(out["inputs"].values())


@pytest.mark.parametrize("version", [s["version"] for s in R.versions("bank_taxonomy") if s["status"] == "adopted"])
def test_every_version_places_every_exposure(version):
    """Each version's row tree partitions the book — no exposure is left unplaced (it would vanish from the totals)."""
    spec = R.load("bank_taxonomy", version)
    out = G.build(spec, BOOK, date(2025, 12, 31), disclosure_date=date.fromisoformat(spec["applies"]["from"]))
    assert out["counts"]["unclassified"] == 0 and out["counts"]["total"] == 630
