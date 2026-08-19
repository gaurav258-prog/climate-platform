"""Fetch ERA5-Land MONTHLY root-zone SOIL MOISTURE for one region — the water-availability signal.

WHY. Our drought driver is SPEI: a METEOROLOGICAL index (rainfall minus evapotranspiration). It
measures the water the SKY delivered, not the water the CROP actually got. A dry sky over a field
with full soil / reservoirs is not a crop failure; a dry sky over depleted soil is. That gap —
irrigation and antecedent storage — is why Spain's irrigated crops (beet/citrus/almonds) came
back weak or wrong-sign on SPEI, and part of why olive's SPEI r² tops out at 0.51.

Root-zone soil moisture (volumetric_soil_water layers 2+3, ~7–100 cm — where crop roots draw)
integrates rainfall AND antecedent storage AND snowmelt, so it is a strictly better proxy for
"water available to the crop" than a precipitation-only index. It still does NOT capture a farmer
pumping from a reservoir — that needs basin reservoir data, a follow-on — but it is the tractable,
free, global, per-cell, 30-yr first step. Same CDS pipeline as fetch_era5_baseline.py.

    .venv/bin/python scripts/fetch_era5_soil_moisture.py spain_olive 1991 2024
"""
from __future__ import annotations

import os
import sys
import time
import zipfile

import cdsapi

from core.config import settings
from services.ingestion.regions import get_region

OUT_DIR = "data/era5_baseline"
# layer 2 (7–28 cm) + layer 3 (28–100 cm) = the crop root zone. Layer 1 (0–7 cm) is too
# skin-like (dries and wets in hours); layer 4 (100–289 cm) is below most annual-crop roots.
VARIABLES = ["volumetric_soil_water_layer_2", "volumetric_soil_water_layer_3"]


def fetch(region_key: str, y0: int, y1: int) -> str:
    r = get_region(region_key)
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{region_key}_{y0}_{y1}_soilmoisture.nc")
    print(f"soil moisture: {region_key} {y0}-{y1}, {VARIABLES}, area {r.cds_area} -> {out}", flush=True)
    c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=False)
    t0 = time.time()
    c.retrieve("reanalysis-era5-land-monthly-means", {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": VARIABLES,
        "year": [str(y) for y in range(y0, y1 + 1)],
        "month": [f"{m:02d}" for m in range(1, 13)],
        "time": ["00:00"],
        "area": r.cds_area,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }, out)
    if zipfile.is_zipfile(out):
        with zipfile.ZipFile(out) as zf:
            name = [n for n in zf.namelist() if n.endswith(".nc")][0]
            zf.extract(name, OUT_DIR)
            os.replace(os.path.join(OUT_DIR, name), out)
    print(f"SOIL MOISTURE OK in {time.time()-t0:.0f}s -> {out} ({os.path.getsize(out)/1e6:.1f} MB)")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    fetch(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
