"""Tier-1 plausibility: the whole verdict rule is one pure function; no reference → no verdict, never a guess."""
from services.supervision.geo_prior import summarise
from services.supervision.plausibility import ABOVE, BELOW, NO_REF, PLAUSIBLE, judge


def test_verdicts_follow_the_regional_spread():
    prior = {"p25": 0.20, "p75": 0.60}
    assert judge(0.40, prior)[0] == PLAUSIBLE
    assert judge(0.75, prior)[0] == ABOVE and "above" in judge(0.75, prior)[1]
    assert judge(0.05, prior)[0] == BELOW
    assert judge(0.20, prior)[0] == PLAUSIBLE and judge(0.60, prior)[0] == PLAUSIBLE   # edges inclusive


def test_no_reference_when_the_platform_cannot_judge():
    assert judge(None, {"p25": 0.2, "p75": 0.6})[0] == NO_REF
    assert judge(0.5, None)[0] == NO_REF
    assert judge(0.5, {"p25": None, "p75": None})[0] == NO_REF


def test_prior_summary_uses_the_spread_across_regions_and_rolls_eu_up():
    rows = []
    for region, share in [("ES11", 0.1), ("ES12", 0.5), ("ES13", 0.9), ("ES21", 0.3)]:
        rows += [("ES", region, i < int(share * 10), "flood") for i in range(10)]
    rows += [("US", "8444a1bffffffff", True, "wildfire")] * 40
    rows += [(None, "x", True, "flood")] * 5           # cells at sea carry no country → ignored
    out = summarise(rows)
    assert set(out) == {"ES", "US", "EU"}
    assert out["ES"]["n_cells"] == 40 and out["ES"]["n_regions"] == 4 and 0.1 <= out["ES"]["p10"] < out["ES"]["p50"] < out["ES"]["p90"] <= 0.9
    assert out["ES"]["hazard_mix"] == {"flood": 18}
    assert out["EU"]["n_cells"] == 40 and out["US"]["p10"] is None       # one US region → no spread → no band
