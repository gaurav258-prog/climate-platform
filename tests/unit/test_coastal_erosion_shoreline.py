"""Coastal-erosion shoreline validator — pure logic (sign convention, per-cell aggregation, filters). No DB/network."""
import h3

from services.validation.validators.coastal_erosion_shoreline import (
    H3_RES,
    aggregate_transects,
    erosion_positive,
)


def _tr(lat, lon, rate, n=25, lin="WeakLin"):
    return {"lat": lat, "lon": lon, "rate": rate, "n_shorelines": n, "linearity": lin}


def test_erosion_is_positive_and_accretion_negative():
    assert erosion_positive(-2.5) == 2.5      # retreating shoreline → hazard up
    assert erosion_positive(1.0) == -1.0      # accreting → below zero
    assert erosion_positive(0.0) == 0.0


def test_transects_in_one_cell_average_and_count():
    lat, lon = 52.0, 4.2
    cell = h3.latlng_to_cell(lat, lon, H3_RES)
    out = aggregate_transects([_tr(lat, lon, -1.0), _tr(lat, lon, -3.0), _tr(lat, lon, 2.0)])
    assert set(out) == {cell}
    assert out[cell]["n"] == 3
    assert abs(out[cell]["obs"] - (1.0 + 3.0 - 2.0) / 3) < 1e-9


def test_strong_linear_subset_is_separate_and_none_when_absent():
    lat, lon = -33.9, 151.2
    cell = h3.latlng_to_cell(lat, lon, H3_RES)
    out = aggregate_transects([_tr(lat, lon, -4.0, lin="StrongLin"), _tr(lat, lon, 0.0, lin="NonLin")])
    assert out[cell]["obs_strong"] == 4.0 and abs(out[cell]["obs"] - 2.0) < 1e-9
    out2 = aggregate_transects([_tr(lat, lon, -4.0, lin="NonLin")])
    assert out2[cell]["obs_strong"] is None


def test_short_records_and_nan_rates_are_dropped_never_filled():
    lat, lon = 10.0, 10.0
    assert aggregate_transects([_tr(lat, lon, -1.0, n=5)]) == {}
    assert aggregate_transects([_tr(lat, lon, float("nan"))]) == {}
    assert aggregate_transects([_tr(lat, lon, None)]) == {}


def test_distant_transects_land_in_distinct_cells():
    out = aggregate_transects([_tr(52.0, 4.2, -1.0), _tr(36.5, -6.3, -1.0)])
    assert len(out) == 2
