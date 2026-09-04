"""Global CMIP6 near-surface wind-speed change field — the wind analogue of build_cmip6_global.py.

`changing wind patterns` is one of the EU Taxonomy's 28 physical climate hazards (wind family, chronic). It
is a projection channel exactly like changing-temperature and changing-precipitation: read the ensemble
fractional change in near-surface wind speed (CMIP6 `sfcWind`, Amon table) between a future period and the
1995–2014 baseline, on the same common 2° grid, with the across-model spread as the honest uncertainty input.

Both an INCREASE and a DECREASE in mean wind speed are hazards (stronger storms / wind loading vs. loss of
wind-energy yield and stagnation), so the scorer keys off the ABSOLUTE fractional change.

Kept as a SEPARATE npz (like build_cmip6_zos.py) so we don't re-stream tas/pr just to add wind. Merged in by
ml.scoring.cmip6.cmip6_delta_latlon, which reads this file if present (older builds without it are unaffected).

Method (identical delta-change / pattern-scaling as the temp/precip builder), per model, per (ssp, period):
  dWind_frac(x) = (future_mean(sfcWind, x) - hist_mean(sfcWind, x)) / hist_mean(sfcWind, x)   [fraction]
each model's delta FIELD is regridded (bilinear) to the common 2° grid, then the ENSEMBLE mean + std across
models per grid cell. Deltas (not absolute fields) cancel systematic model bias.

Output: data/cmip6/cmip6_wind_deltas.npz (lat, lon, n_models, and dwind_mean/std per ssp×period).

Run (needs gcsfs; ~10-25 min, network):  .venv/bin/python -m scripts.build_cmip6_wind
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")
import os

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
OUT = "data/cmip6/cmip6_wind_deltas.npz"

# common 2° target grid (identical to build_cmip6_global.py so the fields co-register)
TLAT = np.arange(-89.0, 90.0, 2.0)
TLON = np.arange(-179.0, 180.0, 2.0)
WIND_FLOOR = 0.1  # m/s: below this a fractional change is undefined (calm-cell guard; sfcWind is ~>1 globally)


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

    acc_w: dict = {}   # dwind_frac fields per (ssp, period)

    def save(n_models):
        arrays = {"lat": TLAT, "lon": TLON, "n_models": np.array(n_models)}
        for ssp in SSPS:
            for per in PERIODS:
                ws = np.array(acc_w.get((ssp, per), []))
                if len(ws):
                    arrays[f"{ssp}|{per}|dwind_mean"] = np.nanmean(ws, axis=0).astype("float32")
                    arrays[f"{ssp}|{per}|dwind_std"] = np.nanstd(ws, axis=0).astype("float32")
        np.savez_compressed(OUT, **arrays)

    done = 0
    for mi, model in enumerate(MODELS, 1):
        print(f"[{mi}/{len(MODELS)}] {model}", flush=True)
        try:
            hw = zopen(model, "historical", "sfcWind")
            if hw is None:
                print("   no historical sfcWind — skip"); continue
            base_w = _period_field(hw["sfcWind"], *HIST)
            base_w_safe = np.where(np.abs(base_w) < WIND_FLOOR, np.nan, base_w)
            for ssp in SSPS:
                fw = zopen(model, ssp, "sfcWind")
                if fw is None:
                    print(f"   {ssp}: missing — skip"); continue
                for per, (y0, y1) in PERIODS.items():
                    dw = (_period_field(fw["sfcWind"], y0, y1) - base_w) / base_w_safe
                    acc_w.setdefault((ssp, per), []).append(dw)
                print(f"   {ssp}: done", flush=True)
            done += 1
            save(done)  # checkpoint after each fully-processed model
            print(f"   checkpointed after {model} ({done} models)", flush=True)
        except Exception as e:
            print(f"   ERROR {type(e).__name__}: {str(e)[:160]} — skipping model")

    if done == 0:
        print("no models processed — wrote nothing"); return 1
    print(f"wrote {OUT} ({done} models)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
