"""Fetch the Global Subsidence Susceptibility raster (EU-Taxonomy solid-mass hazard: land subsidence).

Authoritative open source — Herrera-García et al. (2021), "Mapping the global threat of land subsidence",
Science 371(6524):34-36, doi:10.1126/science.abb8549. The global susceptibility map is published openly on
figshare ("Global Subsidence Maps", doi:10.6084/m9.figshare.13312070) — no registration.

We take GSS.tif = Global Subsidence Susceptibility (2010): a ~1 km GeoTIFF (EPSG:4326) whose pixels carry a
six-level classified susceptibility (1 very-low … 6 very-high; 15 = nodata). It is a geophysical PREDISPOSITION
layer (aquifer-system + lithology + groundwater + urban load), so — like landslide/seismic — it does not vary
by climate scenario. Sampled at each asset point at runtime by ml/scoring/subsidence_point.py (screening tier).

Run:  .venv/bin/python -m scripts.fetch_subsidence
Output: data/subsidence/GSS.tif (gitignored; ~32 MB). Idempotent — skips download if the tif already exists.
"""
from __future__ import annotations

import os
import subprocess
import urllib.request

DEST_DIR = "data/subsidence"
RAR = os.path.join(DEST_DIR, "GSS.rar")
TIF = os.path.join(DEST_DIR, "GSS.tif")
# figshare direct download (article 13312070 → GSS.rar); resolved via the figshare v2 files API.
GSS_URL = "https://ndownloader.figshare.com/files/25764206"


def main() -> int:
    os.makedirs(DEST_DIR, exist_ok=True)
    if os.path.exists(TIF):
        print(f"{TIF} already present — nothing to do.")
        return 0
    if not os.path.exists(RAR):
        print(f"downloading Global Subsidence Susceptibility → {RAR} …", flush=True)
        urllib.request.urlretrieve(GSS_URL, RAR)
    print("extracting GSS.tif …", flush=True)
    # RAR v5 — bsdtar (libarchive) reads it without a separate unrar binary.
    subprocess.run(["bsdtar", "-xf", "GSS.rar"], cwd=DEST_DIR, check=True)
    if not os.path.exists(TIF):
        print("ERROR: GSS.tif not found after extraction"); return 1
    print(f"ready: {TIF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
