"""EFFIS (JRC, Copernicus EMS) burnt-area polygons — independent wildfire target.

For each real European fire event in scripts/build_multievent_wildfire.EVENTS, pulls the official EFFIS
MODIS burnt-area mapping polygons (layer ms:modis.ba.poly, WFS) inside the event's fetch_area and a
±WINDOW-day window around the peak date, to data/wildfire_val/effis_<slug>.geojson. These polygons are the
JRC's mapped burn scars (from MODIS 250 m imagery) — NOT the VIIRS active-fire hotspots the model was
labelled with, and not an input to the ERA5-Land fire-weather features the model scores from.
WFS 1.1.0 + EPSG:4326 means the bbox is LAT-first (miny,minx,maxy,maxx). CQL filters are refused (403);
we filter by FIREDATE client-side. Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_effis_burnt_area.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import timedelta
from pathlib import Path

import requests

from scripts.build_multievent_wildfire import EVENTS

WFS = "https://maps.effis.emergency.copernicus.eu/effis"
OUT = Path("data/wildfire_val")
WINDOW_BEFORE, WINDOW_AFTER = 7, 21   # burn scars are dated by first detection (fires start days before the peak)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _wfs_bbox(n: float, w: float, s: float, e: float, depth: int = 0) -> list[dict]:
    """One GetFeature for a lat/lon box; on a server 500 (large boxes) split into quadrants and recurse."""
    r = requests.get(WFS, params={
        "service": "WFS", "version": "1.1.0", "request": "GetFeature", "typename": "ms:modis.ba.poly",
        "outputFormat": "geojson", "srsname": "EPSG:4326", "bbox": f"{s},{w},{n},{e},EPSG:4326", "maxFeatures": 20000,
    }, timeout=300)
    if r.status_code >= 500 and depth < 3:
        mlat, mlon = (n + s) / 2, (w + e) / 2
        return (_wfs_bbox(n, w, mlat, mlon, depth + 1) + _wfs_bbox(n, mlon, mlat, e, depth + 1)
                + _wfs_bbox(mlat, w, s, mlon, depth + 1) + _wfs_bbox(mlat, mlon, s, e, depth + 1))
    r.raise_for_status()
    return r.json().get("features", [])


def fetch_event(ev: dict) -> dict:
    n, w, s, e = ev["fetch_area"]
    feats = {f["properties"]["id"]: f for f in _wfs_bbox(n, w, s, e)}.values()   # de-dup across quadrants
    feats = list(feats)
    lo = (ev["peak"] - timedelta(days=WINDOW_BEFORE)).isoformat()
    hi = (ev["peak"] + timedelta(days=WINDOW_AFTER)).isoformat()
    keep = [f for f in feats if lo <= (f["properties"].get("FIREDATE") or "")[:10] <= hi]
    return {"type": "FeatureCollection", "event": ev["name"], "peak": ev["peak"].isoformat(),
            "window": [lo, hi], "n_in_bbox_all_years": len(feats), "features": keep,
            "source": "EFFIS burnt-area mapping (ms:modis.ba.poly), JRC / Copernicus EMS"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for ev in EVENTS:
        p = OUT / f"effis_{slug(ev['name'])}.geojson"
        fc = fetch_event(ev)
        p.write_text(json.dumps(fc))
        ha = sum(float(f["properties"].get("AREA_HA") or 0) for f in fc["features"])
        print(f"{ev['name']:32s} polygons in window {len(fc['features']):4d}  burnt {ha:9.0f} ha  "
              f"(bbox all-years {fc['n_in_bbox_all_years']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
