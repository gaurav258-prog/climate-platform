"""Prior-filings forward projection — the reported series continued from its LAST filed value
(services.governance.prior_filings._project). Compound-annual for clean same-sign series, average-annual
fallback otherwise, and no projection when there's nothing to extrapolate from."""
import pytest

from services.governance.prior_filings import _project


def test_compound_annual_continues_from_last_value():
    pts = [{"period": "2021", "value": 1700000.0}, {"period": "2022", "value": 1640000.0},
           {"period": "2023", "value": 1594585.0}]
    out = _project(pts, horizon_years=3)
    proj = out["projection"]
    assert [p["period"] for p in proj] == ["2024", "2025", "2026"]
    assert "compound" in out["method"]
    # CAGR over 2 years = (1594585/1700000)^(1/2)-1 ≈ -3.15%/yr; first projected point continues the decline
    assert proj[0]["value"] < 1594585.0
    assert pytest.approx(proj[0]["value"], rel=1e-6) == 1594585.0 * (1594585.0 / 1700000.0) ** (1 / 2)


def test_linear_fallback_when_not_positive_same_sign():
    pts = [{"period": "2021", "value": 0.0}, {"period": "2023", "value": 100.0}]  # first == 0 -> linear
    out = _project(pts, horizon_years=2)
    assert "average" in out["method"]
    # avg annual delta = (100-0)/2 = 50 -> 2024=150, 2025=200
    assert [round(p["value"]) for p in out["projection"]] == [150, 200]


def test_no_projection_without_two_points_or_bad_periods():
    assert _project([{"period": "2023", "value": 5.0}], 3)["projection"] == []
    assert _project([{"period": "FYx", "value": 1.0}, {"period": "FYy", "value": 2.0}], 3)["projection"] == []


def test_horizon_length_respected():
    pts = [{"period": "2020", "value": 100.0}, {"period": "2024", "value": 200.0}]
    assert len(_project(pts, 5)["projection"]) == 5
