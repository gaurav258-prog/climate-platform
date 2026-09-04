"""Preprocess the GIGLak global glacial-lake inventory into the glacial_lake_cell H3 exposure layer.

Source (open) — Global Inventory of Glacial Lakes (GIGLak), figshare doi:10.6084/m9.figshare.26310967;
117k glacial lakes worldwide with area / elevation / location. Glacial-lake outburst floods (GLOFs) threaten
the valleys BELOW a lake; without a flow-routing model we stamp an honest PROXIMITY exposure zone — H3 cells
within a size-scaled buffer of each lake (bigger lake → longer potential runout) — and keep, per cell, the
LARGEST influencing lake's area/elevation and the distance to it. Disclosed as a proximity screen, not a
flow-routed inundation model. Read at runtime by ml/scoring/glacial_lake_point.py.

Run (after the GIGLak .rar is extracted under data/glacial_lakes/):
  .venv/bin/python -m scripts.ingest_glacial_lakes
"""
from __future__ import annotations

import glob
import math
import os

import h3
import pyogrio
from sqlalchemy import text

from core.db.session import get_session

H3_RES = 6                 # ~3.2 km edge — mountains are broad; keeps the buffer cell-count sane
_EDGE_KM = 3.22
VINTAGE = "GIGLak (Global Inventory of Glacial Lakes), figshare 26310967"


def _radius_km(area_km2: float) -> float:
    """Size-scaled GLOF runout proxy: small tarns a few km, large moraine lakes up to ~25 km."""
    return max(4.0, min(25.0, 4.0 + 6.0 * math.sqrt(max(0.0, area_km2))))


def _find_shp() -> str | None:
    hits = glob.glob("data/glacial_lakes/**/Global_Lake_Dataset.shp", recursive=True)
    return hits[0] if hits else None


def main() -> int:
    shp = _find_shp()
    if not shp:
        print("Global_Lake_Dataset.shp not found under data/glacial_lakes/ — extract the GIGLak .rar first.")
        return 2
    df = pyogrio.read_dataframe(shp, columns=["Area_km2", "Elevation", "Latitude", "Longitude"], read_geometry=False)
    print(f"read {len(df):,} glacial lakes", flush=True)

    best: dict[str, tuple[float, float, float]] = {}   # cell -> (lake_area_km2, lake_elev_m, dist_km)
    for area, elev, lat, lon in zip(df["Area_km2"], df["Elevation"], df["Latitude"], df["Longitude"]):
        if lat is None or lon is None or lat != lat or lon != lon:
            continue
        centre = h3.latlng_to_cell(float(lat), float(lon), H3_RES)
        k = max(0, round(_radius_km(float(area or 0.0)) / _EDGE_KM))
        for cell in h3.grid_disk(centre, k):
            dist = h3.grid_distance(centre, cell) * _EDGE_KM
            cur = best.get(cell)
            if cur is None or float(area) > cur[0]:   # the largest lake influencing this cell wins
                best[cell] = (float(area or 0.0), float(elev) if elev == elev else None, round(dist, 1))
    print(f"stamped {len(best):,} exposure cells", flush=True)

    rows = [{"c": c, "a": v[0], "e": v[1], "d": v[2], "v": VINTAGE} for c, v in best.items()]
    with get_session() as s:
        s.execute(text("DELETE FROM glacial_lake_cell"))
        for i in range(0, len(rows), 5000):
            s.execute(text("""
                INSERT INTO glacial_lake_cell (h3_cell, lake_area_km2, lake_elev_m, dist_km, data_vintage)
                VALUES (:c, :a, :e, :d, :v)
                ON CONFLICT (h3_cell) DO UPDATE SET lake_area_km2=EXCLUDED.lake_area_km2,
                    lake_elev_m=EXCLUDED.lake_elev_m, dist_km=EXCLUDED.dist_km
            """), rows[i:i + 5000])
        s.commit()
    print(f"done: {len(rows):,} glacial_lake_cell rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
