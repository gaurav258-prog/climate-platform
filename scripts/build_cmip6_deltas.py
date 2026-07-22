"""Raw multi-model CMIP6 delta-change fields for the crop belts (projections v3).

Replaces the parametric warming amplification + single Mediterranean precip coefficient with ACTUAL
GCM output. The delta-change ("pattern scaling") method — the standard, bias-robust way to use raw
GCM data for local impacts: we take each model's projected CHANGE (future period minus its own
1995-2014 baseline), not its absolute field, so systematic model biases cancel.

For each crop belt box we compute, per model:
  dTas  = future_mean(tas) - hist_mean(tas)            [°C, absolute]
  dPr   = (future_mean(pr) - hist_mean(pr)) / hist_mean(pr)   [fraction, sign carries drying/wetting]
area-weighted (cos-lat) over the box, then ENSEMBLE mean + std across models (the spread is a real,
honest uncertainty input the parametric model never had).

Source: the Pangeo CMIP6 zarr archive on Google Cloud (public, anonymous) — reliable, no queuing,
unlike the CDS/ROOCS backend. Amon (monthly) tas + pr, member r1i1p1f1, 8 full-coverage models
spanning low→high equilibrium sensitivity (GFDL-ESM4/MPI low, CanESM5 high).

Output: data/cmip6/cmip6_deltas.csv (compact, committed). Run (needs gcsfs; minutes, network):
    .venv/bin/python -m scripts.build_cmip6_deltas
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import os, sys, csv
import numpy as np
import pandas as pd
import gcsfs
import xarray as xr

from services.ingestion.regions import REGIONS

CATALOG = "https://storage.googleapis.com/cmip6/pangeo-cmip6.csv"
MEMBER = "r1i1p1f1"
# COARSE-grid, full-coverage core spanning low→high equilibrium sensitivity (ECS ~3.0 MPI → ~5.6
# CanESM5). The finer-grid models (GFDL-ESM4 180×288, MRI-ESM2-0, EC-Earth3 256×512, MIROC6) read
# too slowly / hang off GCS to be worth the wall-clock, so they're excluded — a 4-model coarse
# ensemble is still a legitimate multi-model spread for regional deltas.
MODELS = ["MPI-ESM1-2-LR", "IPSL-CM6A-LR", "ACCESS-CM2", "CanESM5"]
SSPS = ["ssp126", "ssp245", "ssp585"]
HIST = (1995, 2014)
PERIODS = {"2021-2040": (2021, 2040), "2041-2060": (2041, 2060), "2081-2100": (2081, 2100)}
# the crop belts that carry (or may carry) a scored projection — agriculture regions only
BELTS = ["spain_olive", "spain_extremadura", "spain_citrus", "spain_beet", "portugal_alentejo",
         "morocco_wheat", "algeria_wheat", "tunisia_wheat", "iran_wheat", "turkey_wheat",
         "syria_wheat", "australia_wheat", "west_africa_cocoa"]
OUT = "data/cmip6/cmip6_deltas.csv"


def _norm(ds):
    """0-360 lon → -180..180, sort lat/lon so box slicing is well-defined regardless of model grid."""
    if float(ds.lon.max()) > 180:
        ds = ds.assign_coords(lon=(((ds.lon + 180) % 360) - 180))
    return ds.sortby("lon").sortby("lat")


def _box_period_mean(da, r, y0, y1):
    """cos-lat-weighted area mean over the belt box for calendar years [y0,y1]; nearest-cell if the
    box falls between the coarse GCM gridpoints."""
    yrs = da["time"].dt.year
    da = da.isel(time=((yrs >= y0) & (yrs <= y1)).values)
    sub = da.sel(lat=slice(r.min_lat, r.max_lat), lon=slice(r.min_lon, r.max_lon))
    if sub.sizes.get("lat", 0) == 0 or sub.sizes.get("lon", 0) == 0:  # sub-gridscale belt
        sub = da.sel(lat=(r.min_lat + r.max_lat) / 2, lon=(r.min_lon + r.max_lon) / 2, method="nearest")
        return float(sub.mean("time"))
    w = np.cos(np.deg2rad(sub.lat))
    return float(sub.mean("time").weighted(w).mean(("lat", "lon")))


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

    def flush(acc):
        """Rewrite the CSV from the ensemble computed SO FAR — a checkpoint after each model, so a
        slow/hanging later model never costs the whole run."""
        with open(OUT, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["region", "ssp", "period", "dtas_mean_c", "dtas_std_c",
                        "dpr_frac_mean", "dpr_frac_std", "n_models"])
            for (b, ssp, per), d in sorted(acc.items()):
                dt, dp = np.array(d["dt"]), np.array(d["dp"])
                w.writerow([b, ssp, per, round(float(dt.mean()), 3), round(float(dt.std()), 3),
                            round(float(dp.mean()), 4), round(float(dp.std()), 4), len(dt)])

    # accumulate per (belt, ssp, period, var) -> list of per-model deltas
    acc: dict = {}
    for mi, model in enumerate(MODELS, 1):
        print(f"[{mi}/{len(MODELS)}] {model}", flush=True)
        try:
            hist_t = zopen(model, "historical", "tas"); hist_p = zopen(model, "historical", "pr")
            if hist_t is None or hist_p is None:
                print("   no historical — skip"); continue
            base_t = {b: _box_period_mean(hist_t["tas"], REGIONS[b], *HIST) for b in BELTS}
            base_p = {b: _box_period_mean(hist_p["pr"], REGIONS[b], *HIST) for b in BELTS}
            for ssp in SSPS:
                fut_t = zopen(model, ssp, "tas"); fut_p = zopen(model, ssp, "pr")
                if fut_t is None or fut_p is None:
                    print(f"   {ssp}: missing — skip"); continue
                for per, (y0, y1) in PERIODS.items():
                    for b in BELTS:
                        dt = _box_period_mean(fut_t["tas"], REGIONS[b], y0, y1) - base_t[b]
                        pf = base_p[b]
                        dp = (_box_period_mean(fut_p["pr"], REGIONS[b], y0, y1) - pf) / pf if pf else 0.0
                        acc.setdefault((b, ssp, per), {"dt": [], "dp": []})
                        acc[(b, ssp, per)]["dt"].append(dt)
                        acc[(b, ssp, per)]["dp"].append(dp)
                print(f"   {ssp}: done", flush=True)
            flush(acc)  # checkpoint after each fully-processed model
            print(f"   checkpointed after {model} ({mi}/{len(MODELS)})", flush=True)
        except Exception as e:
            print(f"   ERROR {type(e).__name__}: {str(e)[:160]} — skipping model")

    flush(acc)
    print(f"\nwrote {len(acc)} (belt×ssp×period) rows -> {OUT}")
    # a quick readout for the flagship
    for ssp in SSPS:
        d = acc.get(("spain_olive", ssp, "2081-2100"))
        if d:
            print(f"  spain_olive {ssp} 2081-2100: dTas={np.mean(d['dt']):+.2f}±{np.std(d['dt']):.2f}°C  "
                  f"dPr={100*np.mean(d['dp']):+.1f}±{100*np.std(d['dp']):.1f}%  (n={len(d['dt'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
