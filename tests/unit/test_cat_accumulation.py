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


def test_pml_return_period_is_configurable():
    # a spread of zones so the OEP curve isn't saturated → the PML read point actually matters
    book = _book([("flood", f"R{i}") for i in range(12)] + [("storm", f"S{i}") for i in range(12)])
    r250 = catastrophe_accumulation(book, "org1", "baseline", "current", pml_return_period=250)
    r200 = catastrophe_accumulation(book, "org1", "baseline", "current", pml_return_period=200)
    assert r250["pml_return_period"] == 250 and r200["pml_return_period"] == 200
    # the chosen period is always present in the reported ladders (Solvency II 1-in-200)
    assert "rp_200" in r200["aep_eur"] and "rp_200" in r200["oep_eur"]
    # a longer return period can never give a SMALLER PML (monotone tail)
    assert r250["pml_eur"] >= r200["pml_eur"]


def test_no_priced_policies_is_unavailable():
    assert catastrophe_accumulation([], "o", "s", "h")["available"] is False
    unpriced = [{"headline_hazard": "flood", "region": "A", "pricing": None}]
    assert catastrophe_accumulation(unpriced, "o", "s", "h")["available"] is False


def _ids(book):
    return [{**p, "policy_id": f"p{i}"} for i, p in enumerate(book)]


def test_scenarios_replay_the_same_years():
    """Common random numbers: the scenario is not in the seed, so a warmer book (higher occurrence rates, bigger
    losses) is the same simulated years with more loss — never fewer losses by chance."""
    base = _ids(_book([("flood", "A")] * 10 + [("storm", "B")] * 10, prob=0.03))
    warm = [{**p, "pricing": {**p["pricing"], "annual_occurrence_prob": 0.045,
                              "net_scenario_loss_eur": p["pricing"]["net_scenario_loss_eur"] * 1.2,
                              "expected_annual_loss_eur": p["pricing"]["net_scenario_loss_eur"] * 1.2 * 0.045}} for p in base]
    a = catastrophe_accumulation(base, "org1", "baseline", "current")
    b = catastrophe_accumulation(warm, "org1", "hot_house_3_5c", "2050")
    for t in ("rp_10", "rp_50", "rp_100", "rp_200", "rp_250"):
        assert b["aep_eur"][t] >= a["aep_eur"][t] and b["oep_eur"][t] >= a["oep_eur"][t], t
    same = catastrophe_accumulation(base, "org1", "hot_house_3_5c", "2050")       # same book, other scenario label
    assert same["aep_eur"] == a["aep_eur"] and same["oep_eur"] == a["oep_eur"]


def test_net_of_reinsurance_event_by_event():
    """Hand-checkable limits: a 50 % quota share halves every loss; a cat layer covering everything above 0 leaves no
    net occurrence loss; and the per-occurrence layer now also reduces the aggregate (AEP) view."""
    book = _ids(_book([("flood", "A")] * 12, loss=5_000_000, prob=0.05))
    gross = catastrophe_accumulation(book, "o", "baseline", "current")
    half = catastrophe_accumulation(book, "o", "baseline", "current", reinsurance={"quota_share_pct": 50})
    assert abs(half["net_of_reinsurance"]["net_aep_eur"]["rp_200"] - gross["aep_eur"]["rp_200"] / 2) <= 1
    assert abs(half["net_of_reinsurance"]["net_oep_eur"]["rp_200"] - gross["oep_eur"]["rp_200"] / 2) <= 1
    full = catastrophe_accumulation(book, "o", "baseline", "current",
                                    reinsurance={"quota_share_pct": 0, "xol_attachment_eur": 0, "xol_limit_eur": 1e12})
    assert full["net_of_reinsurance"]["net_oep_eur"]["rp_200"] == 0 and full["net_of_reinsurance"]["net_aep_eur"]["rp_200"] == 0
    layer = {"quota_share_pct": 20, "xol_attachment_eur": 10_000_000, "xol_limit_eur": 20_000_000}
    lay = catastrophe_accumulation(book, "o", "baseline", "current", reinsurance=layer)["net_of_reinsurance"]
    assert lay["net_aep_eur"]["rp_200"] < 0.8 * gross["aep_eur"]["rp_200"]         # the layer recovers in the AEP too
    # the largest event, one zone: 12 × 5m = 60m gross → 48m after 20 % QS → 20m recovered above 10m → 28m net
    assert lay["net_oep_eur"]["rp_250"] <= 28_000_000


def test_held_zones_keep_a_comparison_about_the_climate():
    """A policy whose headline hazard changes between scenarios regroups the zones unless they are held fixed."""
    base = _ids(_book([("flood", "A")] * 10 + [("storm", "A")] * 10, prob=0.03))
    moved = [{**p, "headline_hazard": "storm"} if i < 5 else p for i, p in enumerate(base)]     # same losses, new headline
    zones = {p["policy_id"]: (p["headline_hazard"], p["region"]) for p in base}
    held = catastrophe_accumulation(moved, "o", "hot_house_3_5c", "2050", zones_of=zones)
    ref = catastrophe_accumulation(base, "o", "baseline", "current")
    assert held["aep_eur"] == ref["aep_eur"] and held["oep_eur"] == ref["oep_eur"]
