"""The 'ranged' tier in the engine: a fitted-but-partial driver publishes a BAND, not a point.

Pure-function tests on compute(). A ranged origin carries a 'fit' (slope/intercept/rmse/…) in
its calibration; the engine emits volume_at_risk as low/mid/high with the r² stated, floors the
loss at 0 (a good year is not "volume at risk"), and the publish gate lets it through — unlike
'indicative', which stays held.
"""
from __future__ import annotations

from services.intelligence.supply_cogs import compute

# a fit like Spain olive drought: loss rises with the score, wide residual band.
# fit_r2 surfaced to the buyer is the OUT-OF-SAMPLE r² (r2_oos) — the honest, cross-validated number
# the publish gate keys on (audit F2 / #94), NOT the optimistic in-sample r2. r2 here is deliberately
# higher than r2_oos so the assertions prove the engine states the honest number.
_FIT = {"hazard_driver": "drought", "slope": -0.667, "intercept": 37.6, "rmse": 17.6,
        "r2": 0.60, "r2_oos": 0.51, "score_mean": 53.0, "score_sxx": 12000.0, "n_years": 31}


def _ranged_cal(score_driver="drought"):
    return {"Olive oil": {"ES": {"sensitivity": None, "world_share": 0.45,
                                 "calibration_tier": "ranged", "hazard_driver": score_driver,
                                 "fit": _FIT}}}


def _commodity(hazard_score):
    return {"name": "Olive oil", "eudr_covered": True, "elasticity": -0.20,
            "spend": 10_000_000,
            "plots": [{"spend": 10_000_000, "origin": "ES", "hazards": {"drought": hazard_score}}]}


def test_ranged_publishes_a_band_not_held():
    """A high-drought score → a real, published range with r² stated."""
    r = compute([_commodity(85.0)], 100_000_000, calibrations=_ranged_cal()).commodities[0]
    assert r.status == "scored"
    assert r.calibration == "ranged"
    assert r.fit_r2 == 0.51
    assert r.volume_at_risk_low_eur is not None and r.volume_at_risk_high_eur is not None
    # the band brackets the mid, and the mid is a real loss at score 85
    assert r.volume_at_risk_low_eur <= r.volume_at_risk_eur <= r.volume_at_risk_high_eur
    assert r.volume_at_risk_eur > 0


def test_good_year_floors_to_zero_not_negative():
    """A favourable (low-drought) year predicts a yield GAIN; that is not 'volume at risk'.
    The mid floors at €0 and the band never goes negative."""
    r = compute([_commodity(35.0)], 100_000_000, calibrations=_ranged_cal()).commodities[0]
    assert r.status == "scored" and r.calibration == "ranged"
    assert r.volume_at_risk_eur == 0.0            # a gain, floored
    assert r.volume_at_risk_low_eur == 0.0        # optimistic end can't be negative risk
    assert r.volume_at_risk_high_eur >= 0.0       # pessimistic end may still carry loss


def test_band_widens_with_a_more_severe_score():
    """The worst-case euro must grow as drought worsens."""
    mild = compute([_commodity(55.0)], 100_000_000, calibrations=_ranged_cal()).commodities[0]
    severe = compute([_commodity(90.0)], 100_000_000, calibrations=_ranged_cal()).commodities[0]
    assert severe.volume_at_risk_high_eur > mild.volume_at_risk_high_eur
    assert severe.volume_at_risk_eur >= mild.volume_at_risk_eur


def test_backtested_point_crop_has_no_band():
    """A backtested (point) crop must not sprout a band — those fields stay None."""
    cal = {"Cocoa": {"CI": {"sensitivity": 0.1995, "world_share": 0.45,
                            "calibration_tier": "backtested", "hazard_driver": "heat_acute"}}}
    c = {"name": "Cocoa", "eudr_covered": True, "elasticity": -0.20, "spend": 5_000_000,
         "plots": [{"spend": 5_000_000, "origin": "CI", "hazards": {"heat_acute": 74.2}}]}
    r = compute([c], 100_000_000, calibrations=cal).commodities[0]
    assert r.status == "scored" and r.calibration == "backtested"
    assert r.volume_at_risk_low_eur is None and r.volume_at_risk_high_eur is None
    assert r.fit_r2 is None


def test_below_floor_fit_is_held_but_surfaces_its_r2_and_reason():
    """A crop we tested but whose driver fell below the publish floor must be HELD (no € band),
    yet still surface fit_r2 and an honest 'tested, explains X%, below the bar' reason — the
    engine keeps r² precisely so the reason can be specific."""
    weak = dict(_FIT, r2=0.55, r2_oos=0.36)   # out-of-sample below the 0.40 floor (in-sample looks fine)
    cal = {"Durum wheat": {"ES": {"sensitivity": None, "world_share": None,
                                  "calibration_tier": "indicative",   # view returns this when r²<floor
                                  "hazard_driver": "drought", "fit": weak}}}
    c = {"name": "Durum wheat", "eudr_covered": False, "elasticity": -0.25, "spend": 10_000_000,
         "plots": [{"spend": 10_000_000, "origin": "ES", "hazards": {"drought": 85.0}}]}
    r = compute([c], 100_000_000, calibrations=cal).commodities[0]
    assert r.status == "held"
    assert r.volume_at_risk_eur is None                       # no € published
    assert r.volume_at_risk_low_eur is None and r.volume_at_risk_high_eur is None  # no band
    assert r.fit_r2 == 0.36                                    # but the r² survives
    assert "tested" in r.held_reason and "36%" in r.held_reason and "below" in r.held_reason


def test_ranged_euro_is_in_the_headline_total():
    """A ranged commodity's mid € counts toward the portfolio headline (it is published),
    unlike a held one."""
    r = compute([_commodity(85.0)], 100_000_000, calibrations=_ranged_cal())
    assert r.commodities[0].status == "scored"
    assert r.volume_at_risk_eur == r.commodities[0].volume_at_risk_eur   # single commodity
    assert r.volume_at_risk_eur > 0
