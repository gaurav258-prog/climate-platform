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
        rows += [("ES", region, 80.0 if i < int(share * 10) else 20.0, "flood") for i in range(10)]
    rows += [("US", "8444a1bffffffff", 80.0, "wildfire")] * 40
    rows += [(None, "x", 80.0, "flood")] * 5           # cells at sea carry no country → ignored
    out = summarise(rows, 50.0)
    assert set(out) == {"ES", "US", "EU"}
    assert out["ES"]["n_cells"] == 40 and out["ES"]["n_regions"] == 4 and 0.1 <= out["ES"]["p10"] < out["ES"]["p50"] < out["ES"]["p90"] <= 0.9
    assert out["ES"]["hazard_mix"] == {"flood": 18}
    assert out["EU"]["n_cells"] == 40 and out["US"]["p10"] is None       # one US region → no spread → no band
    assert out["ES"]["at_risk_level"] == 50.0 and summarise(rows, 90.0)["ES"]["share_sensitive"] == 0.0   # read at any level


def test_the_stored_hundredths_give_an_exact_share_at_the_boundary():
    from services.supervision.geo_prior import HUNDREDTHS, MIN_CELLS_PER_GEOGRAPHY, prior_at
    stored = [1000, 4999, 5000, 5001, 9000] * (MIN_CELLS_PER_GEOGRAPHY // 5)    # 10.00, 49.99, 50.00, 50.01, 90.00
    items = [("R1", v / HUNDREDTHS, "flood", 1.0) for v in stored]            # as prior_for reads them back
    assert prior_at(items, 50.0)["share_sensitive"] == 3 / 5                   # 50.00 is at the level
    assert prior_at(items, 50.01)["share_sensitive"] == 2 / 5
    assert prior_at(items, 49.99)["share_sensitive"] == 4 / 5


def test_a_stated_level_is_checked_where_it_enters():
    import pytest

    from services.supervision.levels import clean_basis
    assert clean_basis({"scenario": "disorderly_2c", "at_risk_level": "60"}) == {"scenario": "disorderly_2c", "at_risk_level": 60.0}
    assert clean_basis({"at_risk_level": ""}) == {}
    for bad in ("high", "-1", "101"):
        with pytest.raises(ValueError, match="at_risk_level"):
            clean_basis({"at_risk_level": bad})
