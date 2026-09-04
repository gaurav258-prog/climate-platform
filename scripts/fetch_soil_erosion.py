"""Fetch the GloSEM global soil-erosion raster (EU-Taxonomy solid-mass hazard: soil erosion).

Authoritative source (OPEN — no registration) — Borrelli et al., GloSEM (Global Soil Erosion Modelling),
"High-resolution global estimates of present and future soil displacement in croplands by water erosion",
Scientific Data (2022). The dataset is published open on figshare (Springer Nature collection 5844758) as
well as ESDAC; GloSEM 1.3 is a ~100 m GeoTIFF of soil displacement by water (Mg ha⁻¹ yr⁻¹, WGS84).

⚠️ SIZE, not licence — the present-day layer ("GloSEM 1.3 scenario 2019", figshare article 19181234) is a
~16.5 GB .rar. That is an infrastructure-scale download + preprocess, not a sandbox one — so this fetcher is
OFF by default and needs GLOSEM_FETCH=1 to proceed (guarding against an accidental 16.5 GB pull). On infra:
download it, extract the soil-displacement GeoTIFF, and drop it at data/soil_erosion/GloSEM.tif — the
soil-erosion channel then lights up with zero code change (ml/scoring/soil_erosion_point.py). A coarser
resample is the right move for the standing layer; the on-demand path samples the full-res raster directly.

Run (on infra):  GLOSEM_FETCH=1 .venv/bin/python -m scripts.fetch_soil_erosion
Output: data/soil_erosion/GloSEM.tif (gitignored). Idempotent — skips if the tif already exists.
"""
from __future__ import annotations

import os
import subprocess
import urllib.request

DEST_DIR = "data/soil_erosion"
TIF = os.path.join(DEST_DIR, "GloSEM.tif")
RAR = os.path.join(DEST_DIR, "GloSEM_2019.rar")
# figshare direct download (article 19181234 "GloSEM 1.3 scenario 2019", ~16.5 GB .rar) — OPEN, no registration.
GLOSEM_URL = os.getenv("GLOSEM_URL", "https://ndownloader.figshare.com/files/34079996")


def main() -> int:
    os.makedirs(DEST_DIR, exist_ok=True)
    if os.path.exists(TIF):
        print(f"{TIF} already present — nothing to do.")
        return 0
    if os.getenv("GLOSEM_FETCH") != "1":
        print("GloSEM present-day layer is ~16.5 GB (figshare article 19181234) — an infra-scale download.")
        print("This fetcher is guarded. On infrastructure, run:  GLOSEM_FETCH=1 .venv/bin/python -m scripts.fetch_soil_erosion")
        print("or drop the extracted soil-displacement GeoTIFF at", TIF)
        return 2
    print(f"downloading GloSEM 2019 (~16.5 GB) → {RAR} …", flush=True)
    urllib.request.urlretrieve(GLOSEM_URL, RAR)
    print("extracting …", flush=True)
    subprocess.run(["bsdtar", "-xf", os.path.basename(RAR)], cwd=DEST_DIR, check=True)
    print(f"extracted into {DEST_DIR}; rename the soil-displacement GeoTIFF to {TIF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
