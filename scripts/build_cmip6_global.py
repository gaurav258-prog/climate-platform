"""Global CMIP6 delta-change field — the worldwide analogue of build_cmip6_deltas.py.

build_cmip6_deltas.py streams the SAME global GCM fields from the public Pangeo CMIP6 zarr archive
but only slices out the crop belts. Financial assets are worldwide, so this computes the delta-change
on a common GLOBAL grid instead of per belt, giving every location its own local warming + precip
change (mean + across-model spread) — the honest uncertainty input a flat "warming × time" multiplier
never had.

Method (identical, delta-change / pattern-scaling): per model, per (ssp, period),
  dTas(x)      = future_mean(tas, x) - hist_mean(tas, x)               [°C]
  dPr_frac(x)  = (future_mean(pr, x) - hist_mean(pr, x)) / hist_mean(pr, x)   [fraction]
each model's delta FIELD is regridded (bilinear) to a common 2° grid, then we take the ENSEMBLE
mean + std across models per grid cell. Deltas (not absolute fields) cancel systematic model bias.

Output: data/cmip6/cmip6_global_deltas.npz (lat, lon, and dtas_mean/std + dpr_mean/std per ssp×period).
Read by ml.scoring.cmip6.cmip6_delta_latlon(lat, lon, scenario, horizon).

Run (needs gcsfs; ~15-40 min, network):  .venv/bin/python -m scripts.build_cmip6_global
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

CATALOG = "https://storage.googleapis.com/cmip6/pangeo-cmip6.csv"
MEMBER = "r1i1p1f1"
MODELS = ["MPI-ESM1-2-LR", "IPSL-CM6A-LR", "ACCESS-CM2", "CanESM5"]  # same 4-model coarse ensemble
SSPS = ["ssp126", "ssp245", "ssp585"]
HIST = (1995, 2014)
PERIODS = {"2021-2040": (2021, 2040), "2041-2060": (2041, 2060), "2081-2100": (2081, 2100)}
OUT = "data/cmip6/cmip6_global_deltas.npz"

# common 2° target grid (financial assets are cities, not sub-2° features)
TLAT = np.arange(-89.0, 90.0, 2.0)
TLON = np.arange(-179.0, 180.0, 2.0)
PR_FLOOR = 1e-7  # kg m-2 s-1 (~0.009 mm/day): below this, fractional precip change is undefined (desert)


def _norm(ds):
    if float(ds.lon.max()) > 180:
        ds = ds.assign_coords(lon=(((ds.lon + 180) % 360) - 180))
    return ds.sortby("lon").sortby("lat")


def _period_field(da, y0, y1):
    """time-mean 2D field over calendar years [y0,y1], regridded to the common 2° grid."""
    yrs = da["time"].dt.year
    m = da.isel(time=((yrs >= y0) & (yrs <= y1)).values).mean("time")
    return m.interp(lat=TLAT, lon=TLON, method="linear").values  # (nlat, nlon)


def main() -> int:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    print("reading Pangeo CMIP6 catalog…", flush=True)
    cat = pd.read_csv(CATALOG)
    gcs = gcsfs.GCSFileSystem(token="anon")

    def zopen(model, exp, var):
        rows = cat[(cat.source_id == model) & (cat.experiment_id == exp) & (cat.variable_id == var)
                   & (cat.table_id == "Amon") & (cat.member_id == MEMBER)]
        if not len(rows):
            return None
        return _norm(xr.open_zarr(gcs.get_mapper(rows.iloc[0].zstore), consolidated=True))

    # accumulate per (ssp, period) -> list of per-model delta fields
    acc_t: dict = {}   # dtas fields
    acc_p: dict = {}   # dpr_frac fields

    def save(n_models):
        arrays = {"lat": TLAT, "lon": TLON, "n_models": np.array(n_models)}
        for ssp in SSPS:
            for per in PERIODS:
                ts = np.array(acc_t.get((ssp, per), []))
                ps = np.array(acc_p.get((ssp, per), []))
                if len(ts):
                    arrays[f"{ssp}|{per}|dtas_mean"] = np.nanmean(ts, axis=0).astype("float32")
                    arrays[f"{ssp}|{per}|dtas_std"] = np.nanstd(ts, axis=0).astype("float32")
                if len(ps):
                    arrays[f"{ssp}|{per}|dpr_mean"] = np.nanmean(ps, axis=0).astype("float32")
                    arrays[f"{ssp}|{per}|dpr_std"] = np.nanstd(ps, axis=0).astype("float32")
        np.savez_compressed(OUT, **arrays)

    done = 0
    for mi, model in enumerate(MODELS, 1):
        print(f"[{mi}/{len(MODELS)}] {model}", flush=True)
        try:
            ht, hp = zopen(model, "historical", "tas"), zopen(model, "historical", "pr")
            if ht is None or hp is None:
                print("   no historical — skip"); continue
            base_t = _period_field(ht["tas"], *HIST)
            base_p = _period_field(hp["pr"], *HIST)
            base_p_safe = np.where(np.abs(base_p) < PR_FLOOR, np.nan, base_p)
            for ssp in SSPS:
                ft, fp = zopen(model, ssp, "tas"), zopen(model, ssp, "pr")
                if ft is None or fp is None:
                    print(f"   {ssp}: missing — skip"); continue
                for per, (y0, y1) in PERIODS.items():
                    dt = _period_field(ft["tas"], y0, y1) - base_t
                    dp = (_period_field(fp["pr"], y0, y1) - base_p) / base_p_safe
                    acc_t.setdefault((ssp, per), []).append(dt)
                    acc_p.setdefault((ssp, per), []).append(dp)
                print(f"   {ssp}: done", flush=True)
            done += 1
            save(done)  # checkpoint after each fully-processed model
            print(f"   checkpointed after {model} ({done} models)", flush=True)
        except Exception as e:
            print(f"   ERROR {type(e).__name__}: {str(e)[:160]} — skipping model")

    save(done)
    # readout for a known belt cell (spain_olive ~37.5N, -4.5E) vs a temperate city (London 51.5N, -0.1E)
    d = np.load(OUT)
    for name, la, lo in [("Andalusia", 37.5, -4.5), ("London", 51.5, -0.1), ("Miami", 25.8, -80.2)]:
        i, j = int(np.abs(TLAT - la).argmin()), int(np.abs(TLON - lo).argmin())
        k = "ssp585|2081-2100"
        print(f"  {name}: hot_house/2100 dTas={d[k+'|dtas_mean'][i,j]:+.2f}±{d[k+'|dtas_std'][i,j]:.2f}°C "
              f"dPr={100*d[k+'|dpr_mean'][i,j]:+.1f}±{100*d[k+'|dpr_std'][i,j]:.1f}%")
    print(f"\nwrote global delta field ({done} models) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
