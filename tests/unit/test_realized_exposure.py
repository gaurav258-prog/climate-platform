"""Realized-exposure geospatial matching — the haversine distance that decides whether a real catalogued
event crossed a real asset must be correct. Pure — no DB."""
from services.intelligence.realized_exposure import _haversine_km


def test_haversine_zero_distance():
    assert _haversine_km(40.0, -3.0, 40.0, -3.0) == 0.0


def test_haversine_known_distance_madrid_to_barcelona():
    # Madrid (40.4168, -3.7038) → Barcelona (41.3874, 2.1686) ≈ 505 km
    d = _haversine_km(40.4168, -3.7038, 41.3874, 2.1686)
    assert 495 < d < 515


def test_haversine_one_degree_latitude_is_about_111km():
    d = _haversine_km(40.0, -3.0, 41.0, -3.0)
    assert 110 < d < 112


def test_haversine_is_symmetric():
    a = _haversine_km(35.6, -9.1, 43.2, 3.6)
    b = _haversine_km(43.2, 3.6, 35.6, -9.1)
    assert abs(a - b) < 1e-6


# ── the observed record in the catalogue's own terms (E244, E247, E248) ──────────────────────────────────────────────────────
from datetime import date  # noqa: E402

from services.intelligence.realized_exposure import (  # noqa: E402
    _span,
    storm_class,
    storm_name,
    storm_strength,
)
from services.intelligence.underwriting_review import frequency_check  # noqa: E402


def test_a_tropical_storm_is_never_read_as_a_depression():
    # IBTrACS USA_SSHS 0 is a tropical storm; `category or -1` made it -1 ("Depression")
    assert storm_class(0) == "Tropical storm"
    assert storm_strength(0, 40) > storm_strength(-4, 60)        # a tropical storm outranks a stronger post-tropical point
    assert storm_strength(3, 100) > storm_strength(0, 60) > storm_strength(-1, 30)
    assert storm_strength(-4, 50) > storm_strength(-2, 40)       # below a tropical storm, the wind decides


def test_every_best_track_class_has_its_own_words():
    from core import messages
    names = messages.names()["realized.storm_class"]
    assert set(names) == {str(c) for c in range(-5, 6)}           # the IBTrACS USA_SSHS codes, each its own words
    assert len(set(names.values())) == len(names)
    assert storm_class(-4) == "Post-tropical" and storm_class(None) == "Unclassified"


def test_a_best_track_name_reads_as_a_name():
    assert storm_name("LESLIE") == "Leslie"
    assert storm_name("ANNETTE:JAMINY") == "Annette / Jaminy"
    assert storm_name(None) == "Unnamed storm"


def test_a_catalogue_window_is_its_span_in_days_not_calendar_years():
    # July 2016 to July 2026 is ten years, not the eleven calendar years 2016..2026 counted
    assert _span(date(2016, 7, 5), date(2026, 7, 3))["years"] == 10.0


def test_each_priced_peril_is_checked_on_its_own_return_period():
    c = frequency_check("seismic", 500.0, observed=1, window_years=10.0, tolerance=0.5)
    assert c["priced_return_period_years"] == 500.0 and c["expected_events"] == 0.02 and c["ratio"] == 50.0
    assert c["verdict"] == "more_often" and c["verdict_name"] == "Crossed more often than priced"
    assert frequency_check("flood", 100.0, 3, 10.0, 0.5) is None          # no observed flood catalogue: no check
    assert frequency_check("storm", None, 3, 45.7, 0.5) is None           # no priced return period: no check


def test_seeing_none_says_nothing_when_the_price_expects_less_than_one():
    short = frequency_check("seismic", 500.0, observed=0, window_years=10.0, tolerance=0.5)
    assert short["verdict"] is None and short["no_verdict"]["code"] == "realized.review.window_short"
    long = frequency_check("storm", 10.0, observed=0, window_years=45.7, tolerance=0.5)     # 4.6 expected, none seen
    assert long["verdict"] == "less_often"
    within = frequency_check("storm", 10.0, observed=5, window_years=45.7, tolerance=0.5)
    assert within["verdict"] == "in_line"


def test_without_a_stated_tolerance_the_numbers_stand_without_a_reading():
    c = frequency_check("seismic", 200.0, observed=2, window_years=10.0, tolerance=None)
    assert c["verdict"] is None and c["ratio"] == 40.0 and c["no_verdict"]["code"] == "realized.review.no_tolerance"
