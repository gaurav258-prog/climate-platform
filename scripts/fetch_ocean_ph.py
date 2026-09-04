"""Fetch the OceanSODA-ETHZ surface-ocean pH product (EU-Taxonomy water hazard: ocean acidification).

Open source — OceanSODA-ETHZ (Gregor & Gruber), global gridded surface-ocean carbonate system; hosted at
NOAA NCEI OCADS (accession 0220059). ~1.2 GB NetCDF covering 1982–present. After download,
scripts/build_ocean_ph.py reduces it to a compact recent-climatology grid the scorer reads.

Run:  .venv/bin/python -m scripts.fetch_ocean_ph  &&  .venv/bin/python -m scripts.build_ocean_ph
Output: data/ocean_ph/OceanSODA.nc (gitignored, ~1.2 GB). Resumable / idempotent.
"""
from __future__ import annotations

import os
import subprocess

DEST_DIR = "data/ocean_ph"
NC = os.path.join(DEST_DIR, "OceanSODA.nc")
URL = ("https://www.ncei.noaa.gov/data/oceans/ncei/ocads/data/0220059/"
       "OceanSODA_ETHZ-v2025.OCADS.01-1982-2024.nc")


def main() -> int:
    os.makedirs(DEST_DIR, exist_ok=True)
    if os.path.exists(os.path.join(DEST_DIR, "ocean_ph_grid.npz")):
        print("ocean_ph_grid.npz already built — nothing to do."); return 0
    print("downloading OceanSODA-ETHZ (~1.2 GB, resumable) …", flush=True)
    # curl -C - resumes a partial file; the product is large, so allow a long timeout.
    subprocess.run(["curl", "-sL", "-C", "-", "-o", NC, URL], check=True)
    print(f"ready: {NC} — now run scripts.build_ocean_ph")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
