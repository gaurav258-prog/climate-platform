"""Plot geometry — the EUDR geospatial primitives (services/intelligence/geometry.py).

Pins the invariants a regulated reviewer cares about: geodesic area (not planar degrees), the
point-vs-polygon EUDR rule at 4 ha, and honest rejection of bad geometry.
"""
import json

import pytest

from services.intelligence.geometry import (
    build_plot_geom, geodesic_area_ha, validate_plot_geometry, EUDR_POINT_MAX_HA,
)

# A ~1.9 ha square near Ashanti (small enough that a point would also be EUDR-valid).
SMALL_SQ = {"type": "Polygon", "coordinates": [[[-1.6060, 6.6940], [-1.6047, 6.6940],
            [-1.6047, 6.6952], [-1.6060, 6.6952], [-1.6060, 6.6940]]]}
POINT = {"type": "Point", "coordinates": [-1.6055, 6.6944]}


def test_geodesic_area_is_hectares_not_degrees():
    pg = build_plot_geom(SMALL_SQ)
    assert pg.kind == "polygon"
    # ~1.9 ha, decidedly not the ~0.0000016 a planar degree² area would give.
    assert 1.5 < pg.area_ha < 2.5
    assert geodesic_area_ha(pg.geom) == pytest.approx(pg.area_ha, abs=1e-3)


def test_centroid_from_polygon_is_inside_and_6dp():
    pg = build_plot_geom(SMALL_SQ)
    assert 6.69 < pg.lat < 6.70 and -1.607 < pg.lon < -1.604
    assert pg.geom.contains(pg.geom.centroid)


def test_polygon_of_any_size_is_eudr_valid_geolocation():
    v = validate_plot_geometry(SMALL_SQ)
    assert v["ok"] and v["kind"] == "polygon" and not v["needs_polygon"]


def test_point_over_4ha_needs_a_polygon():
    v = validate_plot_geometry(POINT, declared_area_ha=9.0)
    assert v["ok"] and v["kind"] == "point"
    assert v["needs_polygon"] is True and v["eudr_point_ok"] is False


def test_point_at_or_below_4ha_is_eudr_ok():
    v = validate_plot_geometry(POINT, declared_area_ha=EUDR_POINT_MAX_HA)
    assert v["eudr_point_ok"] is True and v["needs_polygon"] is False


def test_bad_json_is_rejected_not_swallowed():
    v = validate_plot_geometry("{not json")
    assert v["ok"] is False and "JSON" in v["error"]


def test_self_intersecting_polygon_is_rejected():
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    v = validate_plot_geometry(json.dumps(bowtie))
    assert v["ok"] is False and "valid" in v["error"].lower()


def test_feature_wrapper_is_unwrapped():
    feat = {"type": "Feature", "properties": {}, "geometry": SMALL_SQ}
    v = validate_plot_geometry(feat)
    assert v["ok"] and v["kind"] == "polygon"
