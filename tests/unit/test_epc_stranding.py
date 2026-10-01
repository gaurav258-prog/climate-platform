"""Energy-performance stranding on the institution's stated brown discount and retrofit capex per EPC grade (E69):
no floor, curve or cap of the platform's own; an unstated grade is a named gap and the book total over it is a gap;
a property without an EPC or a value is not assessed, never given a number. Pure — no DB."""
from datetime import date

from ml.scoring.epc_stranding import (
    bank_collateral_stranding_rollup,
    epc_stranding,
    stranding_rollup,
)
from services.money.params import Method

STATED = {**{("method.brown_discount", g): v for g, v in zip("ABCDEFG", (0, 0, 0, 0, 0.05, 0.10, 0.15))},
          **{("method.retrofit_capex_share", g): v for g, v in zip("ABCDEFG", (0, 0, 0, 0, 0.04, 0.08, 0.12))}}


def _m(values=STATED):
    return Method.of(values, date(2025, 12, 31))


def test_a_property_takes_its_grades_stated_discount_and_capex():
    r = epc_stranding(_m(), "f", 10_000_000, 500_000)
    assert r["discounted"] and r["brown_discount_pct"] == 10.0
    assert r["value_at_risk_eur"] == 1_000_000 and r["retrofit_capex_eur"] == 800_000 and r["noi_at_risk_eur"] == 50_000
    assert epc_stranding(_m(), "B", 10_000_000)["discounted"] is False


def test_not_assessed_and_gap_are_different_things():
    assert epc_stranding(_m(), None, 1_000_000)["reason"] == "no_epc"
    assert epc_stranding(_m(), "G", None)["reason"] == "no_value"
    r = epc_stranding(_m({}), "G", 1_000_000)
    assert "method.brown_discount (G)" in r["gap"] and "value_at_risk_eur" not in r


def test_the_book_total_over_an_unstated_grade_is_a_gap_never_a_partial_sum():
    props = [{"epc_rating": "G", "property_value_eur": 1e6}, {"epc_rating": "E", "property_value_eur": 2e6},
             {"epc_rating": None, "property_value_eur": 3e6}]
    ok = stranding_rollup(_m(), props)
    assert ok["value_at_stranding_risk_eur"] == 150_000 + 100_000 and ok["n_not_assessed"] == 1 and ok["n_discounted"] == 2
    partial = {k: v for k, v in STATED.items() if k[1] != "E"}
    bad = stranding_rollup(_m(partial), props)
    assert "value_at_stranding_risk_eur" not in bad and "(E)" in bad["gap"]


def test_collateral_stranding_lifts_the_ltv_and_puts_uncovered_loan_value_at_risk():
    loans = [{"epc_label": "G", "asset_value_eur": 1_000_000, "outstanding_loan_balance_eur": 900_000},
             {"epc_label": "A", "asset_value_eur": 1_000_000, "outstanding_loan_balance_eur": 500_000}]
    r = bank_collateral_stranding_rollup(_m(), loans)
    assert r["collateral_value_at_risk_eur"] == 150_000
    assert r["loan_value_at_risk_eur"] == 50_000                                    # 900k loan on 850k stressed collateral
    assert r["exposure_weighted_ltv_pct"] < r["stressed_ltv_pct"]
    no_balance = bank_collateral_stranding_rollup(_m(), [{**loans[0], "outstanding_loan_balance_eur": None}])
    assert no_balance["n_not_assessed"] == 1 and no_balance["loan_value_at_risk_eur"] == 0
