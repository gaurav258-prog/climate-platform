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


def _x(i, gross, *, s=(10.0, 5.0, 100.0), L=1_000_000.0, rep=True, nace="C24.10", country="DE", hazards=(), cp="auto", **kw):
    return {"asset_id": f"a{i}", "asset_name": f"Loan {i}", "nace_code": nace, "country": country,
            "counterparty_ref": f"CP{i}" if cp == "auto" else cp,
            "counterparty_sector": "non_financial_corporation", "outstanding_loan_balance_eur": gross, "value_eur": gross,
            "ghg1": s[0], "ghg2": s[1], "ghg3": s[2], "counterparty_total_liabilities_eur": L,
            "counterparty_total_liabilities_date": "2025-12-31", "emissions_company_reported": rep,
            "hazards": [{"relevant": True, **h} for h in hazards], **kw}


BOOK = [_x(1, 100_000, L=1_000_000, rep=True),                       # factor 0.1
        _x(2, 300_000, L=600_000, rep=False, s=(4.0, 2.0, 40.0)),     # factor 0.5
        _x(3, 600_000, s=(None, None, None), rep=None)]               # no emissions: never in i, never a gap for k


def _rec(est="scope_1_2_3", att="exposure_over_total_liabilities", narrative=None, **kw):
    return {"estimation": est, "attribution": att, "reference_date": "2025-12-31", **kw,
            "narrative": narrative if narrative is not None else {n["key"]: "stated" for n in T1.narrative_items()}}


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
    for key in (T1.ESTIMATION, T1.ATTRIBUTION, T1.K_READING, T1.S3_BASIS):
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


def test_scopes_1_and_2_leave_column_j_blank_and_k_follows_the_stated_reading():
    v = _total(BOOK, _rec("scope_1_2"))                         # k's reading not stated: k alone is a gap
    assert v["i"] == pytest.approx(0.1 * 15 + 0.5 * 6) and v["j"] is None and v["k"] is None
    assert T1.k_gap(_rec("scope_1_2")) and T1.k_gap(_rec("scope_1_2", k_scope_1_2="scopes_estimated")) is None
    assert _total(BOOK, _rec("scope_1_2", k_scope_1_2="scopes_estimated"))["k"] == 10.0
    assert _total(BOOK, _rec("scope_1_2", k_scope_1_2="all_three_scopes"))["k"] == 0.0


def test_not_yet_estimating_prints_k_as_zero_percent():
    """Column k is the share for which the institution 'has been able to estimate' — nothing, so 0 %; i and j blank."""
    v = _total(BOOK, _rec("not_yet_estimating", None))
    assert (v["i"], v["j"], v["k"]) == (None, None, 0.0)


@pytest.mark.parametrize("rec", [_rec(None), _rec("scope_1_2_3", None)])
def test_not_stated_leaves_i_to_k_blank(rec):
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
                                         "t1_emissions_source_recorded", "t1_narrative_authored", "t1_counterparty_identified",
                                         "t1_counterparty_figure_agreed", "t1_scope3_basis", "t1_k_reading_stated"))


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


# ── one counterparty, one figure (E119) ───────────────────────────────────────────────────────────────────────────
def test_an_exposure_without_a_counterparty_id_or_with_a_conflicting_figure_is_in_no_column_and_blocks():
    book = BOOK + [_x(4, 50_000, cp=None), _x(5, 70_000, counterparty_liabilities_conflict=True)]
    g = build(SPEC, "T1", book, t1=_rec())
    v = next(r for r in g["rows"] if r["id"] == TOTAL)["values"]
    assert (g["stated"]["no_counterparty"], g["stated"]["conflict"]) == (1, 1)
    assert v["i"] == pytest.approx(0.1 * 115 + 0.5 * 46)       # neither is attributed: no figure is picked
    f = _findings(_payload(_rec(), book))
    assert not f["t1_counterparty_identified"]["passed"] and not f["t1_counterparty_figure_agreed"]["passed"]
    assert f["t1_counterparty_identified"]["severity"] == "blocking"


# ── sector-average intensity for scope 3 (E120) ───────────────────────────────────────────────────────────────────
_SA = {"C24": {"value": 250.0, "provider": "Source X", "data_vintage": "2024-12-31"}}


def test_scope_3_from_the_stated_sector_average_intensity():
    """Loan 7 (gross 200 000, L 2 000 000) states scopes 1-2 only: its scope 3 is 250 tCO2e/EUR m × L, attributed by
    x / L — i.e. 250 × 0.2 = 50 tCO2e; it is not company-specific, so not in k's share."""
    book = BOOK + [_x(7, 200_000, L=2_000_000, s=(20.0, 10.0, None), rep=True)]
    r = T1.exposure(book[-1], _rec(scope3_sector_average="intensity_x_total_liabilities", sector_intensity=_SA))
    assert r["basis"] == "sector_average" and r["company_specific"] is False
    assert r["j"] == pytest.approx(250.0 * 2_000_000 / 1_000_000 * 0.1) == pytest.approx(50.0)
    v = _total(book, _rec(scope3_sector_average="intensity_x_total_liabilities", sector_intensity=_SA))
    assert v["i"] == pytest.approx(0.1 * 115 + 0.5 * 46 + 0.1 * (30 + 500))
    assert v["j"] == pytest.approx(0.1 * 100 + 0.5 * 40 + 50.0)
    assert v["k"] == round(100_000 / 1_200_000 * 100, 1)        # only loan 1 rests on company-specific reporting


@pytest.mark.parametrize("rec, why", [
    (_rec(), "not stated: how sector-average intensity is used"),
    (_rec(scope3_sector_average="intensity_x_total_liabilities", sector_intensity={}), "no sector-average scope 3 intensity stated for division C24"),
])
def test_no_gathered_scope_3_and_no_sector_average_is_a_named_gap_never_zero(rec, why):
    book = BOOK + [_x(7, 200_000, L=2_000_000, s=(20.0, 10.0, None))]
    g = build(SPEC, "T1", book, t1=rec)
    v = next(r for r in g["rows"] if r["id"] == TOTAL)["values"]
    assert g["stated"]["s3_gap"] == 1 and v["i"] == pytest.approx(0.1 * 115 + 0.5 * 46)
    f = _findings(_payload(rec, book))
    assert not f["t1_scope3_basis"]["passed"] and why in f["t1_scope3_basis"]["message"]


# ── the scope 3 phase-in (Delegated Regulation (EU) 2020/1818 Art. 5(1); E121) ────────────────────────────────────
def test_phase_in_is_quoted_from_the_stored_texts_and_its_dates_follow_the_words():
    from datetime import date
    ref = T1.phase_in_reference()
    assert contains(ref["article"]["quote"]) == "32020R1818"
    for b in ref["basis"]:
        assert contains(b["quote"]) == "32022R2453"
    words = {"a": ("05 to 09", "19 and 20"), "b": ("10 to 18", "21 to 33", "41, 42 and 43", "49 to 53", "Division 81"),
             "c": ("all other sectors",)}
    for p in ref["points"]:
        assert contains(p["quote"]) == "32020R1818" and p["words"] in p["quote"] and ref["anchor"] in p["words"]
        assert all(w in p["quote"] for w in words[p["id"]])
        assert {"a": 0, "b": 2, "c": 4}[p["id"]] == p["years"]
        assert ("two years" in p["words"]) == (p["years"] == 2) and ("four years" in p["words"]) == (p["years"] == 4)
    pts = {p["point"]: p for p in T1.phase_in_points()}
    assert [pts[x]["from"] for x in "abc"] == [date(2020, 12, 23), date(2022, 12, 23), date(2024, 12, 23)]
    # the period's last day by Regulation (EEC, Euratom) No 1182/71 Art. 3(1), 3(2)(c), quoted from the stored text (E131)
    assert {r["ref"].split(", ")[-1] for r in ref["period_rules"]} == {"Article 1", "Article 3(1)", "Article 3(2)(c)", "Article 3(4)"}
    assert all(contains(r["quote"]) == "31971R1182" for r in ref["period_rules"])
    assert all(pts[x]["from"].weekday() < 5 for x in "bc")      # not a Saturday or Sunday: Art. 3(4) moves neither
    assert set(pts["a"]["divisions"]) == {"B05", "B06", "B07", "B08", "B09", "C19", "C20"}
    assert {"C10", "C33", "F41", "F43", "H49", "H53", "N81"} <= set(pts["b"]["divisions"]) and "C19" not in pts["b"]["divisions"]
    assert {"A01", "K64", "N82"} <= set(pts["c"]["divisions"])
    every = [d for p in pts.values() for d in p["divisions"]]
    assert len(every) == len(set(every))                        # each division in exactly one point
    assert T1.all_sectors_from() == date(2024, 6, 30)


def test_phase_in_status_on_a_reference_date():
    from datetime import date
    assert T1.phase_in("C24", date(2022, 6, 30))["phased_in"] is False
    assert T1.phase_in("C24", date(2022, 12, 23))["phased_in"] is True
    st = T1.phase_in("A01", date(2024, 6, 30))
    assert st["phased_in"] is False and st["its_all_sectors"] is True   # the ITS requires all sectors from 30 June 2024
    assert T1.phase_in("B06", date(2021, 1, 1))["phased_in"] is True and T1.phase_in(None, date(2025, 1, 1)) is None
    rows = build(SPEC, "T1", BOOK + [_x(8, 10_000, nace="A01.11")], t1=_rec(reference_date="2023-12-31"))["rows"]
    ph = next(r for r in rows if r["id"] == TOTAL)["scope3_phase_in"]
    assert [p["division"] for p in ph["in_phase_in"]] == ["A01"] and ph["in_phase_in"][0]["n"] == 1
    assert "A01" in T1.phase_in_note(ph)


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
