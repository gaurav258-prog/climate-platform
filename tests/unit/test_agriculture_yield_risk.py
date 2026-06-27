"""
Tests for the agriculture sector (third sector on canonical_scores).

Beyond the standard additivity checks, this exercises what makes agriculture
distinct: multi-hazard combination (drought + heat) and crop-specific sensitivity.
"""

from datetime import datetime, timezone

import pytest

from services.intelligence.asset_risk_projection import CanonicalScoreRow
from services.intelligence.agriculture_yield_risk import (
    FarmParcel, assess_parcels, combined_yield_loss, portfolio_summary,
    CROP_SENSITIVITY,
)


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, tzinfo=timezone.utc)


def _score(cell, score, hazard, scenario="baseline", horizon="current"):
    return CanonicalScoreRow(cell, hazard, scenario, horizon, score, _dt(20), "v1")


def _parcel(pid="P1", cell="c", crop="wheat", ha=100.0, yld=8.0, price=200.0):
    return FarmParcel(pid, cell, crop, ha, yld, price)


# ── Multi-hazard combination ─────────────────────────────────────────────────

def test_drought_and_heat_combine_to_more_than_either_alone():
    drought_only = combined_yield_loss("wheat", {"drought": 80})
    heat_only = combined_yield_loss("wheat", {"heat_acute": 80})
    both = combined_yield_loss("wheat", {"drought": 80, "heat_acute": 80})
    assert both > drought_only
    assert both > heat_only
    # independent-stressor combination, never exceeds 100% loss
    assert both <= 1.0


def test_parcel_uses_both_drought_and_heat_scores():
    parcels = [_parcel(crop="maize")]
    scores = [_score("c", 70, "drought"), _score("c", 90, "heat_acute")]
    [r] = assess_parcels(parcels, scores)
    assert set(r.hazard_scores) == {"drought", "heat_acute"}
    assert r.source == "canonical"
    assert 0 < r.yield_loss_fraction < 1
    assert r.revenue_at_risk > 0


# ── Crop sensitivity differentiates ──────────────────────────────────────────

def test_crop_sensitivity_changes_loss():
    # rice is more drought-sensitive than barley (per the placeholder model)
    assert CROP_SENSITIVITY["rice"].drought > CROP_SENSITIVITY["barley"].drought
    rice_loss = combined_yield_loss("rice", {"drought": 80})
    barley_loss = combined_yield_loss("barley", {"drought": 80})
    assert rice_loss > barley_loss


def test_unknown_crop_uses_default_sensitivity():
    # should not raise; falls back to DEFAULT_SENSITIVITY
    loss = combined_yield_loss("dragonfruit", {"drought": 50})
    assert 0 < loss < 1


# ── Revenue math ─────────────────────────────────────────────────────────────

def test_revenue_at_risk_scales_with_area_and_price():
    small = _parcel(pid="s", ha=10, yld=8, price=200)
    big = _parcel(pid="b", ha=100, yld=8, price=200)
    scores = [_score("c", 60, "drought")]
    out = {r.parcel_id: r for r in assess_parcels([small, big], scores)}
    assert out["b"].revenue_at_risk == pytest.approx(out["s"].revenue_at_risk * 10)


# ── Honesty rule ─────────────────────────────────────────────────────────────

def test_parcel_without_score_is_not_assessed():
    parcels = [_parcel(pid="P1", cell="unscored")]
    scores = [_score("other", 80, "drought")]
    [r] = assess_parcels(parcels, scores)
    assert r.yield_loss_fraction is None
    assert r.revenue_at_risk is None
    assert r.source == "no_canonical_score"


def test_non_yield_hazard_does_not_trigger_assessment():
    # a flood score on the parcel's cell must not produce a yield loss
    parcels = [_parcel(cell="c")]
    scores = [_score("c", 95, "flood")]
    [r] = assess_parcels(parcels, scores)
    assert r.source == "no_canonical_score"


# ── Portfolio roll-up ────────────────────────────────────────────────────────

def test_portfolio_summary():
    parcels = [
        _parcel(pid="a", cell="c1", crop="maize", ha=50),
        _parcel(pid="b", cell="c2", crop="wheat", ha=80),
        _parcel(pid="c", cell="none", crop="soy", ha=30),
    ]
    scores = [_score("c1", 70, "drought"), _score("c2", 60, "heat_acute")]
    s = portfolio_summary(assess_parcels(parcels, scores))
    assert s["parcels_assessed"] == 2
    assert s["parcels_unassessed"] == 1
    assert s["total_revenue_at_risk"] > 0
    assert s["unassessed_reasons"] == ["no_canonical_score"]


# ── Scenario dialect normalizes in (shared vocabulary) ───────────────────────

def test_scenario_dialect_normalizes():
    parcels = [_parcel(cell="c")]
    scores = [_score("c", 60, "drought", scenario="orderly_1_5c", horizon="2030")]
    [r] = assess_parcels(parcels, scores, scenario="1.5c", time_horizon="2030")
    assert r.source == "canonical"
    assert r.scenario == "orderly_1_5c"
