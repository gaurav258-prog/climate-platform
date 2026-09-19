"""Regional validation helpers: region assignment and the pooled-hides-failure check."""
import numpy as np
import pytest

from ml.validation import regional as R


@pytest.mark.parametrize("lat,lon,expected", [
    (48.85, 2.35, "europe"),                    # Paris
    (25.76, -80.19, "north_america"),           # Miami
    (17.97, -76.79, "latin_america_caribbean"), # Kingston
    (-1.29, 36.82, "africa"),                   # Nairobi
    (28.61, 77.21, "asia"),                     # Delhi
    (-33.87, 151.21, "oceania"),                # Sydney
    (55.75, 37.62, "europe"),                   # Moscow (Russia west of 60E)
    (55.03, 82.92, "asia"),                     # Novosibirsk (Russia east of 60E)
    (36.90, -76.00, "north_america"),           # just offshore Virginia: nearest country within 1 degree
    (30.0, -40.0, None),                        # open Atlantic: never guessed
    (-82.0, 0.0, None),                         # Antarctica: unassigned
])
def test_macro_region_from_point(lat, lon, expected):
    assert R.macro_region(lat, lon) == expected


def test_iso2_mapping_handles_gisco_codes_and_russia():
    assert R.macro_region_from_iso2("EL") == "europe" and R.macro_region_from_iso2("UK") == "europe"
    assert R.macro_region_from_iso2("TR") == "asia" and R.macro_region_from_iso2("XX") is None
    assert R.macro_region_from_iso2("RU", 30) == "europe" and R.macro_region_from_iso2("RU", 100) == "asia"
    assert R.macro_region_from_iso2("RU") is None      # ambiguous without a longitude: not guessed


def test_pooled_pass_that_hides_a_failing_region_is_flagged():
    rng = np.random.default_rng(1)
    pe = rng.uniform(50, 100, 60)                       # 'Europe': score tracks the observation
    oe = pe + rng.normal(0, 3, 60)
    pt = rng.uniform(0, 50, 40)                         # 'Tropics': lower level, but score runs AGAINST the observation
    ot = (50 - pt) * 0.4 + rng.normal(0, 1, 40)
    pred = np.concatenate([pe, pt]); obs = np.concatenate([oe, ot])
    rep = R.stratified_report(pred, obs, ["europe"] * 60 + ["asia"] * 40)
    assert rep["pooled"]["spearman"] >= 0.35            # the pooled number looks healthy...
    assert rep["by_stratum"]["europe"]["status"] == "validated"
    assert rep["by_stratum"]["asia"]["status"] == "fails"
    assert rep["hides_failure"] is True                 # ...and is flagged as concealing the failure


def test_small_strata_are_insufficient_not_pass_or_fail():
    x = np.arange(30, dtype=float)
    rep = R.stratified_report(x, x, ["a"] * 25 + ["b"] * 5)
    assert rep["by_stratum"]["a"]["status"] == "validated"
    assert rep["by_stratum"]["b"]["status"] == "insufficient"     # n=5 < 20: no regional claim either way
    assert rep["hides_failure"] is False


def test_unlocated_samples_are_kept_visible():
    x = np.arange(40, dtype=float)
    rep = R.stratified_report(x, x, [None] * 40)
    assert "unassigned" in rep["by_stratum"]


def test_loro_folds_partition_the_data():
    strata = ["a", "a", "b", "b", "b", "c"]
    seen = {name: (tr, te) for name, tr, te in R.loro_folds(strata)}
    assert set(seen) == {"a", "b", "c"}
    for name, (tr, te) in seen.items():
        assert set(tr).isdisjoint(te) and len(tr) + len(te) == 6
