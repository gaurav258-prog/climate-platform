"""Pillar 3 Templates 1 and 5 against their specification — a golden book with known answers, run under every adopted
version (dual run). Each figure below is worked by hand from the book; the rules are the spec's (Annex XL):

  T5 c-o describe the physical-risk-sensitive exposures only; h / i / j are chronic ONLY / acute ONLY / both
  T5 rows 1-9, 13 = non-financial corporations by NACE; rows 10-12 = loans by immovable collateral, any counterparty
  T1 rows = non-financial corporations; row 1 = its printed section rows (incl. I), 53 = K + (J, M-U), 56 = 1 + 53
  a fact no exposure states is blank (None), never zero
"""
import pytest

import services.regspec as R
from services.governance import pillar3_grids as G
from services.governance.filing_annex import build_annex

ADOPTED = [s["version"] for s in R.versions("bank_p3esg") if s["status"] == "adopted"]


def _a(nace, gross, hazards=(), **kw):
    return {"nace_code": nace, "outstanding_loan_balance_eur": gross, "country": kw.pop("country", "DE"),
            "hazards": [{"hazard": h, "bucket": b} for h, b in hazards], **kw}


BOOK = [
    # A, NFC: chronic only, 3y, stage 2, impairment 10
    _a("01.11", 100, [("drought", "H")], residual_maturity_years=3, ifrs9_stage="2", accumulated_impairment_eur=10),
    # A, NFC: acute only, 12y, stage 1
    _a("01.11", 200, [("flood", "VH")], residual_maturity_years=12, ifrs9_stage="1"),
    # A, NFC: both, no stated maturity (equity) → '> 20 years', stage 3
    _a("01.11", 300, [("drought", "H"), ("flood", "H")], no_stated_maturity=True, ifrs9_stage="3"),
    # A, NFC: not sensitive, stage 2 — in b only, never in c-o
    _a("01.11", 400, [("flood", "M")], residual_maturity_years=4, ifrs9_stage="2"),
    # L, NFC, commercial property collateral (stated): row 9 AND row 11
    _a("68.20", 50, [("flood", "H")], residual_maturity_years=7, immovable_collateral="commercial",
       counterparty_sector="non_financial_corporation"),
    # household mortgage: row 10 only
    _a(None, 80, [("flood", "H")], asset_type="residential_real_estate", residual_maturity_years=25),
    # I (accommodation), NFC: T5 row 13; T1 row 51, inside row 1
    _a("55.10", 60, [("heatwave", "H")]),
    # J, NFC: T5 row 13; T1 row 55 (inside 53)
    _a("62.01", 70),
    # K, stated NFC holding: T1 row 54
    _a("64.20", 90, counterparty_sector="non_financial_corporation"),
    # K, inferred financial corporation: in no row of either template
    _a("64.19", 1000, [("flood", "VH")]),
    # B.05 coal mining: row 3 (B) and row 4 (B.05) of T1, row 2 of T5
    _a("05.10", 40, [("drought", "VH")], pab_excluded=True, emissions_company_reported=True, ghg1=5, ghg2=1, ghg3=4),
]


def _rows(g):
    return {r["id"]: r["values"] for r in g["rows"]}


@pytest.mark.parametrize("version", ADOPTED)
def test_every_spec_row_and_column_is_built_in_spec_order(version):
    spec = R.load("bank_p3esg", version)
    for tid in ("T1", "T5"):
        g = G.build(spec, tid, BOOK)
        assert [r["id"] for r in g["rows"]] == [r["id"] for r in R.template(spec, tid)["rows"]]
        cols = {c["id"] for c in R.template(spec, tid)["columns"]} - {"a"} if tid == "T5" else {c["id"] for c in R.template(spec, tid)["columns"]}
        assert cols <= set(g["rows"][0]["values"])


@pytest.mark.parametrize("version", ADOPTED)
def test_template5_golden_book(version):
    r = _rows(G.build(R.load("bank_p3esg", version), "T5", BOOK))
    a = r["1"]
    assert a["b"] == 1000                                              # all four A exposures
    assert (a["h"], a["i"], a["j"]) == (100, 200, 300)                 # chronic only / acute only / both — a partition
    assert a["sensitive"] == 600 and a["h"] + a["i"] + a["j"] == 600
    assert (a["c"], a["d"], a["e"], a["f"]) == (100, 0, 200, 300)      # sensitive only: the 400 non-sensitive loan is absent
    assert a["g"] == round((100 * 3 + 200 * 12) / 300, 1)              # stated maturities only (equity has none to average)
    assert (a["k"], a["l"]) == (100, 300)                              # stage 2 / NPE among the sensitive — not the 400
    assert (a["m"], a["n"], a["o"]) == (10, 10, 0)                     # impairment stated on one sensitive loan
    assert r["9"]["b"] == 50 and r["11"]["b"] == 50                    # NFC with CRE collateral: sector row and row 11
    assert r["10"]["b"] == 80 and r["10"]["f"] == 80                   # household mortgage: collateral row only
    assert r["12"]["b"] == 0
    assert r["13"]["b"] == 60 + 70 + 90                                # I, J and the stated-NFC holding in K: outside A–H, L
    assert r["2"]["b"] == 40
    assert sum(v["b"] for k, v in r.items() if k not in ("10", "11", "12")) == 1000 + 50 + 220 + 40   # no financial corporation
    assert r["13"]["m"] is None                                        # nobody states impairment there: blank, not zero


@pytest.mark.parametrize("version", ADOPTED)
def test_template1_golden_book(version):
    r = _rows(G.build(R.load("bank_p3esg", version), "T1", BOOK))
    assert r["2"]["a"] == 1000                                         # A: all four, sensitive or not
    assert r["3"]["a"] == 40 and r["4"]["a"] == 40 and r["5"]["a"] == 0   # B and its 'of which' B.05
    assert r["51"]["a"] == 60 and r["52"]["a"] == 50
    assert r["1"]["a"] == 1000 + 40 + 60 + 50                          # A…I, L — divisions not added twice
    assert r["54"]["a"] == 90 and r["55"]["a"] == 70 and r["53"]["a"] == 160
    assert r["56"]["a"] == r["1"]["a"] + r["53"]["a"]
    assert (r["2"]["d"], r["2"]["e"]) == (500, 300)                    # stage 2 / NPE over all exposures in T1
    assert r["2"]["o"] == 300 and r["2"]["l"] == 400 + 100             # equity → '> 20 years'; 3y and 4y ≤ 5
    assert r["3"]["b"] == 40 and r["2"]["b"] is None                   # Paris exclusion stated only on the coal loan
    assert r["3"]["i"] == 10 and r["3"]["j"] == 4
    assert r["3"]["k"] == 100.0 and r["2"]["k"] is None                # share of gross from company-reported emissions


def test_geographies_keep_every_exposure():
    spec = R.load("bank_p3esg", ADOPTED[-1])
    book = BOOK + [_a("01.11", 5, [("flood", "H")], country=f"X{i}") for i in range(12)]
    g = G.template5(spec, book)
    assert len(g["geographies"]) == G.TOP_GEOGRAPHIES + 1 and g["geographies"][-1]["geography"] == "OTHER"
    total = sum(_rows(x)["1"]["b"] for x in g["geographies"])
    assert total == _rows(g)["1"]["b"]


def test_the_form_follows_the_frozen_spec():
    old = build_annex("bank_p3esg", {}, [], {"assets": BOOK})                               # frozen before specs existed
    new = build_annex("bank_p3esg", {}, [], {"assets": BOOK, "_spec": {"version": "its_2024_3172"}})
    assert "2022/2453" in old["legal_basis"] and "2024/3172" in new["legal_basis"]
    t5 = next(s for s in new["sections"] if s.get("key") == "t5")
    spec = R.load("bank_p3esg", "its_2024_3172")
    assert "2024/3172" in t5["title"] and t5["spec"]["sha256"] == spec["_sha256"]
    assert [c.split(" · ")[0] for c in t5["columns"][1:]] == [c["id"] for c in R.template(spec, "T5")["columns"]][1:]
    assert len(t5["rows"]) == 13
