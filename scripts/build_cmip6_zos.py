"""Global CMIP6 ocean-dynamic sea-level (zos) change field — the regional deviation of SLR from global mean.

Companion to build_cmip6_global.py (which builds the atmospheric tas/pr deltas). Sea level is not uniform:
ocean circulation and steric changes make it rise MORE in some places and LESS in others than the global
mean. CMIP6 `zos` (sea-surface height above geoid) captures that ocean-dynamic pattern. Per model, per
(ssp, period):

  dzos(x) = future_mean(zos, x) − hist_mean(zos, x)      [m, on the model's native ocean grid]

Each model's dzos is regridded (nearest) to a common 2° grid, then DEMEANED (area-weighted global ocean mean
subtracted) so only the local-minus-global DEVIATION remains — the global-mean rise is already carried by the
AR6 table in ml/scoring/sea_level.py. Finally the ensemble mean + std across models per cell.

Output: data/cmip6/cmip6_zos_regional.npz  (lat, lon, and {ssp}|{period}|dzos_mean / _std, metres).
Read by ml.scoring.sea_level_regional.regional_dynamic_offset_m(lat, lon, scenario, horizon).

Run (needs gcsfs, scipy; ~streams 4 ocean models, network):  .venv/bin/python -m scripts.build_cmip6_zos
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")
import os
import sys

import gcsfs
import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import griddata

CATALOG = "https://storage.googleapis.com/cmip6/pangeo-cmip6.csv"
MEMBER = "r1i1p1f1"
MODELS = ["MPI-ESM1-2-LR", "IPSL-CM6A-LR", "ACCESS-CM2", "CanESM5"]
SSPS = ["ssp126", "ssp245", "ssp585"]
HIST = (1995, 2014)
PERIODS = {"2021-2040": (2021, 2040), "2041-2060": (2041, 2060), "2081-2100": (2081, 2100)}
OUT = "data/cmip6/cmip6_zos_regional.npz"

TLAT = np.arange(-89.0, 90.0, 2.0)
TLON = np.arange(-179.0, 180.0, 2.0)
GLON, GLAT = np.meshgrid(TLON, TLAT)                       # target 2-D grid (nlat, nlon)


def _latlon(da):
    """Return the ocean grid's 2-D (lat, lon) arrays, whatever the model calls them."""
    for la, lo in (("latitude", "longitude"), ("lat", "lon"), ("nav_lat", "nav_lon")):
        if la in da.coords and lo in da.coords:
            a, o = np.asarray(da[la].values), np.asarray(da[lo].values)
            if a.ndim == 1 and o.ndim == 1:               # rectilinear ocean grid → mesh it
                o, a = np.meshgrid(o, a)
            return a, o
    raise KeyError("no lat/lon coords on zos")


def _period_mean(da, y0, y1):
    yrs = da["time"].dt.year
    return da.isel(time=((yrs >= y0) & (yrs <= y1)).values).mean("time").values   # native 2-D


def _regrid_demean(dzos_native, lat2d, lon2d):
    """Nearest-regrid a native-grid field to the 2° grid, then subtract the area-weighted global mean."""
    lon2d = ((lon2d + 180) % 360) - 180
    pts = np.column_stack([lon2d.ravel(), lat2d.ravel()])
    val = dzos_native.ravel()
    ok = np.isfinite(pts[:, 0]) & np.isfinite(pts[:, 1]) & np.isfinite(val)
    grid = griddata(pts[ok], val[ok], (GLON, GLAT), method="nearest")             # (nlat, nlon)
    # ocean mask: cells with no source within ~2° stay ocean; leave nearest fill, then mask far-inland later
    w = np.cos(np.deg2rad(GLAT))
    gmean = float(np.nansum(grid * w) / np.nansum(w))
    return (grid - gmean).astype("float32")


def main() -> int:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    print("reading Pangeo CMIP6 catalog…", flush=True)
    cat = pd.read_csv(CATALOG)
    gcs = gcsfs.GCSFileSystem(token="anon")

    def zopen(model, exp):
        rows = cat[(cat.source_id == model) & (cat.experiment_id == exp) & (cat.variable_id == "zos")
                   & (cat.table_id == "Omon") & (cat.member_id == MEMBER)]
        if not len(rows):
            return None
        return xr.open_zarr(gcs.get_mapper(rows.iloc[0].zstore), consolidated=True)["zos"]

    acc: dict = {}   # (ssp, period) -> list of per-model demeaned 2° dzos fields
    for model in MODELS:
        try:
            hist = zopen(model, "historical")
            if hist is None:
                print(f"  {model}: no historical zos, skip", flush=True); continue
            lat2d, lon2d = _latlon(hist)
            hmean = _period_mean(hist, *HIST)
            print(f"  {model}: hist ok ({hmean.shape})", flush=True)
            for ssp in SSPS:
                fut = zopen(model, ssp)
                if fut is None:
                    continue
                for per, (y0, y1) in PERIODS.items():
                    dz = _period_mean(fut, y0, y1) - hmean
                    acc.setdefault((ssp, per), []).append(_regrid_demean(dz, lat2d, lon2d))
                print(f"  {model}: {ssp} done", flush=True)
        except Exception as e:                            # one model failing must not sink the ensemble
            print(f"  {model}: ERROR {e}", flush=True)

    arrays = {"lat": TLAT, "lon": TLON}
    for ssp in SSPS:
        for per in PERIODS:
            fields = acc.get((ssp, per), [])
            if fields:
                s = np.array(fields)
                arrays[f"{ssp}|{per}|dzos_mean"] = np.nanmean(s, axis=0).astype("float32")
                arrays[f"{ssp}|{per}|dzos_std"] = np.nanstd(s, axis=0).astype("float32")
    arrays["n_models"] = np.array(max((len(v) for v in acc.values()), default=0))
    np.savez_compressed(OUT, **arrays)
    print(f"wrote {OUT} — {len([k for k in arrays if 'dzos_mean' in k])} scenario×period fields, "
          f"{int(arrays['n_models'])} models", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
