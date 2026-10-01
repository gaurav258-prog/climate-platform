"""Pillar 3 ESG prints what its ITS templates print (E97) and its Template 5 rows carry KRIs with filed history (E98).

Pure: synthetic frozen payloads — every fact the code reads is stated here.
"""
from __future__ import annotations

import json

import services.regspec as R
from services.governance import kri_t5
from services.governance.filing_annex import build_annex
from services.governance.filing_form import build_form
from services.governance.filing_validation import _RULESETS
from services.governance.pillar3_report import EARLIER, EARLIER_KEYS, is_earlier_shape

_LEVEL = {"period_end": "2025-12-31", "used": [{"key": "method.at_risk_level", "member": None, "value": 50}], "gaps": []}


def _asset(i, nace, country, hazards, gross):
    return {"asset_id": f"a{i}", "asset_name": f"Loan {i}", "asset_type": "corporate_loan", "nace_code": nace,
            "counterparty_sector": "non_financial_corporation", "country": country, "value_eur": gross,
            "outstanding_loan_balance_eur": gross, "residual_maturity_years": 4, "ghg1": 10, "ghg2": 5, "ghg3": 100,
            "headline_score": max(h["score"] for h in hazards), "headline_bucket": "H",
            "hazards": [{"relevant": True, **h} for h in hazards]}


ASSETS = [
    _asset(1, "C24.10", "DE", [{"hazard": "flood", "score": 80}], 1_000_000),          # acute only
    _asset(2, "C20.11", "ES", [{"hazard": "drought", "score": 70}], 2_000_000),              # chronic only
    _asset(3, "A01.11", "ES", [{"hazard": "drought", "score": 60}, {"hazard": "wildfire", "score": 90}], 4_000_000),  # both
    _asset(4, "C10.11", "FR", [{"hazard": "drought", "score": 20}], 8_000_000),              # not sensitive
]


def _spec_record(version="its_2024_3172"):
    return {"bank_p3esg": {"framework": "bank_p3esg", "version": version}}


def _new(**over) -> dict:
    p = {"assets": ASSETS, "rollup": {"n_assets": 4, "n_scored": 4, "total_value_eur": 15_000_000},
         "financed_emissions_tco2e": {"scope1": 40, "scope2": 20, "scope3": 400},
         "financed_emissions_pcaf": {"attributed": {"scope1": 40, "scope2": 20, "scope3": 400}},
         "method": _LEVEL, "_specs": _spec_record()}
    return {**p, **over}


def _earlier() -> dict:
    return _new(rollup={"n_assets": 4, "n_scored": 4, "total_value_eur": 15_000_000, "value_at_risk_eur": 7_000_000,
                        "pct_value_at_risk": 46.7, "by_bucket": {"H": {"count": 4, "value_eur": 15_000_000}}},
                by_hazard={"drought": {"exposed_value_eur": 6_000_000, "n_exposed": 2}},
                taxonomy={"eligible": {"count": 1, "value_eur": 1_000_000}},
                expected_loss={"annual_el_eur": 12_345, "total_ead_eur": 15_000_000, "annual_el_bps": 8,
                               "lifetime_el_eur": 50_000, "lifetime_el_bps": 33, "scenario": "disorderly_2c"},
                transition={"available": True, "financed_emissions_tco2e": 460, "emissions_reported_pct": 100,
                            "transition_expected_loss_eur": 9_000, "transition_el_pct_of_outstanding": 0.1},
                collateral_stranding={"available": True, "gap": "not stated: method.brown_discount"})


def _render(payload):
    groups = build_form("bank_p3esg", payload)
    dps = {d["key"]: d for g in groups for d in g["datapoints"]}
    return groups, build_annex("bank_p3esg", dps, groups, payload)


_NOT_PRINTED = ("expected loss", "stranding", "Headline exposure", "TCFD", "Value at material physical risk",
                "Exposure by hazard", "EU Taxonomy")


def test_a_new_filing_prints_only_template_content():
    p = _new()
    assert not is_earlier_shape(p)
    groups, annex = _render(p)
    assert [g["group"] for g in groups] == ["Financed emissions (PCAF)", "Frozen banking book"]
    titles = [s["title"] for s in annex["sections"]]
    assert all(t.startswith(("Template", "Transition risk — financed")) for t in titles), titles
    txt = json.dumps({"g": groups, "a": annex}, ensure_ascii=False)
    assert not any(w in txt for w in _NOT_PRINTED)
    assert any(t.startswith("Template 5") for t in titles) and any(t.startswith("Template 1") for t in titles)


def test_a_filing_of_the_earlier_shape_still_renders_what_it_froze_marked():
    p = _earlier()
    assert is_earlier_shape(p) and set(EARLIER_KEYS) <= set(p)
    groups, annex = _render(p)
    names = [g["group"] for g in groups]
    assert names[:2] == ["Financed emissions (PCAF)", "Frozen banking book"]
    assert f"{EARLIER} · Headline exposure" in names and all(n.startswith(EARLIER) for n in names[2:])
    secs = annex["sections"]
    earlier = [s for s in secs if s["title"].startswith(EARLIER)]
    templates = [s for s in secs if s["title"].startswith("Template")]
    assert earlier and secs.index(templates[-1]) < secs.index(earlier[0])               # the templates first
    assert any("expected loss" in s["title"] for s in earlier) and all("earlier shape" in s["note"] for s in earlier)


def test_validation_checks_what_the_frozen_book_holds():
    new = {f["rule"] for f in _RULESETS["bank_p3esg"](_new())}
    assert {"has_assets", "some_scored", "gross_carrying_amount_stated"} <= new
    assert not {"buckets_reconcile", "var_within_book", "share_in_range"} & new        # figures no longer frozen
    old = {f["rule"] for f in _RULESETS["bank_p3esg"](_earlier())}
    assert {"buckets_reconcile", "var_within_book"} <= old                             # the checks it was made under


def test_template5_row_kris_read_the_filed_grid():
    spec = R.load("bank_p3esg", "its_2024_3172")
    p = _new()
    g = kri_t5.grid(p)
    row_c = next(r for r in g["rows"] if r["label"].startswith("C - "))
    row_a = next(r for r in g["rows"] if r["label"].startswith("A - "))
    assert (row_c["values"]["h"], row_c["values"]["i"], row_c["values"]["j"]) == (2_000_000, 1_000_000, 0)
    assert row_a["values"]["j"] == 4_000_000
    figs = {f["key"]: f["value"] for f in kri_t5.figures(p, spec)}
    assert figs[kri_t5.key(row_c["id"], "i")] == 1_000_000 and figs[kri_t5.key(row_a["id"], "j")] == 4_000_000
    assert len(figs) == 3 * len(g["rows"])
    # the live KRIs: one per row and column, grouped, each with its printed cell as filed basis
    ks = kri_t5.kpis(spec, g, None)
    assert len(ks) == len(figs) and all(k["group"] == kri_t5.GROUP and not k["live_only"] for k in ks)
    k = next(k for k in ks if k["key"] == kri_t5.key(row_c["id"], "h"))
    assert k["value"] == 2_000_000 and "Template 5" in k["filed_basis"] and k["row"]["label"].startswith("C - ")


def test_a_filed_grid_counts_only_where_it_is_the_same_cell():
    spec = R.load("bank_p3esg", "its_2024_3172")
    renamed = json.loads(json.dumps(spec))
    t5 = next(t for t in renamed["templates"] if t["id"] == "T5")
    t5["rows"][0]["label"] = "something else"
    assert not any(f["key"].startswith(f"t5.{t5['rows'][0]['id']}.") for f in kri_t5.figures(_new(), renamed))
    assert kri_t5.figures(_new(_fx={"presentation_currency": "USD"}), spec) == []        # another currency: not one trend
    assert kri_t5.grid(_new(method={"period_end": "2025-12-31", "used": [], "gaps": []})) is None   # level not stated
    assert kri_t5.kpis(spec, None, "not stated: method.at_risk_level")[0]["value"] is None
