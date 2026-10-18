"""The Portfolio screen's server text (UI standard, product owner 2026-10-16): every explanation a book engine sends the
screen is a message of the catalogue (core/messages.py) — a label and its what/why in customer words, rendered where
the figure is computed — never a sentence written in the engine, and a hazard is named, never shown by its key. A
missing method choice is one 'not stated: …' list, the format the screens name in customer words. Pure — no database.
"""
from __future__ import annotations

from datetime import date

from core import messages
from core.types import HAZARD_VALUES
from ml.scoring.cat_accumulation import catastrophe_accumulation
from ml.scoring.epc_stranding import bank_collateral_stranding_rollup, stranding_rollup
from ml.scoring.insurance_pricing import price_perils
from ml.scoring.valuation_discount import VAR_SIMULATIONS, valuation_block, value_loss_band
from services.intelligence.resilience_capex import resilience_capex_plan
from services.money.params import Method
from services.scoring.combined_var import combined_climate_var
from services.scoring.loan_transition import loan_transition_overlay
from services.scoring.portfolio_concentration import portfolio_concentration

PE = date(2025, 12, 31)
S, H = "disorderly_2c", "2030"
# test values for the mechanics only — nobody's method
STATED = {("method.valuation_haircut", "flood/M"): 0.05, ("method.valuation_haircut", "flood/H"): 0.15,
          ("method.valuation_haircut", "flood/VH"): 0.30, ("method.valuation_haircut", "heat_chronic/H"): 0.10,
          ("method.damage_ratio", "flood/H"): 0.40, ("method.annual_event_probability", "flood/H"): 0.01,
          ("method.expense_ratio", None): 0.25, ("method.profit_margin", None): 0.05,
          ("method.var_relative_uncertainty", None): 0.4, ("method.transition_var_relative_uncertainty", None): 0.5,
          ("method.stranded_share", f"any@{S}/{H}"): 0.02, ("method.carbon_price", f"{S}/{H}"): 150.0,
          ("method.adaptation_effectiveness", "flood"): 0.5, ("method.resilience_capex_share", "H"): 0.025,
          **{("method.brown_discount", g): v for g, v in zip("ABCDEFG", (0, 0, 0, 0, 0.05, 0.10, 0.15))},
          **{("method.retrofit_capex_share", g): v for g, v in zip("ABCDEFG", (0, 0, 0, 0, 0.04, 0.08, 0.12))}}
PROSE = ("method", "note", "basis")


def _m(values=STATED):
    return Method.of(values, PE)


def _is_catalogue(msg: dict) -> None:
    """A rendered message: a code of the catalogue, its label, and the detail behind the screen's pop-up."""
    entry = messages.catalogue()[msg["code"]]
    assert msg["code"].startswith("portfolio.") and msg["label"] and msg["detail"]["what"]
    assert not messages.INTERNAL.search(msg["label"] + " ".join(msg["detail"].values())), msg
    assert entry["label"].split("{")[0] in msg["label"]


def _no_prose(result: dict) -> None:
    """No explanation is a sentence written in the engine (the screen would print it as it stands)."""
    assert not [k for k in PROSE if isinstance(result.get(k), str)], [k for k in PROSE if isinstance(result.get(k), str)]


def _holding(hazard, region, value=1_000_000, score=60):
    return {"position_value_eur": value, "headline_score": score, "headline_hazard": hazard, "headline_bucket": "H",
            "region": region, "nace_code": "24.10", "hazards": [], "valuation": {},
            "climate_var": valuation_block(_m(), "H", value, None, hazard=hazard, score=score)}


def test_each_book_engine_explains_itself_with_a_catalogue_message():
    assets = [{"value_eur": 1_000_000, "headline_score": 60, "headline_hazard": "flood",
               "hazards": [{"hazard": "flood", "ci_lo": 45, "ci_hi": 80}], "valuation": {}}]
    loans = [{"asset_id": "l1", "asset_name": "Co", "nace_code": "24.10", "revenue_eur": 1e8, "ghg1": 1000, "ghg2": 0,
              "ghg3": None, "outstanding_loan_balance_eur": 1e7, "value_eur": 2e7}]
    props = [{"property_value_eur": 10_000_000, "headline_score": 60, "headline_hazard": "flood", "valuation": {}, "epc_rating": "F"}]
    collateral = [{"epc_label": "F", "asset_value_eur": 2e6, "outstanding_loan_balance_eur": 1e6}]
    pol = {"policy_id": "p1", "region": "A", "pricing": price_perils(_m(), [{"hazard": "flood", "score": 60}], 1_000_000)}
    results = {
        "value loss band": (value_loss_band(_m(), assets), "method_message"),
        "combined value at risk": (combined_climate_var(_m(), [_holding("flood", "A")], "o", S, H, VAR_SIMULATIONS, "independent"), "method_message"),
        "resilience": (resilience_capex_plan(_m(), props), "method_message"),
        "loan transition": (loan_transition_overlay(_m(), loans, S, H), "method_message"),
        "energy stranding": (stranding_rollup(_m(), props), "basis_message"),
        "collateral stranding": (bank_collateral_stranding_rollup(_m(), collateral), "basis_message"),
        "catastrophe": (catastrophe_accumulation([pol], "o", "baseline", "current", pml_return_period=250), "method_message"),
        "concentration": (portfolio_concentration([_holding("flood", "A")]), "method_message"),
    }
    for name, (r, key) in results.items():
        assert key in r, f"{name}: no {key}"
        _is_catalogue(r[key])
        _no_prose(r)


def test_the_net_of_reinsurance_and_a_missing_return_period_are_catalogue_messages():
    pol = {"policy_id": "p1", "region": "A", "pricing": price_perils(_m(), [{"hazard": "flood", "score": 60}], 1_000_000)}
    prog = {"quota_share_pct": 30, "xol_attachment_eur": 1e4, "xol_limit_eur": 5e4}
    net = catastrophe_accumulation([pol], "o", "baseline", "current", pml_return_period=250, reinsurance=prog)["net_of_reinsurance"]
    _is_catalogue(net["basis_message"])
    _no_prose(net)
    none = catastrophe_accumulation([pol], "o", "baseline", "current", pml_return_period=None)
    _is_catalogue(none["pml_gap_message"])
    assert none["pml_gap"].startswith("not stated:")          # the filing annex and the risk indicators read this one


def test_a_combined_figure_without_its_dependence_choice_says_so_in_customer_words():
    r = combined_climate_var(_m(), [_holding("flood", "A")], "o", S, H, VAR_SIMULATIONS, None)
    assert r["available"] is False and r["gap_message"]["code"] == "portfolio.combined_var.no_dependence"
    _is_catalogue(r["gap_message"])
    assert not messages.INTERNAL.search(r["gap"])


def test_a_concentration_names_its_hazard_and_region_in_customer_words():
    book = [_holding("heat_chronic", "Valencia", 5_000_000)] + [_holding("flood", f"R{i}", 100_000) for i in range(3)]
    flags = portfolio_concentration(book)["flags"]
    codes = {f["code"] for f in flags}
    assert {"portfolio.concentration.region", "portfolio.concentration.hazard", "portfolio.concentration.diversification"} <= codes
    hazard = next(f for f in flags if f["code"] == "portfolio.concentration.hazard")
    assert "Rising average heat" in hazard["label"] and "heat_chronic" not in hazard["label"]
    for f in flags:
        _is_catalogue(f)


def test_a_missing_haircut_is_one_not_stated_list_the_screens_can_name():
    v = valuation_block(_m({}), "H", 1_000_000, None, hazard="flood", score=60)
    assert v["gap"] == "not stated: method.valuation_haircut (flood/H)"
    book = [{**_holding("flood", "A"), "climate_var": v},
            {**_holding("drought", "B"), "climate_var": valuation_block(_m({}), "M", 1, None, hazard="drought", score=40)}]
    gap = portfolio_concentration(book)["gap"]
    assert gap == "not stated: method.valuation_haircut (drought/M), method.valuation_haircut (flood/H)"


def test_the_catalogue_names_every_hazard_the_engine_scores():
    names = messages.names()["hazard"]
    assert set(HAZARD_VALUES) <= set(names), sorted(set(HAZARD_VALUES) - set(names))
    assert not [n for n in names.values() if messages.INTERNAL.search(n)]
    assert set(messages.names()["dependence"]) == {"independent", "additive", "max"}
