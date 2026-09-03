"""Fetch NASA's Global Landslide Susceptibility Map (the static baseline for the landslide hazard channel).

Source: NASA Goddard / LHASA — a 30 arc-second (~1 km) global susceptibility raster derived from slope,
geology, road networks, fault zones and forest loss (Stanley & Kirschbaum). EPSG:4326, int8 classes 0–5
(0 negligible … 5 very high), nodata=127, coverage 60°S–72°N.
  https://gpm.nasa.gov/landslides/projects.html  ·  data: gpm.nasa.gov global-landslide-susceptibility-map

Idempotent: skips the download if the file already exists. The landslide point scorer
(ml/scoring/landslide_point.py) reads this file directly at full resolution, so no baseline table is built.
"""
from __future__ import annotations

import sys
from pathlib import Path

URL = "https://gpm.nasa.gov/sites/default/files/downloads/global-landslide-susceptibility-map-2-27-23.tif"
DEST = Path(__file__).resolve().parents[1] / "data" / "landslide" / "global_landslide_susceptibility.tif"


def main() -> int:
    if DEST.exists() and DEST.stat().st_size > 1_000_000:
        print(f"already present: {DEST} ({DEST.stat().st_size/1e6:.1f} MB)")
        return 0
    DEST.parent.mkdir(parents=True, exist_ok=True)
    import requests

    print(f"downloading {URL}")
    with requests.get(URL, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(DEST, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    print(f"saved {DEST} ({DEST.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
