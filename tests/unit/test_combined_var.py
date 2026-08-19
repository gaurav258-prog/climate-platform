"""Combined physical + transition climate VaR — one loss distribution over both drivers, combined by
complementary survival so a holding is never lost twice. Pure — synthetic holdings, seeded RNG, no DB."""
from services.scoring.combined_var import combined_climate_var


def _holding(value, score, nace, hazard="flood", ci=(None, None)):
    return {"position_value_eur": value, "headline_score": score,
            "headline_bucket": "H" if score and score >= 60 else "M", "headline_hazard": hazard,
            "nace_code": nace, "hazards": [{"hazard": hazard, "score": score, "ci_lo": ci[0], "ci_hi": ci[1]}]}


def test_combined_never_exceeds_naive_sum_and_at_least_physical():
    book = [_holding(100_000_000, 70, "35.11"), _holding(50_000_000, 55, "62.01")]
    r = combined_climate_var(book, "org1", "disorderly_2c", "2050")
    assert r["available"]
    # complementary survival: combined ≤ physical + transition (no double-count), and ≥ physical alone
    assert r["combined_expected_eur"] <= r["physical_expected_eur"] + r["transition_expected_eur"]
    assert r["combined_expected_eur"] >= r["physical_expected_eur"]


def test_var_percentiles_are_ordered():
    book = [_holding(100_000_000, 75, "05.10", ci=(60, 90))]
    r = combined_climate_var(book, "org1", "disorderly_2c", "2050")
    assert r["median_loss_eur"] <= r["var95_eur"] <= r["var99_eur"]


def test_transition_adds_a_component_for_high_carbon_sector():
    # coal (05) has a stranding thesis → a transition component; a no-thesis sector adds ~none.
    coal = combined_climate_var([_holding(100_000_000, 40, "05.10")], "o", "orderly_1_5c", "2050")
    plain = combined_climate_var([_holding(100_000_000, 40, "88.10")], "o", "orderly_1_5c", "2050")
    assert coal["transition_expected_eur"] > 0
    assert coal["combined_expected_eur"] > plain["combined_expected_eur"]
    assert coal["n_with_transition"] == 1


def test_deterministic_same_seed():
    book = [_holding(100_000_000, 70, "35.11", ci=(55, 85)), _holding(40_000_000, 62, "24.10")]
    a = combined_climate_var(book, "orgZ", "disorderly_2c", "2050")
    b = combined_climate_var(book, "orgZ", "disorderly_2c", "2050")
    assert a["var99_eur"] == b["var99_eur"] and a["median_loss_eur"] == b["median_loss_eur"]


def test_no_scored_positions_is_unavailable():
    assert combined_climate_var([], "o", "s", "h")["available"] is False
    unscored = [{"position_value_eur": 100, "headline_score": None, "headline_bucket": None, "nace_code": "35"}]
    assert combined_climate_var(unscored, "o", "s", "h")["available"] is False
