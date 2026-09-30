"""Every insured property peril priced on its own (ml.scoring.insurance_pricing.price_perils) — the foundation the
nat-cat SCR, the ORSA climate scenarios and the recovery stress stand on."""
import pytest

from ml.scoring.insurance_pricing import insured_peril, price_perils, price_policy


def test_only_insured_perils_on_a_likelihood_scale_are_priced():
    assert insured_peril("flood") and insured_peril("seismic") and insured_peril("severe_convective")
    assert not insured_peril("drought") and not insured_peril("heat_chronic") and not insured_peril("pollution")
    assert not insured_peril("subsidence")                                   # the susceptibility class
    assert insured_peril("subsidence", "subsidence-egms-observed-v2")        # the measured EGMS rate
    assert not insured_peril("landslide")                                    # LHASA susceptibility class


def test_the_policy_is_the_sum_of_its_perils():
    hz = [{"hazard": "flood", "score": 70, "model_version": None}, {"hazard": "storm", "score": 50, "model_version": None},
          {"hazard": "drought", "score": 95, "model_version": None}]
    p = price_perils(hz, 1_000_000, 0.0)
    each = {c["hazard"]: c for c in p["perils"]}
    assert set(each) == {"flood", "storm"}                                     # drought is not property damage
    assert p["expected_annual_loss_eur"] == pytest.approx(sum(c["expected_annual_loss_eur"] for c in p["perils"]), abs=0.02)
    assert each["flood"]["expected_annual_loss_eur"] == pytest.approx(price_policy(70, 1_000_000, 0.0, hazard="flood")["expected_annual_loss_eur"])
    assert p["driver_peril"] == max(p["perils"], key=lambda c: c["expected_annual_loss_eur"])["hazard"]


def test_a_changing_headline_cannot_hide_a_peril():
    """Under warming heat can top the scores; the flood loss stays in the policy (the headline-only pricing it
    replaces dropped it, and the 1-in-200 fell as the climate warmed)."""
    today = price_perils([{"hazard": "flood", "score": 60}], 1_000_000)
    warmer = price_perils([{"hazard": "heat_chronic", "score": 90}, {"hazard": "flood", "score": 65}], 1_000_000)
    assert warmer["expected_annual_loss_eur"] >= today["expected_annual_loss_eur"]
    assert price_perils([{"hazard": "drought", "score": 99}], 1_000_000) is None       # nothing insured to price
