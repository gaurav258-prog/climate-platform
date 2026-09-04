"""Fetch the global permafrost-probability raster (EU-Taxonomy temperature hazard: permafrost thawing).

Authoritative open source — Obu et al. (2019), "Northern Hemisphere permafrost map based on TTOP modelling
for 2000-2016 at 1 km² scale", Earth-Science Reviews; data on PANGAEA (doi:10.1594/PANGAEA.888600, ESA DUE
GlobPermafrost). The Permafrost Probability Fraction (PERPROB) GeoTIFF (0–1, EPSG:3995 Arctic Polar
Stereographic, NH ≥25°N) is the thaw-exposure layer: assets sitting on high-probability permafrost carry
degradation/thaw risk. Sampled at runtime by ml/scoring/permafrost_point.py (screening tier).

NOTE — the PANGAEA per-file download URLs are served through a JS landing page (not a stable direct link that
resolves from an automated environment), so this fetcher takes PERPROB_URL from the environment: set it to the
exact PERPROB GeoTIFF download URL (copy it from https://doi.pangaea.de/10.1594/PANGAEA.888600) and re-run.
Once the file lands at data/permafrost/PERPROB.tif the permafrost channel lights up with zero code change.

Run:  PERPROB_URL="https://download.pangaea.de/dataset/888600/files/<PERPROB file>.tif" \
      .venv/bin/python -m scripts.fetch_permafrost
Output: data/permafrost/PERPROB.tif (gitignored). Idempotent — skips if the tif already exists.
"""
from __future__ import annotations

import os
import urllib.request

DEST_DIR = "data/permafrost"
TIF = os.path.join(DEST_DIR, "PERPROB.tif")
PERPROB_URL = os.getenv("PERPROB_URL")


def main() -> int:
    os.makedirs(DEST_DIR, exist_ok=True)
    if os.path.exists(TIF):
        print(f"{TIF} already present — nothing to do.")
        return 0
    if not PERPROB_URL:
        print("PERPROB_URL not set. Copy the exact Permafrost Probability (PERPROB) GeoTIFF download URL from")
        print("  https://doi.pangaea.de/10.1594/PANGAEA.888600")
        print("and re-run:  PERPROB_URL=<url> .venv/bin/python -m scripts.fetch_permafrost")
        return 2
    print(f"downloading permafrost probability → {TIF} …", flush=True)
    urllib.request.urlretrieve(PERPROB_URL, TIF)
    print(f"ready: {TIF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
