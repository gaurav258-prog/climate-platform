from services.validation.validators import storm_holdout_regions as S


def test_cap_per_region_is_seeded_and_bounded():
    pts = [(float(i), 0.0, "a") for i in range(50)] + [(float(i), 1.0, "b") for i in range(5)]
    out = S._cap_per_region(pts, 10, 1)
    assert sum(p[-1] == "a" for p in out) == 10 and sum(p[-1] == "b" for p in out) == 5
    assert out == S._cap_per_region(pts, 10, 1)


def test_registered():
    from services.validation.engine import REGISTRY
    assert "storm_oos_allbasin" in REGISTRY
