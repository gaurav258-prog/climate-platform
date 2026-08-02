"""WS4c — CMIP6-driven financial projections carry an honest model-disagreement band.

flood/storm/wildfire forward projections are now driven by each cell's local CMIP6 warming/precip
(the global delta field) through documented sensitivities (ml/scoring/physical_projection.py), and
carry a real across-model band in score_ci_lower/upper — surfaced on v_portfolio_entity_physical_risk.
Invariants:
  1. the flat-held combos carry NO fabricated projection band — baseline scenario at a FORWARD
     horizon, and any SSP scenario at the CURRENT horizon (both = today's hazard held constant).
     (The true base, baseline/current, may carry a pre-existing ML-ensemble band on wildfire — that
     is a current-reading uncertainty, not a projection, so it is excluded from this check.)
  2. a forward SSP scenario carries a band that brackets the central projected score;
  3. a real disagreement band exists somewhere.
Skips cleanly if the financial projections haven't been run in this environment.
"""
import pytest
from sqlalchemy import text

from core.db.session import get_session


def _rows():
    with get_session() as s:
        return s.execute(text("""
            SELECT scenario, time_horizon, hazard_type,
                   ROUND(physical_risk_score::numeric, 2) AS score,
                   ROUND(physical_risk_ci_lower::numeric, 2) AS lo,
                   ROUND(physical_risk_ci_upper::numeric, 2) AS hi
            FROM v_portfolio_entity_physical_risk
            WHERE hazard_type IN ('flood','storm','wildfire')
        """)).mappings().all()


@pytest.fixture(scope="module")
def rows():
    r = _rows()
    if not r:
        pytest.skip("no financial flood/storm/wildfire projections in this environment")
    return r


def test_flat_held_combos_have_no_projection_band(rows):
    for r in rows:
        base_current = r["scenario"] == "baseline" and r["time_horizon"] == "current"
        flat_held = ((r["scenario"] == "baseline" and r["time_horizon"] != "current")
                     or (r["scenario"] != "baseline" and r["time_horizon"] == "current"))
        if flat_held and not base_current:
            assert r["lo"] is None and r["hi"] is None, f"{r['scenario']}/{r['time_horizon']} should have no projection band"


def test_forward_bands_bracket_the_score(rows):
    fwd = [r for r in rows if r["scenario"] != "baseline" and r["time_horizon"] != "current" and r["lo"] is not None]
    assert fwd, "expected at least one forward band"
    for r in fwd:
        assert r["lo"] <= r["score"] <= r["hi"], f"{r['hazard_type']} {r['scenario']}/{r['time_horizon']} band excludes score"


def test_a_real_disagreement_band_exists(rows):
    widths = [r["hi"] - r["lo"] for r in rows if r["lo"] is not None]
    assert widths and max(widths) > 0.5, "expected a non-trivial CMIP6 band somewhere"
