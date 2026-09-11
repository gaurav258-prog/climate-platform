"""Subsidence v2 — observed EGMS rate: anchored scale, tile lookup, holdout split."""
from ml.scoring.subsidence_egms import rate_to_score
from services.validation.validators.subsidence_egms_holdout import MIN_EPOCHS, SPLIT


def test_rate_scale_is_the_disclosed_anchors():
    assert rate_to_score(0.0) == 0.0 and rate_to_score(-3.0) == 0.0          # uplift is not subsidence
    assert rate_to_score(2.0) == 25.0 and rate_to_score(5.0) == 50.0 and rate_to_score(10.0) == 75.0
    assert rate_to_score(20.0) == 100.0 and rate_to_score(35.0) == 100.0
    assert rate_to_score(1.0) == 12.5                                          # linear between anchors


def test_holdout_split_leaves_two_years_each_side():
    assert SPLIT == "20211231" and MIN_EPOCHS >= 40                            # ≥ 40 six-day epochs ≈ 8 months per side
