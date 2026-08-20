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
