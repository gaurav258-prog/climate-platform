"""Fetch a global land-degradation raster (EU-Taxonomy solid-mass hazard: soil degradation).

The authoritative global land-degradation layers are ISRIC GLADA / GLADIS (NDVI-trend based) and FAO's
degradation assessments. Unlike GloSEM (erosion) or the subsidence map, there is no single clean anonymous
GeoTIFF download for a *degradation index* — GLADA is distributed via ISRIC and FAO SOLAW channels. So this is
WIRED-READY: obtain a global degradation index GeoTIFF (0–100 or classed), drop it at
data/soil_degradation/degradation.tif, and the channel lights up (ml/scoring/soil_degradation_point.py) with
zero code change. Set SOILDEG_URL to a direct GeoTIFF URL to have this fetch it for you.

Run:  SOILDEG_URL="<direct GeoTIFF url>" .venv/bin/python -m scripts.fetch_soil_degradation
Output: data/soil_degradation/degradation.tif (gitignored). Idempotent.
"""
from __future__ import annotations

import os
import urllib.request

DEST_DIR = "data/soil_degradation"
TIF = os.path.join(DEST_DIR, "degradation.tif")
SOILDEG_URL = os.getenv("SOILDEG_URL")


def main() -> int:
    os.makedirs(DEST_DIR, exist_ok=True)
    if os.path.exists(TIF):
        print(f"{TIF} already present — nothing to do."); return 0
    if not SOILDEG_URL:
        print("SOILDEG_URL not set. Obtain a global land-degradation index GeoTIFF (ISRIC GLADA / FAO GLADIS)")
        print("  → https://www.isric.org/projects/global-assessment-land-degradation-and-improvement-glada")
        print(f"  and either set SOILDEG_URL=<direct url> or drop the GeoTIFF at {TIF}, then re-run.")
        return 2
    print(f"downloading land-degradation raster → {TIF} …", flush=True)
    urllib.request.urlretrieve(SOILDEG_URL, TIF)
    print(f"ready: {TIF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
