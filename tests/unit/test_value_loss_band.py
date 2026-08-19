"""The shared portfolio value-loss band — propagates each asset's per-cell score confidence interval
(ci_lo/ci_hi) through the continuous haircut into a portfolio €-range. Honest by construction: overrides
carry no band, assets without a modelled CI contribute their point only. Pure — no DB."""
from ml.scoring.valuation_discount import value_loss_band


def _asset(value, score, ci_lo, ci_hi, hazard="flood", overridden=False, eff=None):
    return {
        "value_eur": value, "headline_score": score, "headline_hazard": hazard,
        "headline_bucket": "H" if score and score >= 60 else "M",
        "hazards": [{"hazard": hazard, "score": score, "ci_lo": ci_lo, "ci_hi": ci_hi}],
        "valuation": {"is_overridden": overridden, "effective_discount_pct": eff, "severity_model": "universal"},
    }


def test_band_brackets_the_point_and_is_ordered():
    assets = [_asset(100_000_000, 70, 55, 85), _asset(50_000_000, 40, 30, 55)]
    b = value_loss_band(assets)
    assert b["loss_low_eur"] <= b["expected_value_loss_eur"] <= b["loss_high_eur"]
    assert b["band_pct"] > 0
    assert 0 < b["ci_coverage_pct"] <= 100


def test_no_ci_gives_point_only_no_band():
    # ci_lo/ci_hi absent → the asset contributes its point to low and high alike, and no coverage.
    assets = [_asset(100_000_000, 70, None, None)]
    b = value_loss_band(assets)
    assert b["loss_low_eur"] == b["expected_value_loss_eur"] == b["loss_high_eur"]
    assert b["ci_coverage_pct"] == 0.0
    assert b["band_pct"] == 0.0


def test_override_carries_no_band():
    # An overridden valuation is a fixed human number — its loss is the same in low/point/high.
    assets = [_asset(100_000_000, 70, 55, 85, overridden=True, eff=25.0)]
    b = value_loss_band(assets)
    expected = round(100_000_000 * 0.25)
    assert b["loss_low_eur"] == b["expected_value_loss_eur"] == b["loss_high_eur"] == expected
    assert b["ci_coverage_pct"] == 0.0  # overridden value is not counted as modelled-banded


def test_wider_ci_widens_the_band():
    narrow = value_loss_band([_asset(100_000_000, 70, 65, 75)])
    wide = value_loss_band([_asset(100_000_000, 70, 45, 95)])
    assert (wide["loss_high_eur"] - wide["loss_low_eur"]) > (narrow["loss_high_eur"] - narrow["loss_low_eur"])


def test_empty_and_unscored_are_safe():
    assert value_loss_band([])["expected_value_loss_eur"] == 0
    unscored = [{"value_eur": 100, "headline_score": None, "headline_bucket": None, "hazards": [], "valuation": {}}]
    b = value_loss_band(unscored)
    assert b["expected_value_loss_eur"] == 0 and b["ci_coverage_pct"] == 0
