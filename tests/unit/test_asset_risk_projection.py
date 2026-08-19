"""
Tests for asset risk projection (reconciliation step #1).

Locks the contract that an asset's physical risk IS the canonical score for its
H3 cell — derived, latest-wins, provenance-explicit — never an independently
stored value.
"""

from datetime import datetime, timezone

from services.intelligence.asset_risk_projection import (
    Asset,
    CanonicalScoreRow,
    project,
)


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, tzinfo=timezone.utc)


def test_asset_inherits_canonical_score_and_derived_bucket():
    assets = [Asset(asset_id="A1", h3_cell="cell_munich")]
    scores = [CanonicalScoreRow(
        h3_cell="cell_munich", hazard_type="flood", scenario="baseline",
        time_horizon="current", risk_score=82.0, scored_at=_dt(20),
        model_version="flood-v3",
    )]
    [risk] = project(assets, scores)
    assert risk.risk_score == 82.0
    assert risk.risk_bucket == "VH"          # derived via score_to_bucket, not stored
    assert risk.source == "canonical"
    assert risk.model_version == "flood-v3"


def test_latest_current_score_wins():
    assets = [Asset(asset_id="A1", h3_cell="c")]
    scores = [
        CanonicalScoreRow("c", "flood", "baseline", "current", 40.0, _dt(10), "v1"),
        CanonicalScoreRow("c", "flood", "baseline", "current", 70.0, _dt(20), "v2"),
    ]
    [risk] = project(assets, scores)
    assert risk.risk_score == 70.0
    assert risk.model_version == "v2"


def test_retired_scores_ignored():
    assets = [Asset(asset_id="A1", h3_cell="c")]
    scores = [
        CanonicalScoreRow("c", "flood", "baseline", "current", 90.0, _dt(25), "v3",
                          valid_to=_dt(26)),  # retired
        CanonicalScoreRow("c", "flood", "baseline", "current", 30.0, _dt(20), "v2"),
    ]
    [risk] = project(assets, scores)
    assert risk.risk_score == 30.0           # the current one, not the higher retired one


def test_scenario_dialect_normalizes_in():
    """A caller asking for IPCC '1.5c' matches NGFS 'orderly_1_5c' scores."""
    assets = [Asset(asset_id="A1", h3_cell="c")]
    scores = [CanonicalScoreRow(
        "c", "flood", "orderly_1_5c", "2030", 55.0, _dt(20), "v1",
    )]
    [risk] = project(assets, scores, scenario="1.5c", time_horizon="2030")
    assert risk.risk_score == 55.0
    assert risk.scenario == "orderly_1_5c"
    assert risk.risk_bucket == "H"


def test_unscored_asset_reports_no_data_not_zero():
    assets = [
        Asset(asset_id="A1", h3_cell="scored_cell"),
        Asset(asset_id="A2", h3_cell="unscored_cell"),
    ]
    scores = [CanonicalScoreRow(
        "scored_cell", "flood", "baseline", "current", 60.0, _dt(20), "v1",
    )]
    risks = {(r.asset_id, r.hazard_type): r for r in project(assets, scores)}
    assert risks[("A1", "flood")].risk_score == 60.0
    a2 = risks[("A2", "flood")]
    assert a2.risk_score is None              # NOT a silent 0
    assert a2.source == "no_canonical_score"


def test_multiple_hazards_per_asset():
    assets = [Asset(asset_id="A1", h3_cell="c")]
    scores = [
        CanonicalScoreRow("c", "flood", "baseline", "current", 80.0, _dt(20), "v1"),
        CanonicalScoreRow("c", "heat_acute", "baseline", "current", 45.0, _dt(20), "v1"),
    ]
    by_hazard = {r.hazard_type: r for r in project(assets, scores)}
    assert by_hazard["flood"].risk_bucket == "VH"
    assert by_hazard["heat_acute"].risk_bucket == "M"


def test_asset_without_h3_cell_is_unscored():
    assets = [Asset(asset_id="A1", h3_cell=None)]
    scores = [CanonicalScoreRow("c", "flood", "baseline", "current", 80.0, _dt(20), "v1")]
    risks = project(assets, scores)
    assert all(r.source == "no_canonical_score" for r in risks)
