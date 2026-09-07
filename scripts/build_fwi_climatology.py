"""Global fire-weather climatology — Copernicus CEMS/ECMWF Fire Weather Index (GEFF, ERA5-driven), EWDS.

Lands data/wildfire/fwi_climatology.npz: per 0.25° cell, the mean annual number of days at each EFFIS fire-danger
class threshold — FWI ≥ 21.3 (very high+), ≥ 38 (extreme+), ≥ 50 (very extreme) — plus the mean annual 95th
percentile of daily FWI, averaged over YEARS. Dataset `cems-fire-historical-v1` (consolidated, system 4.1) on the
CEMS Early Warning Data Store (NOT the CDS; same ECMWF key, EWDS terms-of-use accepted on the account). One request
per year (~700 MB netCDF), reduced immediately to per-year statistics (data/wildfire/fwi_<year>.npz) and deleted,
so the build is resumable and never holds a raw year on disk. This is the climatological fire-WEATHER term of the
wildfire hazard — independent of any burn observation.
Usage: PYTHONPATH=. .venv/bin/python scripts/build_fwi_climatology.py [first_year last_year]
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np

EWDS = "https://ewds.climate.copernicus.eu/api"
OUT_DIR = Path("data/wildfire")
OUT = OUT_DIR / "fwi_climatology.npz"
THRESHOLDS = {"very_high": 21.3, "extreme": 38.0, "very_extreme": 50.0}   # EFFIS FWI danger classes
DAYS = [f"{d:02d}" for d in range(1, 32)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]


def _key() -> str:
    for line in open(os.path.expanduser("~/.cdsapirc")):
        if line.strip().startswith("key:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("no key in ~/.cdsapirc")


def fetch_year(year: int) -> dict:
    import cdsapi
    import xarray as xr
    c = cdsapi.Client(url=EWDS, key=_key(), quiet=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False); tmp.close()
    c.retrieve("cems-fire-historical-v1", {
        "product_type": "reanalysis", "variable": ["fire_weather_index"], "dataset_type": "consolidated_dataset",
        "system_version": "4_1", "year": str(year), "month": MONTHS, "day": DAYS,
        "grid": "0.25/0.25", "data_format": "netcdf",
    }, tmp.name)
    ds = xr.open_dataset(tmp.name)
    fwi = ds["fwinx"]
    tdim = [d for d in fwi.dims if d not in ("latitude", "longitude")][0]
    out = {"lat": ds["latitude"].values, "lon": ds["longitude"].values, "n_days": int(fwi.sizes[tdim])}
    for name, thr in THRESHOLDS.items():
        out[f"days_{name}"] = (fwi >= thr).sum(tdim).values.astype("int16")
    out["p95"] = fwi.quantile(0.95, dim=tdim).values.astype("float32")
    ds.close(); os.unlink(tmp.name)
    return out


def main() -> int:
    y0, y1 = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (2006, 2020)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    acc: dict = {}; years = []; lat = lon = None
    for y in range(y0, y1 + 1):
        p = OUT_DIR / f"fwi_{y}.npz"
        if not p.exists():
            print(f"[fwi] {y} — requesting from EWDS …", flush=True)
            np.savez_compressed(p, **fetch_year(y))
        z = np.load(p); lat, lon = z["lat"], z["lon"]; years.append(y)
        for k in ["days_very_high", "days_extreme", "days_very_extreme", "p95"]:
            acc[k] = acc.get(k, 0) + z[k].astype("float64")
        print(f"  {y}: {int(z['n_days'])} days; global-mean extreme+ days {float(z['days_extreme'].mean()):.1f}", flush=True)
    n = len(years)
    np.savez_compressed(OUT, lat=lat, lon=lon, years=np.array(years),
                        **{k: (v / n).astype("float32") for k, v in acc.items()})
    print(f"saved {OUT}: {n} years, thresholds {THRESHOLDS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
