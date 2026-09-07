"""Global observed burn-frequency climatology — C3S / ESA-CCI Fire burned area (MODIS, 0.25° grid product).

Lands data/wildfire/burned_area_climatology.npz: per 0.25° cell, the mean annual burned FRACTION of burnable land
over 2001-2020 (and the number of years with any burn) from the Copernicus Climate Data Store dataset
`satellite-fire-burned-area` (ESA CCI Fire v5.1.1cds, monthly grid product; burned_area in m² per cell). This is the
observed HISTORY term of the wildfire hazard climatology — where fire has actually recurred — independent of any
fire-weather input. Resumable: one CDS request per year, cached as data/wildfire/ba_<year>.npz.
Usage: PYTHONPATH=. .venv/bin/python scripts/build_burned_area_climatology.py [first_year last_year]
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

OUT_DIR = Path("data/wildfire")
OUT = OUT_DIR / "burned_area_climatology.npz"
DATASET = "satellite-fire-burned-area"
MONTHS = [f"{m:02d}" for m in range(1, 13)]


def fetch_year(year: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """→ (lat, lon, annual burned fraction of burnable area) for one year, from 12 monthly grid files."""
    import cdsapi
    import xarray as xr
    c = cdsapi.Client(quiet=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False); tmp.close()
    c.retrieve(DATASET, {"origin": "esa_cci", "sensor": "modis", "variable": "grid_variables", "version": "5_1_1cds",
                         "year": str(year), "month": MONTHS, "nominal_day": "01"}, tmp.name)
    d = tempfile.mkdtemp()
    with zipfile.ZipFile(tmp.name) as z:
        z.extractall(d)
    os.unlink(tmp.name)
    files = sorted(Path(d).glob("*.nc"))
    burned = None
    for f in files:
        ds = xr.open_dataset(f)
        ba = ds["burned_area"].isel(time=0).values.astype("float64")          # m² burned in the month
        if burned is None:
            lat, lon = ds["lat"].values, ds["lon"].values
            burnable = ds["fraction_of_burnable_area"].isel(time=0).values.astype("float64")
            burned = np.zeros_like(ba)
        burned += np.nan_to_num(ba)
        ds.close()
    shutil.rmtree(d, ignore_errors=True)
    # cell area (m²) of a 0.25° cell at each latitude
    dlat = np.abs(np.diff(lat)).mean(); dlon = np.abs(np.diff(lon)).mean()
    r = 6371000.0
    cell_area = (np.radians(dlat) * r) * (np.radians(dlon) * r * np.cos(np.radians(lat)))[:, None] * np.ones((1, len(lon)))
    burnable_area = cell_area * np.clip(np.nan_to_num(burnable), 0, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(burnable_area > 0, burned / burnable_area, np.nan)
    return lat, lon, np.clip(frac, 0, 1).astype("float32")


def fetch_burnable() -> np.ndarray:
    """fraction_of_burnable_area (static land/vegetation mask of the product) from one monthly file."""
    import cdsapi
    import xarray as xr
    c = cdsapi.Client(quiet=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False); tmp.close()
    c.retrieve(DATASET, {"origin": "esa_cci", "sensor": "modis", "variable": "grid_variables", "version": "5_1_1cds",
                         "year": "2019", "month": "07", "nominal_day": "01"}, tmp.name)
    d = tempfile.mkdtemp()
    with zipfile.ZipFile(tmp.name) as z:
        z.extractall(d)
    os.unlink(tmp.name)
    ds = xr.open_dataset(sorted(Path(d).glob("*.nc"))[0])
    b = np.clip(np.nan_to_num(ds["fraction_of_burnable_area"].isel(time=0).values.astype("float32")), 0, 1)
    ds.close(); shutil.rmtree(d, ignore_errors=True)
    return b


def main() -> int:
    y0, y1 = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (2001, 2019)   # product ends 2019
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    years, stack, lat = [], [], None
    for y in range(y0, y1 + 1):
        p = OUT_DIR / f"ba_{y}.npz"
        if not p.exists():
            print(f"[burned area] {y} — requesting from CDS …", flush=True)
            la, lo, frac = fetch_year(y)
            np.savez_compressed(p, lat=la, lon=lo, frac=frac)
        z = np.load(p)
        lat, lon, frac = z["lat"], z["lon"], z["frac"]
        years.append(y); stack.append(frac)
        print(f"  {y}: global burnable land burned {100*np.nanmean(frac):.2f}%  max cell {100*np.nanmax(frac):.0f}%", flush=True)
    s = np.stack(stack)
    mean_frac = np.nanmean(s, axis=0)
    years_with_burn = np.nansum(s > 0.001, axis=0)
    bp = OUT_DIR / "burnable_fraction.npz"
    if not bp.exists():
        np.savez_compressed(bp, burnable=fetch_burnable())
    burnable = np.load(bp)["burnable"]
    np.savez_compressed(OUT, lat=lat, lon=lon, mean_annual_burned_fraction=mean_frac.astype("float32"),
                        years_with_burn=years_with_burn.astype("int16"), burnable_fraction=burnable, years=np.array(years))
    print(f"saved {OUT}: {len(years)} years; cells with any burn {int((years_with_burn > 0).sum())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
