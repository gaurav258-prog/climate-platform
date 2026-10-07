"""E169: a damage-curve family is accepted only when it is complete, cited and well formed."""
import copy

import pytest

from services.loss import curves

GOOD = {
    "family": "test_family", "peril": "flood", "metric": "water_depth", "unit": "m", "damage_basis": "building",
    "source": {"authors": "A. Author", "year": 2017, "title": "A title", "publisher": "A publisher",
               "url": "https://example.org", "file": "data/reference/vulnerability/sources/x.pdf", "sha256": "ab" * 32},
    "licence": "CC BY 4.0", "beyond_last": "hold",
    "curves": [{"key": "test_family:residential:europe", "occupancy": "residential", "region": "europe", "countries": ["ES"],
                "points": [[0, 0], [0.5, 0.25], [1, 0.4], [6, 1.0]], "quote": {"table": "Table 3", "page": 12}}]}


def _with(**changes):
    d = copy.deepcopy(GOOD)
    for k, v in changes.items():
        d[k] = v
    return d


def test_a_complete_family_is_sound():
    assert curves.check_family(GOOD) == []


def test_a_curve_without_its_quoted_table_is_refused():
    d = copy.deepcopy(GOOD)
    d["curves"][0]["quote"] = {"table": "Table 3"}
    assert any("not quoted" in p for p in curves.check_family(d))


def test_a_falling_or_out_of_range_curve_is_refused():
    d = copy.deepcopy(GOOD)
    d["curves"][0]["points"] = [[0, 0], [1, 0.5], [2, 0.4]]
    assert any("never fall" in p for p in curves.check_family(d))
    d["curves"][0]["points"] = [[0, 0], [1, 1.2]]
    assert any("[0, 1]" in p for p in curves.check_family(d))


def test_a_family_must_measure_what_a_layer_measures():
    assert any("no intensity layer" in p for p in curves.check_family(_with(metric="water_velocity")))
    assert any("no intensity layer" in p for p in curves.check_family(_with(unit="ft")))


def test_an_uncited_or_extrapolating_family_is_refused():
    d = copy.deepcopy(GOOD)
    del d["source"]["sha256"]
    assert any("sha256" in p for p in curves.check_family(d))
    assert any("holds" in p for p in curves.check_family(_with(beyond_last="extrapolate")))


def test_the_ratio_is_read_off_the_published_points():
    pts = GOOD["curves"][0]["points"]
    assert curves.ratio(pts, -1) == 0.0 and curves.ratio(pts, 0) == 0.0
    assert curves.ratio(pts, 0.25) == 0.125
    assert abs(curves.ratio(pts, 3.5) - (0.4 + 0.6 * 2.5 / 5)) < 1e-12
    assert curves.ratio(pts, 9) == 1.0


def test_a_measured_family_records_its_derivation_test_and_bands():
    d = copy.deepcopy(GOOD)
    d["kind"] = "measured"
    del d["curves"][0]["quote"]
    assert any("protocol" in p for p in curves.check_family(d))
    d["derivation"] = {"protocol": "loss-protocol-v1", "claims_used": 10}
    d["test"] = {"passed": False, "events_tested": 3}
    assert any("bands" in p for p in curves.check_family(d))
    d["curves"][0]["bands"] = [{"n": 5, "p10": 0.01, "p90": 0.5}]
    assert curves.check_family(d) == []
    d["curves"][0]["countries"] = []
    assert any("countries" in p for p in curves.check_family(d))


def test_a_published_range_is_one_standard_deviation_or_none():
    """Product owner's decision (2026-10-07): the publisher's standard deviation where given (central ± σ, bounded to
    [0, 1]); a curve with no published spread has no range of its own."""
    from services.loss.engine import _band_at
    with_sd = {"points": [[0, 0.0], [1, 0.5], [2, 1.0]], "sd": [[0, 0.0], [1, 0.2], [2, 0.0]]}
    assert _band_at(with_sd, 1.0, 0.5) == pytest.approx((0.3, 0.7))
    assert _band_at(with_sd, 0.5, 0.25) == pytest.approx((0.15, 0.35))         # σ read linearly between points
    assert _band_at({"points": [[0, 0], [1, 0.95]], "sd": [[0, 0], [1, 0.2]]}, 1.0, 0.95)[1] == 1.0   # bounded
    assert _band_at({"points": [[0, 0], [1, 1]], "spread": "none published"}, 0.5, 0.5) == (0.5, 0.5)
    with pytest.raises(ValueError):
        _band_at({"points": [[0, 0], [1, 1]]}, 0.5, 0.5)


def test_a_curve_tested_on_its_own_carries_that_standing():
    from services.loss.engine import standing
    fam = {"curves": []}
    assert standing(fam, "US", {"test": {"passed": False}}) == "held"
    assert standing(fam, "US", {"test": {"passed": True}}) == "published"
    assert standing(fam, "DE", {}) == "untested"


def test_a_family_that_requires_a_spread_refuses_a_curve_silent_about_it():
    import copy
    fam = curves.families().get("jrc_huizinga_2017")
    if fam is None:
        pytest.skip("the JRC family is not built on this machine")
    bad = copy.deepcopy(fam)
    bad["curves"][0].pop("sd", None)
    bad["curves"][0].pop("spread", None)
    assert any("published spread" in p for p in curves.check_family(bad))
    bad = copy.deepcopy(fam)
    c = next(c for c in bad["curves"] if c.get("sd"))
    c["sd"] = c["sd"][:-1]
    assert any("standard deviation" in p for p in curves.check_family(bad))
