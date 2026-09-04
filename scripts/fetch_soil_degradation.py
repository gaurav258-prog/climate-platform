"""(Optional) materialise the SDG 15.3.1 land-degradation raster locally (EU-Taxonomy hazard: soil degradation).

The soil-degradation channel is ALREADY LIVE: ml/scoring/soil_degradation_point.py reads the UNCCD SDG 15.3.1
status straight from the Trends.Earth Cloud-Optimized GeoTIFF on demand (a range read of one tile — no bulk
download). This script is only needed if you want a LOCAL copy on infrastructure (faster, offline): it fetches
the 5.4 GB COG (Zenodo 10.5281/zenodo.17079487) so the scorer reads it from disk instead of over HTTP. The
scorer prefers data/soil_degradation/degradation.tif when present.

Source (open) — Trends.Earth SDG Indicator 15.3.1 Datasets, Conservation International, Zenodo 17079487
(ESA-CCI land cover + land-productivity dynamics + SoilGrids SOC; band 1 = degraded-land status).

Run (only if you want a local copy):  SOILDEG_FETCH=1 .venv/bin/python -m scripts.fetch_soil_degradation
Output: data/soil_degradation/degradation.tif (gitignored, ~5.4 GB).
"""
from __future__ import annotations

import os
import subprocess

DEST_DIR = "data/soil_degradation"
TIF = os.path.join(DEST_DIR, "degradation.tif")
URL = "https://zenodo.org/records/17079487/files/TrendsEarth_SDG15.3.1_2000-2023.tiff"


def main() -> int:
    os.makedirs(DEST_DIR, exist_ok=True)
    if os.path.exists(TIF):
        print(f"{TIF} already present — nothing to do."); return 0
    if os.getenv("SOILDEG_FETCH") != "1":
        print("Soil degradation is already LIVE via the on-demand COG read — a local copy is optional.")
        print("The SDG 15.3.1 COG is ~5.4 GB (Zenodo 17079487). To materialise it locally on infra, run:")
        print("  SOILDEG_FETCH=1 .venv/bin/python -m scripts.fetch_soil_degradation")
        return 2
    print("downloading SDG 15.3.1 COG (~5.4 GB, resumable) …", flush=True)
    subprocess.run(["curl", "-sL", "-C", "-", "-o", TIF, URL], check=True)
    print(f"ready: {TIF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
