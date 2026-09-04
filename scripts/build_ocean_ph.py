"""Reduce the OceanSODA-ETHZ surface-ocean pH product to a small recent-climatology grid for scoring.

Source (open) — OceanSODA-ETHZ (Gregor & Gruber), a global gridded surface-ocean carbonate-system product;
file OceanSODA_ETHZ-v2025.OCADS.01-1982-2024.nc (~1.2 GB, NCEI OCADS 0220059). We take the surface total-scale
pH, average the most recent RECENT_YEARS, and save a compact lat/lon field data/ocean_ph/ocean_ph_grid.npz
(NaN over land) — read by ml/scoring/ocean_acidification_point.py. This keeps the 1.2 GB source off the runtime
path (like the CMIP6 delta fields).

Run (after the .nc is downloaded to data/ocean_ph/OceanSODA.nc):
  .venv/bin/python -m scripts.build_ocean_ph
"""
from __future__ import annotations

import os

import numpy as np
import xarray as xr

SRC = "data/ocean_ph/OceanSODA.nc"
OUT = "data/ocean_ph/ocean_ph_grid.npz"
RECENT_YEARS = 10


def _pick_ph(ds: xr.Dataset) -> str:
    for name in ds.data_vars:
        n = name.lower()
        if "ph" in n and "phos" not in n:      # ph_total / pH / spco2... prefer a pH var, not phosphate
            return name
    raise SystemExit(f"no pH variable found in {SRC}; vars = {list(ds.data_vars)}")


def main() -> int:
    if not os.path.exists(SRC):
        print(f"{SRC} not present — download OceanSODA-ETHZ first."); return 2
    ds = xr.open_dataset(SRC)
    var = _pick_ph(ds)
    da = ds[var]
    if "time" in da.dims:
        da = da.isel(time=slice(-12 * RECENT_YEARS, None)).mean("time")
    latn = "lat" if "lat" in da.dims else ("latitude" if "latitude" in da.dims else list(da.dims)[-2])
    lonn = "lon" if "lon" in da.dims else ("longitude" if "longitude" in da.dims else list(da.dims)[-1])
    lat = np.asarray(da[latn].values, dtype="float32")
    lon = np.asarray(da[lonn].values, dtype="float32")
    ph = np.asarray(da.transpose(latn, lonn).values, dtype="float32")
    np.savez_compressed(OUT, lat=lat, lon=lon, ph=ph)
    ok = np.isfinite(ph)
    print(f"wrote {OUT} from var '{var}': grid {ph.shape}, "
          f"ocean pH mean {np.nanmean(ph):.3f} range {np.nanmin(ph):.2f}–{np.nanmax(ph):.2f} ({ok.sum():,} ocean cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
