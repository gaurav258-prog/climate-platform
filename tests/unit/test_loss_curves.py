"""E169: a damage-curve family is accepted only when it is complete, cited and well formed."""
import copy

from services.loss import curves

GOOD = {
    "family": "test_family", "peril": "flood", "metric": "water_depth", "unit": "m", "damage_basis": "building",
    "source": {"authors": "A. Author", "year": 2017, "title": "A title", "publisher": "A publisher",
               "url": "https://example.org", "file": "data/reference/vulnerability/sources/x.pdf", "sha256": "ab" * 32},
    "licence": "CC BY 4.0", "beyond_last": "hold",
    "curves": [{"key": "test_family:residential:europe", "occupancy": "residential", "region": "europe",
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
