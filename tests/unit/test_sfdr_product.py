"""Golden book for the SFDR product templates (RTS 2022/1288 Annexes II–V, family sfdr_product), worked by hand.

Periodic, reference year 2025, two position dates (30.6 and 31.12):
  A  equity, utility (35.11)        100 then 140 → average 120; turnover KPI aligned 50 % (fossil gas 10 %), CapEx 60 %
  B  equity, software (62.01)        60 then 60 → average 60;  turnover KPI aligned 20 %; DNSH attestation false
  C  sovereign bond (DE)             20 then 20 → average 20;  no KPIs
Total 200. Turnover aligned incl. sovereigns: A 60 (B excluded by the gate) = 30 % of 200; fossil gas A 12 = 6 %;
aligned without gas and nuclear 24 %; KPIs stated for A and B = 180 / 200 = 90 %. Excluding sovereigns (base 180):
60 / 180 = 33.33 %; the excluding graph is 90 % of total investments. CapEx: A 72 → 36 % / 40 %.
Top investments: A 60 %, B 30 %, C 10 %.
"""

import pytest

import services.regspec as R
from services.governance import sfdr_product as S
from services.governance.sfdr_product_forms import missing
from services.governance.sfdr_product_html import render
from services.governance.template_answers import AnswerError
from services.governance.template_answers import shape as _shape

V2 = "rts_2022_1288_as_amended_2023_363"


def _h(d, issuer, value, *, nace="35.11", sov=False, kpi=None, gate=False):
    return {"date": d, "issuer_id": issuer, "issuer": issuer, "country": "DE", "nace": nace, "asset_class": "sovereign_bond" if sov else "equity",
            "sovereign": sov, "fossil_fuel": False, "value": value, "kpi": kpi, "gate_failed": gate}


KA = {"turnover": {"aligned": 50.0, "fossil_gas": 10.0, "nuclear": None, "eligible": 70.0, "transitional": None, "enabling": None},
      "capex": {"aligned": 60.0, "fossil_gas": None, "nuclear": None, "eligible": None, "transitional": None, "enabling": None}}
KB = {"turnover": {"aligned": 20.0, "fossil_gas": None, "nuclear": None, "eligible": 30.0, "transitional": None, "enabling": None}}
BOOK = {"fund": {"fund_id": "f", "name": "Golden Fund", "lei": "LEI0000000000000GOLD", "sfdr_classification": "article_8"},
        "document": "periodic", "period": {"start": "2025-01-01", "end": "2025-12-31"},
        "position_dates": ["2025-06-30", "2025-12-31"],
        "holdings": [_h("2025-06-30", "A", 100, kpi=KA), _h("2025-12-31", "A", 140, kpi=KA),
                     _h("2025-06-30", "B", 60, nace="62.01", kpi=KB, gate=True), _h("2025-12-31", "B", 60, nace="62.01", kpi=KB, gate=True),
                     _h("2025-06-30", "C", 20, sov=True), _h("2025-12-31", "C", 20, sov=True)],
        "answers": {"q_es_met": {"text": "Met, as shown by the indicators."}}}


def test_the_taxonomy_graphs_from_investees_own_kpis():
    t = S.taxonomy(BOOK)
    inc, exc = t["incl"]["turnover"], t["excl"]["turnover"]
    assert (inc["aligned"], inc["fossil_gas"], inc["aligned_other"], inc["kpi_coverage"]) == (30.0, 6.0, 24.0, 90.0)
    assert inc["nuclear"] is None and inc["transitional"] is None          # nobody states them: blank, never 0
    assert exc["aligned"] == pytest.approx(33.33) and t["excl_share_of_total"] == 90.0
    assert (t["incl"]["capex"]["aligned"], t["excl"]["capex"]["aligned"]) == (36.0, 40.0)
    assert t["incl"]["opex"]["aligned"] is None                             # no investee states an OpEx KPI


def test_top_investments_are_averaged_over_the_reference_period():
    rows = S.top_investments(BOOK)
    assert [(r["table_top_inv.largest"], r["table_top_inv.assets"]) for r in rows] == [("A", 60.0), ("B", 30.0), ("C", 10.0)]


def test_computed_items_exist_in_every_version_that_prints_them():
    """The binding's computed ids are the spec's own: a renamed item in a new version fails here, not silently."""
    for v in R.versions(S.FAMILY):
        spec = R.load(S.FAMILY, v["version"])
        for t in spec["templates"]:
            ids = {i["id"] for i in t["items"]}
            want = S._COMPUTED | (S._COMPUTED_PERIODIC if S.document_of(t["id"]) == "periodic" else set())
            gas = {i for i in want if "fossil_nuclear" in i}                 # added by 2023/363
            assert want - gas <= ids, (v["version"], t["id"], (want - gas) - ids)
            if v["version"] == V2 and S.document_of(t["id"]) == "periodic":
                assert gas <= ids


def test_the_periodic_document_fills_computed_items_and_asks_for_the_rest():
    spec = R.load(S.FAMILY, V2)
    built = {i["id"]: i for i in S.build(spec, "AIV", BOOK)}
    assert built["product_name"]["value"] == {"text": "Golden Fund"}
    assert built["q_sust_obj.no"]["value"] == {"ticked": True}                    # Art. 8
    assert built["q_taxonomy.fossil_nuclear.yes.fossil_gas"]["value"] == {"ticked": True}
    assert built["q_es_met"]["status"] == "filled" and built["q_es_met"]["source"] == "input"
    assert built["q_actions"]["status"] == "missing"
    assert all(i["source"] == "fixed" for i in built.values() if i["kind"] in ("definition", "heading"))


def test_no_holdings_leaves_the_computed_tables_missing_not_empty():
    spec = R.load(S.FAMILY, V2)
    built = {i["id"]: i for i in S.build(spec, "AIV", {**BOOK, "holdings": [], "position_dates": []})}
    assert built["table_top_inv"]["status"] == "missing" and "holdings" in built["table_top_inv"]["needs"]


def test_answers_take_the_shape_of_their_item():
    spec = R.load(S.FAMILY, V2)
    t = R.template(spec, "AII")
    by = {i["id"]: i for i in t["items"]}
    kids = lambda i: [c for c in t["items"] if c.get("parent") == i]   # noqa: E731
    assert _shape(by["q_sust_obj.no.es_with_si"], [], {"ticked": True, "percent": 15}) == {"ticked": True, "percent": 15.0}
    assert _shape(by["q_strategy.min_rate"], [], {"percent": 20}) == {"percent": 20.0}
    with pytest.raises(AnswerError):
        _shape(by["q_es_chars"], [], {"text": "  "})
    with pytest.raises(AnswerError):
        _shape(by["q_sust_obj.no.es_with_si"], [], {"ticked": True, "percent": 140})
    chart = by["chart_asset_alloc"]
    first = kids("chart_asset_alloc")[0]["id"]
    assert _shape(chart, kids("chart_asset_alloc"), {"values": {first: 90}}) == {"values": {first: 90.0}}
    with pytest.raises(AnswerError):
        _shape(chart, kids("chart_asset_alloc"), {"values": {"not_a_label": 5}})


def test_the_annex_marks_what_is_unanswered():
    spec = R.load(S.FAMILY, V2)
    built = S.build(spec, "AIV", BOOK)
    html = render(R.template(spec, "AIV")["title"], R.citation(spec, "AIV"), BOOK["fund"], built, "2025-12-31")
    assert "Met, as shown by the indicators." in html and "[not yet answered]" in html
    assert "☒" in html                                                         # the Art. 8 'No' box is ticked
    gaps = missing(built)
    assert "q_actions" in {g["id"] for g in gaps}
