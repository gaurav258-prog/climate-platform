"""On-demand terrain slope at an arbitrary point — the shared input for the slope-driven hazards
(avalanche, solifluction), computed the same fetch-free-at-scale way the coastal channel gets elevation.

Slope is derived from a 5-point elevation stencil (centre + N/S/E/W neighbours ~300 m out) queried in ONE
batched Copernicus GLO-90 DEM call (Open-Meteo elevation API, no key), then a central-difference gradient.
Result is cached per H3 cell in `terrain_cell`, so a location's slope is fetched once and reused across every
slope-driven hazard. Returns None where the DEM has no coverage (never a fabricated slope).
"""
from __future__ import annotations

import json
import math
import urllib.request
from typing import Optional

import h3
from sqlalchemy import text

from core.db.session import get_session

_DELTA_DEG = 0.0027            # ~300 m stencil half-step
_EARTH_M_PER_DEG = 111320.0


def _fetch_stencil(lat: float, lon: float) -> Optional[tuple[float, float, float, float, float]]:
    """(centre, north, south, east, west) elevations in metres, in one batched DEM call, or None."""
    d = _DELTA_DEG
    lats = [lat, lat + d, lat - d, lat, lat]
    lons = [lon, lon, lon, lon + d, lon - d]
    la = ",".join(f"{v:.5f}" for v in lats)
    lo = ",".join(f"{v:.5f}" for v in lons)
    url = f"https://api.open-meteo.com/v1/elevation?latitude={la}&longitude={lo}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            els = json.load(r).get("elevation")
        if not els or len(els) < 5 or any(e is None for e in els[:5]):
            return None
        return tuple(float(e) for e in els[:5])  # type: ignore[return-value]
    except Exception:
        return None


def _slope_from_stencil(lat: float, st: tuple[float, float, float, float, float]) -> float:
    """Central-difference slope (degrees) from the (centre, N, S, E, W) elevation stencil."""
    _c, n, s, e, w = st
    dy = 2.0 * _DELTA_DEG * _EARTH_M_PER_DEG
    dx = 2.0 * _DELTA_DEG * _EARTH_M_PER_DEG * max(0.05, math.cos(math.radians(lat)))
    dz_dy = (n - s) / dy
    dz_dx = (e - w) / dx
    return math.degrees(math.atan(math.hypot(dz_dx, dz_dy)))


def slope_degrees(lat: float, lon: float) -> Optional[tuple[float, float]]:
    """(slope_degrees, elevation_m) at (lat, lon), cached per H3 cell. None if the DEM has no coverage."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        row = s.execute(text("SELECT slope_deg, elevation_m FROM terrain_cell WHERE h3_cell=:c"),
                        {"c": cell}).mappings().first()
    if row is not None:
        return float(row["slope_deg"]), float(row["elevation_m"])
    st = _fetch_stencil(lat, lon)
    if st is None:
        return None
    slope = _slope_from_stencil(lat, st)
    elev = st[0]
    with get_session() as s:
        s.execute(text("""
            INSERT INTO terrain_cell (h3_cell, slope_deg, elevation_m)
            VALUES (:c, :sl, :el) ON CONFLICT (h3_cell) DO UPDATE SET slope_deg=:sl, elevation_m=:el
        """), {"c": cell, "sl": slope, "el": elev})
        s.commit()
    return slope, elev
