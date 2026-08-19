"""Property resilience-capex plan — avoided loss (physical loss × disclosed adaptation effectiveness) vs a
disclosed reference retrofit capex, per property and rolled up. Pure — synthetic properties, no DB."""
from services.intelligence.resilience_capex import (
    RESILIENCE_CAPEX_PCT,
    resilience_capex_plan,
)


def _prop(value, score, hazard="flood", bucket="H"):
    return {"property_id": f"{hazard}-{score}", "property_name": "P", "property_value_eur": value,
            "headline_score": score, "headline_bucket": bucket, "headline_hazard": hazard,
            "valuation": {"severity_model": "universal"}}


def test_avoided_loss_is_below_physical_and_capex_is_a_tier():
    book = [_prop(100_000_000, 80, "flood", "VH")]
    r = resilience_capex_plan(book)
    assert r["available"]
    # effectiveness < 1 → avoided is a fraction of the physical loss
    assert 0 < r["total_avoided_loss_eur"] < r["total_physical_loss_eur"]
    # capex is the disclosed VH tier of value
    assert r["total_resilience_capex_eur"] == round(100_000_000 * RESILIENCE_CAPEX_PCT["VH"] / 100)


def test_benefit_cost_ratio_and_worth_retrofit():
    r = resilience_capex_plan([_prop(100_000_000, 85, "wildfire", "VH")])
    assert r["portfolio_benefit_cost_ratio"] is not None
    top = r["top_properties"][0]
    assert top["benefit_cost_ratio"] == round(top["avoided_loss_eur"] / top["resilience_capex_eur"], 2)
    assert top["worth_retrofit"] == (top["benefit_cost_ratio"] >= 1.0)


def test_taxonomy_aligned_capex_equals_total_capex():
    r = resilience_capex_plan([_prop(50_000_000, 70), _prop(30_000_000, 62, "storm")])
    assert r["taxonomy_adaptation_aligned_capex_eur"] == r["total_resilience_capex_eur"]


def test_by_hazard_and_measures_present():
    r = resilience_capex_plan([_prop(80_000_000, 78, "flood", "H"), _prop(40_000_000, 66, "wildfire", "H")])
    hazards = {h["hazard"] for h in r["by_hazard"]}
    assert "flood" in hazards and "wildfire" in hazards
    # measures reuse the adaptation library — each carries its hazard label + concrete actions
    assert r["recommended_measures"] and r["recommended_measures"][0].get("actions")


def test_higher_severity_has_higher_capex_tier():
    hi = resilience_capex_plan([_prop(100_000_000, 90, "flood", "VH")])
    lo = resilience_capex_plan([_prop(100_000_000, 40, "flood", "M")])
    assert hi["total_resilience_capex_eur"] > lo["total_resilience_capex_eur"]


def test_empty_or_unscored_is_unavailable():
    assert resilience_capex_plan([])["available"] is False
    unscored = [{"property_value_eur": 100, "headline_score": None, "headline_bucket": None}]
    assert resilience_capex_plan(unscored)["available"] is False
