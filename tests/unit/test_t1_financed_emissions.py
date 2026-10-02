"""Pillar 3 Template 1 columns i, j, k to the instructions (E103), and Template 5 cells traced to their exposures (E105).

Pure: synthetic frozen payloads — every fact the code reads is stated here. The quotes are checked against the stored
official text (Annex II of Implementing Regulation (EU) 2022/2453); the EBA IT solutions under 2024/3172 carry the same
wording (checked at capture, data/reference/pillar3/t1_financed_emissions.json) and are not EU OJ text, so not stored.
"""
from __future__ import annotations

import pytest

import services.regspec as R
from services.calc_settings import INTERPRETATION_SCHEMA, validate_interpretation
from services.governance import pillar3_t1 as T1
from services.governance.filing_form import build_form
from services.governance.filing_validation import _RULESETS
from services.governance.pillar3_grids import (
    BINDING,
    build,
    geographies,
    row_population,
    t5_contribution,
    template5,
)
from services.governance.pillar3_report import t1_total
from services.reference.legal_texts import contains

SPEC = R.load("bank_p3esg", "its_2024_3172")
TOTAL = next(rid for rid, how in BINDING["T1"]["rows"].items() if how == "computed:total")
_LEVEL = {"period_end": "2025-12-31", "used": [{"key": "method.at_risk_level", "member": None, "value": 50}], "gaps": []}


def _x(i, gross, *, s=(10.0, 5.0, 100.0), L=1_000_000.0, rep=True, nace="C24.10", country="DE", hazards=(), **kw):
    return {"asset_id": f"a{i}", "asset_name": f"Loan {i}", "nace_code": nace, "country": country,
            "counterparty_sector": "non_financial_corporation", "outstanding_loan_balance_eur": gross, "value_eur": gross,
            "ghg1": s[0], "ghg2": s[1], "ghg3": s[2], "counterparty_total_liabilities_eur": L,
            "counterparty_total_liabilities_date": "2025-12-31", "emissions_company_reported": rep,
            "hazards": [{"relevant": True, **h} for h in hazards], **kw}


BOOK = [_x(1, 100_000, L=1_000_000, rep=True),                       # factor 0.1
        _x(2, 300_000, L=600_000, rep=False, s=(4.0, 2.0, 40.0)),     # factor 0.5
        _x(3, 600_000, s=(None, None, None), rep=None)]               # no emissions: never in i, never a gap for k


def _rec(est="scope_1_2_3", att="exposure_over_total_liabilities", narrative=None):
    return {"estimation": est, "attribution": att, "narrative": narrative if narrative is not None else {
        n["key"]: "stated" for n in T1.narrative_items()}}


def _total(assets, rec):
    return next(r for r in build(SPEC, "T1", assets, t1=rec)["rows"] if r["id"] == TOTAL)["values"]


# ── the quotes and the statements ─────────────────────────────────────────────────────────────────────────────────
def test_every_quote_is_word_for_word_in_the_stored_2022_2453_text():
    for qid, q in T1.reference()["quotes"].items():
        assert contains(q["quote"]) == "32022R2453", qid


def test_statements_and_narrative_cite_only_held_quotes_and_are_switches_without_a_default():
    ref = T1.reference()
    for st in ref["statements"].values():
        assert set(st["quotes"]) <= set(ref["quotes"])
    for n in ref["narrative"]:
        assert set(n["quotes"]) <= set(ref["quotes"]) and n["key"].startswith("t1.")
        assert set(n["required_when"]) <= set(ref["statements"][T1.ESTIMATION]["options"])
    for key in (T1.ESTIMATION, T1.ATTRIBUTION):
        sw = INTERPRETATION_SCHEMA[key]
        assert sw["default"] is None and sw["frameworks"] == ["bank_p3esg"]
        assert sw["allowed"] == list(ref["statements"][key]["options"])
        with pytest.raises(ValueError):
            validate_interpretation(key, "pcaf")            # PCAF's own attribution is not offered (not implemented)
    assert "pcaf" in ref["statements"][T1.ATTRIBUTION]["not_offered"]


# ── columns i, j, k ───────────────────────────────────────────────────────────────────────────────────────────────
def test_scopes_1_to_3_attributed_by_exposure_over_total_liabilities():
    v = _total(BOOK, _rec())
    assert v["i"] == pytest.approx(0.1 * 115 + 0.5 * 46)
    assert v["j"] == pytest.approx(0.1 * 100 + 0.5 * 40)
    assert v["k"] == round(100_000 / 1_000_000 * 100, 1)      # reported: loan 1's gross over the row's gross


def test_scopes_1_and_2_leave_column_j_blank():
    v = _total(BOOK, _rec("scope_1_2"))
    assert v["i"] == pytest.approx(0.1 * 15 + 0.5 * 6) and v["j"] is None and v["k"] == 10.0


@pytest.mark.parametrize("rec", [_rec("not_yet_estimating", None), _rec(None), _rec("scope_1_2_3", None)])
def test_not_estimating_or_not_stated_leaves_i_to_k_blank(rec):
    v = _total(BOOK, rec)
    assert (v["i"], v["j"], v["k"]) == (None, None, None)


def test_a_filing_frozen_before_the_statements_prints_as_it_did():
    v = _total(BOOK, None)
    assert v["i"] == 115 + 46 and v["j"] == 140                 # un-attributed, as then printed


def test_what_cannot_be_attributed_or_read_is_counted_never_guessed():
    book = BOOK + [_x(4, 50_000, L=None), _x(5, 2_000_000, L=1_000_000), _x(6, 10_000, rep=None)]
    g = build(SPEC, "T1", book, t1=_rec())
    st, v = g["stated"], next(r for r in g["rows"] if r["id"] == TOTAL)["values"]
    assert (st["unattributed"], st["over"], st["rep_unknown"]) == (1, 1, 1)
    assert v["k"] is None                                       # a column-i exposure without its emissions' source
    assert v["i"] == pytest.approx(0.1 * 115 + 0.5 * 46 + 0.01 * 115)


# ── the filing: form, validation ──────────────────────────────────────────────────────────────────────────────────
def _payload(rec, assets=BOOK):
    return {"assets": assets, "rollup": {"n_assets": len(assets), "n_scored": len(assets), "total_value_eur": 1_000_000},
            T1.RECORD: rec, "method": _LEVEL, "_specs": {"bank_p3esg": {"framework": "bank_p3esg", "version": "its_2024_3172"}}}


def _findings(p):
    return {f["rule"]: f for f in _RULESETS["bank_p3esg"](p)}


def test_the_form_prints_template_1_total_row_on_the_stated_method():
    groups = build_form("bank_p3esg", _payload(_rec()))
    dps = {d["key"]: d for g in groups for d in g["datapoints"]}
    assert groups[0]["group"].startswith("Template 1")
    assert dps["emissions.total"]["value"] == pytest.approx(34.5) and dps["emissions.company_reported_pct"]["value"] == 10.0
    assert t1_total(_payload(_rec()))["j"] == pytest.approx(30.0)


def test_validation_blocks_an_unstated_method_and_missing_narrative():
    f = _findings(_payload(_rec(None)))
    assert not f["t1_method_stated"]["passed"] and f["t1_method_stated"]["severity"] == "blocking"
    f = _findings(_payload(_rec("scope_1_2", narrative={"t1.data_sources": "x"})))
    assert f["t1_method_stated"]["passed"] and not f["t1_narrative_authored"]["passed"]
    assert "scope 3" in f["t1_narrative_authored"]["message"] and "Methodology" in f["t1_narrative_authored"]["message"]
    assert _findings(_payload(_rec("not_yet_estimating", None, {"t1.plans_emissions": "p", "t1.plans_scope3": "p"})))[
        "t1_narrative_authored"]["passed"]
    ok = _findings(_payload(_rec()))
    assert all(ok[r]["passed"] for r in ("t1_method_stated", "t1_total_liabilities_stated", "t1_exposure_within_liabilities",
                                         "t1_emissions_source_recorded", "t1_narrative_authored"))


def test_validation_blocks_unattributable_and_unreadable_exposures():
    f = _findings(_payload(_rec(), BOOK + [_x(4, 50_000, L=None), _x(5, 10_000, rep=None)]))
    assert not f["t1_total_liabilities_stated"]["passed"] and not f["t1_emissions_source_recorded"]["passed"]
    assert f["t1_exposure_within_liabilities"]["passed"]
    f = _findings(_payload(_rec(), BOOK + [_x(5, 2_000_000, L=1_000_000)]))
    assert not f["t1_exposure_within_liabilities"]["passed"]


def test_a_filing_without_the_record_keeps_its_checks():
    p = _payload(None)
    p.pop(T1.RECORD)
    assert not any(r.startswith("t1_") for r in _findings(p))


# ── Template 5 lineage: every cell is the sum of its contributors ─────────────────────────────────────────────────
T5_BOOK = [
    _x(1, 1_000_000, country="DE", hazards=[{"hazard": "flood", "score": 80}], residual_maturity_years=4, ifrs9_stage="2",
       accumulated_impairment_eur=1_000),
    _x(2, 2_000_000, nace="C20.11", country="ES", hazards=[{"hazard": "drought", "score": 70}], residual_maturity_years=12),
    _x(3, 4_000_000, nace="A01.11", country="ES", hazards=[{"hazard": "drought", "score": 60}, {"hazard": "wildfire", "score": 90}],
       no_stated_maturity=True, ifrs9_stage="3", accumulated_impairment_eur=-5_000),
    _x(4, 8_000_000, nace="C10.11", country="FR", hazards=[{"hazard": "drought", "score": 20}], residual_maturity_years=7),
    {**_x(5, 500_000, nace=None, country="IT", hazards=[{"hazard": "flood", "score": 95}], residual_maturity_years=25),
     "counterparty_sector": "household", "immovable_collateral": "residential"},
]


def test_every_template_5_cell_is_the_sum_of_its_traced_exposures():
    g5 = template5(SPEC, T5_BOOK, 50)
    t = R.template(SPEC, "T5")
    scopes = [("ALL", T5_BOOK, g5)] + [(c, pop, next(x for x in g5["geographies"] if x["geography"] == c))
                                       for c, _, pop in geographies(T5_BOOK)]
    for _, pop_geo, grid in scopes:
        for r in t["rows"]:
            pop = row_population(SPEC, "T5", r["id"], pop_geo)
            printed = next(x for x in grid["rows"] if x["id"] == r["id"])["values"]
            for c in (c["id"] for c in t["columns"] if c["id"] != "a"):
                parts = [p for p in (t5_contribution(a, c, 50) for a in pop) if p is not None]
                if c == "g":
                    w = sum(p["weight"] for p in parts)
                    got = round(sum(p["weight"] * p["maturity"] for p in parts) / w, 1) if w else None
                    assert got == printed[c], (r["id"], c)
                elif printed[c] is None:
                    assert not parts, (r["id"], c)
                else:
                    assert sum(p["amount"] for p in parts) == pytest.approx(printed[c]), (r["id"], c)
