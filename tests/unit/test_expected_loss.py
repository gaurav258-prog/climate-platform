"""Near-term climate expected-loss math (services.intelligence.expected_loss)."""
from services.intelligence.expected_loss import (
    annual_expected_loss,
    lifetime_expected_loss,
    score_at_year,
)


def test_annual_el_is_exposure_times_prob_times_severity():
    r = annual_expected_loss(1_000_000, 80.0, hazard="flood")
    # EL ≈ EAD × p_event × damage_ratio (components are independently rounded, so allow a small tolerance)
    recon = 1_000_000 * r["p_event"] * r["damage_ratio"]
    assert abs(r["annual_el_eur"] - recon) <= max(1.0, 0.005 * recon)
    assert r["annual_el_eur"] > 0 and 0 < r["p_event"] < 1 and 0 < r["damage_ratio"] < 1


def test_annual_el_monotonic_in_score():
    lo = annual_expected_loss(1_000_000, 30.0, hazard="flood")["annual_el_eur"]
    hi = annual_expected_loss(1_000_000, 80.0, hazard="flood")["annual_el_eur"]
    assert hi > lo


def test_zero_when_no_exposure_or_no_score():
    assert annual_expected_loss(0, 80.0)["annual_el_eur"] == 0.0
    assert annual_expected_loss(1_000_000, None)["annual_el_eur"] == 0.0


def test_score_at_year_interpolates_between_nodes():
    nodes = {2025: 40.0, 2030: 60.0}
    assert score_at_year(0, nodes) == 40.0            # now
    assert score_at_year(5, nodes) == 60.0            # 2030
    assert abs(score_at_year(2.5, nodes) - 50.0) < 1e-9   # midpoint
    # flat beyond the last node
    assert score_at_year(50, nodes) == 60.0


def test_lifetime_el_grows_with_tenor_and_respects_maturity():
    nodes = {2025: 50.0, 2030: 70.0, 2050: 85.0}
    short = lifetime_expected_loss(1_000_000, nodes, tenor_years=3)
    long = lifetime_expected_loss(1_000_000, nodes, tenor_years=10)
    assert long > short > 0            # a longer loan accumulates more expected loss
    assert lifetime_expected_loss(1_000_000, nodes, tenor_years=0) == 0.0
