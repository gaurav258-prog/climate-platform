"""Re-sourcing / origin-substitution — the pure reallocation math: shift a bounded share of a commodity's
spend from its highest-risk to its lowest-risk EXISTING origin, and report the avoided COGS-at-risk. Single-
origin commodities are flagged as needing a new origin, never given a fabricated one. Pure — no DB."""
from services.intelligence.resourcing import REALLOC_CAP, evaluate_commodity


def _o(code, ys, spend):
    return {"origin": code, "name": code, "yield_shock_pct": ys, "spend_eur": spend}


def test_opportunity_shifts_worst_to_best_within_cap():
    # wheat: Australia 3.4% vs Morocco 0.0%, €10m each → shift ≤30% of €20m = €6m at a 3.4pt gap
    ev = evaluate_commodity("Wheat", [_o("AU", 3.4, 10_000_000), _o("MA", 0.0, 10_000_000)])
    assert ev["kind"] == "opportunity"
    assert ev["from_origin"] == "AU" and ev["to_origin"] == "MA"
    shift = min(10_000_000, REALLOC_CAP * 20_000_000)      # capped at €6m
    assert ev["shift_spend_eur"] == round(shift)
    assert ev["avoidable_eur"] == round(shift * (3.4 - 0.0) / 100.0)


def test_single_origin_needs_a_new_origin():
    ev = evaluate_commodity("Olive oil", [_o("ES", 12.0, 40_000_000)])
    assert ev["kind"] == "single"
    assert ev["origin"] == "ES"
    assert ev["cogs_at_risk_eur"] == round(0.12 * 40_000_000)


def test_already_concentrated_on_lowest_risk_has_no_opportunity():
    # both origins at the same (lowest) risk → nothing to gain by moving
    ev = evaluate_commodity("Coffee", [_o("BR", 5.0, 10_000_000), _o("CO", 5.0, 10_000_000)])
    assert ev["kind"] == "concentrated"


def test_reallocation_is_capped_not_the_whole_book():
    # one huge worst origin: the shift is bounded by the cap, not the worst origin's full spend
    ev = evaluate_commodity("Cocoa", [_o("GH", 20.0, 90_000_000), _o("CI", 10.0, 10_000_000)])
    assert ev["shift_spend_eur"] == round(REALLOC_CAP * 100_000_000)   # 30% of €100m, not €90m
    # avoided uses the 10pt gap on the capped shift
    assert ev["avoidable_eur"] == round(REALLOC_CAP * 100_000_000 * (20.0 - 10.0) / 100.0)


def test_empty_is_none():
    assert evaluate_commodity("X", [])["kind"] == "none"


def test_reallocation_cap_is_configurable():
    origins = [_o("GH", 20.0, 50_000_000), _o("CI", 10.0, 50_000_000)]
    at30 = evaluate_commodity("Cocoa", origins, cap=0.30)
    at60 = evaluate_commodity("Cocoa", origins, cap=0.60)
    # a higher cap shifts more spend → avoids more (bounded by the worst origin's spend)
    assert at60["shift_spend_eur"] > at30["shift_spend_eur"]
    assert at60["avoidable_eur"] > at30["avoidable_eur"]
