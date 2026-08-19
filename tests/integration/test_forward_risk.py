"""Forward-change decision signal — honesty invariants against the live golden source.

The forward-risk brief turns banded scenario projections into a portfolio decision (€-at-risk
trajectory, new crossings, movers, runway). Invariants:
  1. 'current' carries no band and no new crossing (today's reading, held);
  2. every forward point's at-risk band BRACKETS the central at-risk € (lo ≤ central ≤ hi);
  3. movers are genuine deteriorations (Δscore > 0);
  4. runway, if set, is a real horizon; percentages stay in [0,100].
Skips cleanly if the demo bank org isn't scored in this environment.
"""
import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.forward_risk import HORIZONS, forward_risk

BANK_ORG = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(scope="module")
def brief():
    with get_session() as s:
        n = s.execute(text("SELECT COUNT(*) FROM portfolio_entities WHERE org_id=:o AND vertical='banking'"),
                      {"o": BANK_ORG}).scalar()
        if not n:
            pytest.skip("demo bank not present")
        return forward_risk(s, BANK_ORG, "banking", "hot_house_3_5c")


def test_current_is_held_flat_no_band_no_crossing(brief):
    cur = next(t for t in brief["trajectory"] if t["horizon"] == "current")
    assert cur["at_risk_band_eur"][0] == cur["at_risk_band_eur"][1] == cur["at_risk_eur"]
    assert cur["newly_crossing_eur"] == 0.0 and cur["newly_crossing_count"] == 0


def test_forward_bands_bracket_central(brief):
    fwd = [t for t in brief["trajectory"] if t["horizon"] != "current"]
    assert fwd
    for t in fwd:
        lo, hi = t["at_risk_band_eur"]
        assert lo <= t["at_risk_eur"] <= hi, f"{t['horizon']}: band {lo}-{hi} excludes {t['at_risk_eur']}"
        assert 0 <= t["at_risk_pct"] <= 100


def test_movers_are_real_deteriorations(brief):
    for m in brief["movers"]:
        assert m["delta"] > 0 and m["future_score"] > m["current_score"]


def test_runway_is_a_real_horizon(brief):
    assert brief["runway"] is None or brief["runway"] in HORIZONS
