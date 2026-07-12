"""Emissions-estimation coefficient math — the honest fallback when an issuer's
scope emissions aren't disclosed. These lock in that the estimate is exactly
sector-intensity × revenue, that it degrades safely without inputs, and that
scope 3 is never estimated."""
from services.reference.emissions_estimation import (
    DEFAULT_INTENSITY, _INTENSITIES, estimate_emissions,
)


def test_estimate_is_intensity_times_revenue():
    # NACE 35 (electricity) effective intensity (EXIOBASE-calibrated) × €1,000m revenue.
    intensity = _INTENSITIES["35"]
    out = estimate_emissions("35.11", 1_000_000_000)
    assert out["scope1_2_tco2e"] == round(intensity * 1000)
    assert out["intensity_tco2e_per_meur"] == intensity
    assert "nace_intensity_x_revenue" in out["method"]


def test_uses_division_prefix_not_full_code():
    # "20.13" and "20" must resolve to the same division intensity.
    assert estimate_emissions("20.13", 5e8)["intensity_tco2e_per_meur"] == \
        estimate_emissions("20", 5e8)["intensity_tco2e_per_meur"]


def test_unknown_division_uses_flagged_default():
    out = estimate_emissions("99", 1_000_000_000)  # no such division
    assert out["intensity_tco2e_per_meur"] == DEFAULT_INTENSITY
    assert out["method"].endswith(":default_division")


def test_missing_inputs_return_none_not_zero():
    assert estimate_emissions(None, 1e9) is None       # no sector
    assert estimate_emissions("35", None) is None       # no revenue
    assert estimate_emissions("35", 0) is None          # non-positive revenue
    assert estimate_emissions("35", -5) is None


def test_scope3_is_never_estimated():
    out = estimate_emissions("20", 1e9)
    # The estimate is a combined scope 1+2 figure only — no scope 3 key.
    assert "scope1_2_tco2e" in out
    assert "scope3" not in out and "scope_3" not in out
