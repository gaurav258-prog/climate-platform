"""Portfolio catastrophe accumulation — the common-shock Monte-Carlo must (a) reconcile its mean annual
loss to the independent EAL sum, (b) show a tail (AEP/OEP/PML) above the mean, (c) be deterministic, and
(d) produce a fatter tail when policies share an accumulation zone than when they're spread across zones.
Pure — synthetic policies, seeded RNG, no DB."""
from ml.scoring.cat_accumulation import catastrophe_accumulation


def _policy(loss, prob, hazard, region):
    return {"headline_hazard": hazard, "region": region, "headline_score": 80,
            "pricing": {"net_scenario_loss_eur": loss, "annual_occurrence_prob": prob,
                        "expected_annual_loss_eur": loss * prob}}


def _book(hazard_region_pairs, loss=10_000_000, prob=0.04):
    return [_policy(loss, prob, hz, rg) for hz, rg in hazard_region_pairs]


def test_mean_reconciles_to_independent_eal_sum():
    book = _book([("flood", "A")] * 20 + [("wildfire", "B")] * 20)
    r = catastrophe_accumulation(book, "org1", "baseline", "current")
    assert r["available"]
    assert r["mean_reconciles"]  # simulated mean within 5% of the independent EAL sum
    assert abs(r["mean_annual_loss_eur"] - r["sum_independent_eal_eur"]) <= 0.05 * r["sum_independent_eal_eur"]


def test_tail_exceeds_the_mean():
    book = _book([("flood", "A")] * 30)
    r = catastrophe_accumulation(book, "org1", "baseline", "current")
    assert r["aep_eur"]["rp_250"] > r["mean_annual_loss_eur"]
    assert r["pml_eur"] > r["mean_annual_loss_eur"]
    assert r["aep_eur"]["rp_250"] >= r["aep_eur"]["rp_10"]  # monotone up the return periods


def test_deterministic_same_seed():
    book = _book([("flood", "A")] * 15 + [("storm", "C")] * 10)
    a = catastrophe_accumulation(book, "orgX", "disorderly_2c", "2050")
    b = catastrophe_accumulation(book, "orgX", "disorderly_2c", "2050")
    assert a["pml_eur"] == b["pml_eur"] and a["aep_eur"] == b["aep_eur"]


def test_correlation_fattens_the_tail():
    # Same 24 policies, same marginals. Concentrated: all in ONE (peril, region) zone → one event hits all.
    # Diversified: spread across 8 zones → events are independent, so the aggregate tail is thinner.
    concentrated = _book([("flood", "A")] * 24)
    diversified = _book([("flood", f"R{i % 8}") for i in range(24)])
    rc = catastrophe_accumulation(concentrated, "org1", "baseline", "current")
    rd = catastrophe_accumulation(diversified, "org1", "baseline", "current")
    # Means reconcile for both (marginals identical); the concentrated book's 1-in-250 is materially larger.
    assert rc["aep_eur"]["rp_250"] > rd["aep_eur"]["rp_250"]
    assert rc["tail_to_mean_multiple"] > rd["tail_to_mean_multiple"]


def test_no_priced_policies_is_unavailable():
    assert catastrophe_accumulation([], "o", "s", "h")["available"] is False
    unpriced = [{"headline_hazard": "flood", "region": "A", "pricing": None}]
    assert catastrophe_accumulation(unpriced, "o", "s", "h")["available"] is False
