"""Plot geometry — the geospatial primitives EUDR needs, done in Python (no PostGIS).

A sourcing plot is either a POINT (small plot, ≤ 4 ha) or a POLYGON boundary (EUDR requires the
full boundary above 4 ha). We store the geometry as GeoJSON and compute everything here with
shapely + pyproj so the platform stays portable — the target Postgres has no PostGIS extension.

Two facts this module is the single source of for:
  * area_ha — GEODESIC area on the WGS84 ellipsoid (not planar degrees², which is meaningless),
  * centroid (lat, lon) — the H3 key the rest of the platform joins on.

The EUDR rule (Art. 9): geolocation may be a single point ONLY for plots ≤ 4 ha; above that a
polygon is mandatory. `validate_plot_geometry` enforces exactly that, honestly: a >4 ha plot
that arrives as a point is flagged, not silently accepted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Union

from pyproj import Geod
from shapely.geometry import shape, mapping
from shapely.geometry.base import BaseGeometry

_GEOD = Geod(ellps="WGS84")
EUDR_POINT_MAX_HA = 4.0  # a point is EUDR-valid only at/below this; above needs a polygon


@dataclass
class PlotGeom:
    geom: BaseGeometry            # shapely geometry (Point / Polygon / MultiPolygon)
    geojson: dict                 # normalized GeoJSON geometry (what we persist)
    kind: str                     # 'point' | 'polygon'
    area_ha: Optional[float]      # geodesic hectares (None for a point)
    lat: float                    # centroid latitude
    lon: float                    # centroid longitude


def parse_geojson(value: Union[str, dict]) -> BaseGeometry:
    """Parse a GeoJSON geometry (or a Feature/FeatureCollection wrapping one) into shapely.

    Validates at the boundary: bad JSON, a non-geometry, or an invalid ring raises ValueError
    with a specific message the caller can surface — never a silent pass."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("empty geometry")
    obj = value
    if isinstance(value, str):
        try:
            obj = json.loads(value)
        except json.JSONDecodeError as e:
            raise ValueError(f"not valid JSON: {e}")
    if not isinstance(obj, dict):
        raise ValueError("geometry must be a JSON object")
    t = obj.get("type")
    # Unwrap a Feature / FeatureCollection down to the geometry.
    if t == "Feature":
        obj = obj.get("geometry") or {}
        t = obj.get("type")
    elif t == "FeatureCollection":
        feats = obj.get("features") or []
        if not feats:
            raise ValueError("empty FeatureCollection")
        obj = feats[0].get("geometry") or {}
        t = obj.get("type")
    if t not in ("Point", "Polygon", "MultiPolygon"):
        raise ValueError(f"unsupported geometry type '{t}' (need Point, Polygon or MultiPolygon)")
    try:
        geom = shape(obj)
    except Exception as e:
        raise ValueError(f"invalid geometry coordinates: {e}")
    if geom.is_empty:
        raise ValueError("geometry is empty")
    if not geom.is_valid and t != "Point":
        # A self-intersecting ring is a real EUDR data error — surface it.
        raise ValueError("polygon is not valid (self-intersecting or unclosed ring)")
    return geom


def geodesic_area_ha(geom: BaseGeometry) -> float:
    """Geodesic area in hectares on the WGS84 ellipsoid. 0.0 for a point/line."""
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        return 0.0
    area_m2, _ = _GEOD.geometry_area_perimeter(geom)
    return abs(area_m2) / 10_000.0


def centroid_latlon(geom: BaseGeometry) -> tuple[float, float]:
    """Centroid as (lat, lon). For a polygon this is the representative interior point when the
    plain centroid would fall outside a concave boundary."""
    c = geom.centroid
    if geom.geom_type in ("Polygon", "MultiPolygon") and not geom.contains(c):
        c = geom.representative_point()
    return round(c.y, 6), round(c.x, 6)


def build_plot_geom(value: Union[str, dict]) -> PlotGeom:
    """Parse + derive everything we persist for a plot geometry."""
    geom = parse_geojson(value)
    kind = "point" if geom.geom_type == "Point" else "polygon"
    area = None if kind == "point" else round(geodesic_area_ha(geom), 4)
    lat, lon = centroid_latlon(geom)
    return PlotGeom(geom=geom, geojson=mapping(geom), kind=kind, area_ha=area, lat=lat, lon=lon)


def validate_plot_geometry(value: Union[str, dict], declared_area_ha: Optional[float] = None) -> dict:
    """Boundary validator for an uploaded plot geometry.

    Returns a dict the upload/onboarding path can act on directly:
      { ok, kind, area_ha, lat, lon, geojson, eudr_point_ok, needs_polygon, error }
    `eudr_point_ok` is True when a point is EUDR-acceptable (plot ≤ 4 ha). `needs_polygon` is
    True when the geometry is a point but the plot is (or is declared) > 4 ha — the honest flag
    that a boundary is still required. Never raises; a parse failure comes back as ok=False."""
    try:
        pg = build_plot_geom(value)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    # Effective area: the polygon's own geodesic area, else the declared number (point case).
    area = pg.area_ha if pg.area_ha is not None else declared_area_ha
    over_threshold = area is not None and area > EUDR_POINT_MAX_HA
    needs_polygon = pg.kind == "point" and over_threshold
    return {
        "ok": True,
        "kind": pg.kind,
        "area_ha": pg.area_ha,
        "lat": pg.lat,
        "lon": pg.lon,
        "geojson": pg.geojson,
        # A point ≤4 ha is EUDR-valid geolocation; a point that should be a polygon is not.
        "eudr_point_ok": pg.kind == "point" and not over_threshold,
        "needs_polygon": needs_polygon,
        "error": None,
    }
