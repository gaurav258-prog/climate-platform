"""
Tests for the canonical vocabulary (core/types.py).

These lock the consistency-by-design contract: every dialect that exists
anywhere in the stack (platform / bank SQL / UI CSV templates) must normalize
to exactly one canonical value, and anything unknown must fail loudly.
"""

import pytest

from core.types import (
    HazardType, RiskScenario, RiskBucket, TimeHorizon,
    HAZARD_VALUES, SCENARIO_VALUES, TIME_HORIZON_VALUES,
    normalize_hazard, normalize_scenario, normalize_time_horizon,
    score_to_bucket,
)


# ── Canonical values round-trip ──────────────────────────────────────────────

def test_every_canonical_hazard_normalizes_to_itself():
    for value in HAZARD_VALUES:
        assert normalize_hazard(value).value == value


def test_every_canonical_scenario_normalizes_to_itself():
    for value in SCENARIO_VALUES:
        assert normalize_scenario(value).value == value


def test_every_canonical_time_horizon_normalizes_to_itself():
    for value in TIME_HORIZON_VALUES:
        assert normalize_time_horizon(value).value == value


# ── Hazard dialects ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("flood", HazardType.FLOOD),
    ("Flooding", HazardType.FLOOD),
    ("river_flood", HazardType.FLOOD),
    ("heat", HazardType.HEAT_ACUTE),           # bank SQL dialect
    ("Heat_Stress", HazardType.HEAT_ACUTE),    # UI CSV dialect
    ("extreme heat", HazardType.HEAT_ACUTE),
    ("heat_chronic", HazardType.HEAT_CHRONIC),
    ("wildfire", HazardType.WILDFIRE),
    ("earthquake", HazardType.SEISMIC),
    ("drought", HazardType.DROUGHT),
    ("hurricane", HazardType.STORM),
    ("extreme_weather", HazardType.STORM),
])
def test_hazard_dialects_map_to_canonical(raw, expected):
    assert normalize_hazard(raw) == expected


# ── Scenario dialects: NGFS (platform) + IPCC SSP (bank) + UI labels ─────────

@pytest.mark.parametrize("raw,expected", [
    ("orderly_1_5c", RiskScenario.ORDERLY_1_5C),     # platform
    ("1.5c", RiskScenario.ORDERLY_1_5C),             # bank SQL
    ("1.5C_Paris_Aligned", RiskScenario.ORDERLY_1_5C),  # UI CSV
    ("SSP1-2.6", RiskScenario.ORDERLY_1_5C),
    ("2c", RiskScenario.DISORDERLY_2C),
    ("2C_Moderate_Transition", RiskScenario.DISORDERLY_2C),
    ("4c", RiskScenario.HOT_HOUSE_3_5C),             # bank "4c" → hot house archetype
    ("4C_Business_As_Usual", RiskScenario.HOT_HOUSE_3_5C),
    ("BAU", RiskScenario.HOT_HOUSE_3_5C),
    ("baseline", RiskScenario.BASELINE),
])
def test_scenario_dialects_map_to_canonical(raw, expected):
    assert normalize_scenario(raw) == expected


# ── Time horizon dialects: bank (short/medium/long) → platform (years) ───────

@pytest.mark.parametrize("raw,expected", [
    ("short_term", TimeHorizon.Y2030),
    ("medium_term", TimeHorizon.Y2050),
    ("long_term", TimeHorizon.Y2100),
    ("2030", TimeHorizon.Y2030),
    ("current", TimeHorizon.CURRENT),
    ("now", TimeHorizon.CURRENT),
])
def test_time_horizon_dialects_map_to_canonical(raw, expected):
    assert normalize_time_horizon(raw) == expected


# ── Drift fails loudly ───────────────────────────────────────────────────────

def test_unknown_hazard_raises():
    with pytest.raises(ValueError, match="unknown hazard"):
        normalize_hazard("tsunami")


def test_unknown_scenario_raises():
    with pytest.raises(ValueError, match="unknown scenario"):
        normalize_scenario("rcp_8_5")


def test_unknown_time_horizon_raises():
    with pytest.raises(ValueError, match="unknown time horizon"):
        normalize_time_horizon("2075")


# ── Bucket thresholds: one definition of score→bucket ───────────────────────

@pytest.mark.parametrize("score,bucket", [
    (0, RiskBucket.L), (24.9, RiskBucket.L),
    (25, RiskBucket.M), (49.9, RiskBucket.M),
    (50, RiskBucket.H), (74.9, RiskBucket.H),
    (75, RiskBucket.VH), (100, RiskBucket.VH),
])
def test_score_to_bucket(score, bucket):
    assert score_to_bucket(score) == bucket


@pytest.mark.parametrize("bad", [-1, 101])
def test_score_to_bucket_out_of_range_raises(bad):
    with pytest.raises(ValueError):
        score_to_bucket(bad)
