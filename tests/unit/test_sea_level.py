"""Sea-level-rise coastal-flood model — freeboard screening + honest band, zero inland."""
from ml.scoring.sea_level import COAST_KM, SlrProjection, coastal_flood_score, slr_projection


def test_inland_asset_has_zero_coastal_risk():
    # far from the coast → a definitive 0 (not None, not a fabricated uplift)
    sc, lo, hi = coastal_flood_score(5.0, COAST_KM + 50, slr_projection("hot_house_3_5c", "2100"))
    assert sc == 0.0 and lo is None and hi is None


def test_low_coastal_asset_is_high_risk_and_rises_with_slr():
    slr30 = coastal_flood_score(1.0, 2.0, slr_projection("hot_house_3_5c", "2030"))[0]
    slr100 = coastal_flood_score(1.0, 2.0, slr_projection("hot_house_3_5c", "2100"))[0]
    assert slr100 > slr30 > 50            # a 1 m-elevation coastal asset is exposed, and worsens by 2100


def test_high_coastal_asset_is_low_risk():
    sc, _, _ = coastal_flood_score(30.0, 1.0, slr_projection("hot_house_3_5c", "2100"))
    assert sc < 5                          # 30 m up, on the coast → negligible SLR exposure


def test_band_brackets_and_widens_with_uncertainty():
    sc, lo, hi = coastal_flood_score(2.0, 3.0, slr_projection("disorderly_2c", "2100"))
    assert lo is not None and lo <= sc <= hi

def test_no_data_or_no_slr_returns_none():
    assert coastal_flood_score(None, 2.0, slr_projection("hot_house_3_5c", "2100")) == (None, None, None)
    assert coastal_flood_score(1.0, 2.0, None) == (None, None, None)      # baseline/current: no SLR
    assert slr_projection("baseline", "2100") is None


def test_stress_tail_is_separate_and_higher_than_likely_range():
    p = slr_projection("hot_house_3_5c", "2100")
    assert isinstance(p, SlrProjection)
    assert p.stress_m > p.hi_m > p.median_m > p.lo_m   # collapse tail sits ABOVE the likely range


# ── v2: regional dynamic offset + land subsidence ────────────────────────────────────────────────
from ml.scoring.sea_level import SEA_LEVEL_VERSION, coastal_flood_stress


def test_regional_offset_raises_and_lowers_score():
    base = coastal_flood_score(2.0, 3.0, slr_projection("disorderly_2c", "2100"))[0]
    higher = coastal_flood_score(2.0, 3.0, slr_projection("disorderly_2c", "2100"), regional_offset_m=0.2)[0]
    lower = coastal_flood_score(2.0, 3.0, slr_projection("disorderly_2c", "2100"), regional_offset_m=-0.2)[0]
    assert higher > base > lower   # local sea level above global mean is worse; below is better


def test_subsidence_raises_score_like_added_sea_level():
    base = coastal_flood_score(2.0, 3.0, slr_projection("disorderly_2c", "2100"))[0]
    sub = coastal_flood_score(2.0, 3.0, slr_projection("disorderly_2c", "2100"), subsidence_m=0.3)[0]
    assert sub > base
    # subsidence and equal added sea level are interchangeable in the freeboard
    a = coastal_flood_score(2.0, 3.0, slr_projection("disorderly_2c", "2100"), subsidence_m=0.25)[0]
    b = coastal_flood_score(2.0, 3.0, slr_projection("disorderly_2c", "2100"), regional_offset_m=0.25)[0]
    assert abs(a - b) < 1e-6


def test_v2_defaults_reproduce_v1():
    # no regional/subsidence data → identical to the global-mean result
    with_defaults = coastal_flood_score(2.0, 3.0, slr_projection("hot_house_3_5c", "2100"))
    explicit_zero = coastal_flood_score(2.0, 3.0, slr_projection("hot_house_3_5c", "2100"), 0.0, 0.0)
    assert with_defaults == explicit_zero


def test_corrections_do_not_apply_inland_or_unknown():
    assert coastal_flood_score(2.0, COAST_KM + 10, slr_projection("hot_house_3_5c", "2100"), 0.3, 0.3)[0] == 0.0
    assert coastal_flood_stress(None, 3.0, slr_projection("hot_house_3_5c", "2100"), 0.3, 0.3) is None


def test_version_is_v2():
    assert SEA_LEVEL_VERSION == "sea-level-ar6-v2"
