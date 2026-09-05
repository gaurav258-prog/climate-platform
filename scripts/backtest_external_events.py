"""
Out-of-event backtest: score REAL historical floods the model never trained on.

The flood model was trained on a single event (Jul 2021). This fetches ERA5 for
other well-documented European floods, builds the same three features the model
uses, scores each cell with the trained model, and checks whether the model
lights up over the documented flood corridor — i.e. whether it generalises to an
event it has never seen.

Labels are an informed footprint of the documented worst-hit river corridor (an
approximation, stated as such) — enough to measure whether the model ranks those
cells above the surrounding region during the event.

Run:  python scripts/backtest_external_events.py
"""
import sys
import warnings
from datetime import date, timedelta

warnings.filterwarnings("ignore")
import h3
import numpy as np
import pandas as pd
import xarray as xr
from sklearn.metrics import average_precision_score, roc_auc_score

# Events the model never saw. fetch_area / flood_bbox are [N, W, S, E].
EVENTS = [
    {
        "name": "2002 Elbe/Vltava flood",
        "peak": date(2002, 8, 13),
        "fetch_area": [52.0, 11.0, 48.0, 16.0],     # Saxony / Bohemia
        "flood_bbox": [51.2, 13.4, 50.0, 14.6],     # Dresden–Prague river corridor
    },
    {
        "name": "2013 Central Europe flood",
        "peak": date(2013, 6, 3),
        "fetch_area": [51.0, 10.0, 47.5, 15.0],     # Danube / Inn / Saale
        "flood_bbox": [49.2, 12.8, 48.2, 14.2],     # Passau / lower Inn corridor
    },
]

VARS = ["total_precipitation", "volumetric_soil_water_layer_1", "runoff"]
H3_RES = 8


def fetch(ev):
    """One CDS request: 8-day window of the 3 vars over the event area."""
    import os
    import shutil
    import tempfile
    import zipfile

    import cdsapi
    days = [(ev["peak"] - timedelta(days=k)) for k in range(8)]
    c = cdsapi.Client(quiet=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False); tmp.close()
    c.retrieve("reanalysis-era5-land", {
        "variable": VARS,
        "year": sorted({str(d.year) for d in days}),
        "month": sorted({f"{d.month:02d}" for d in days}),
        "day": sorted({f"{d.day:02d}" for d in days}),
        "time": ["23:00"],
        "area": ev["fetch_area"],
        "format": "netcdf",
    }, tmp.name)
    path = tmp.name
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            nc = [n for n in zf.namelist() if n.endswith(".nc")][0]
            out = path + "_d.nc"
            with zf.open(nc) as s, open(out, "wb") as d:
                shutil.copyfileobj(s, d)
        os.unlink(path); path = out
    return xr.open_dataset(path)


def features(ds, ev):
    """Build precip_7d_mm, soil_saturation_index, glofas_discharge_m3s per H3 cell."""
    tvar = "valid_time" if "valid_time" in ds else ("time" if "time" in ds else None)
    lat = ds["latitude"].values; lon = ds["longitude"].values
    tp = ds["tp"]; sw = ds["swvl1"]; ro = ds["ro"] if "ro" in ds else ds.get("runoff")
    # collapse time: precip = sum over window (×1000 m→mm); soil/runoff = last day
    tp_sum = (tp.sum(dim=tvar) * 1000.0).values
    sw_last = sw.isel({tvar: -1}).values
    ro_last = ro.isel({tvar: -1}).values
    rows = []
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            v_tp = tp_sum[i, j]
            if np.isnan(v_tp):
                continue
            cell = h3.latlng_to_cell(float(la), float(lo), H3_RES)
            in_flood = (ev["flood_bbox"][2] <= la <= ev["flood_bbox"][0] and
                        ev["flood_bbox"][1] <= lo <= ev["flood_bbox"][3])
            rows.append({
                "h3_cell": cell,
                "precipitation_7d_mm": float(v_tp),
                "soil_saturation_index": float(sw_last[i, j]),
                "glofas_discharge_m3s": float(ro_last[i, j]),
                "y": 1 if in_flood else 0,
            })
    df = pd.DataFrame(rows).groupby("h3_cell", as_index=False).agg(
        precipitation_7d_mm=("precipitation_7d_mm", "max"),
        soil_saturation_index=("soil_saturation_index", "mean"),
        glofas_discharge_m3s=("glofas_discharge_m3s", "max"),
        y=("y", "max"),
    )
    return df


def main():
    from ml.scoring.engine import _load_ensemble_scorer
    scorer = _load_ensemble_scorer(None, "flood")   # always the latest trained flood model, never pinned
    if scorer is None:
        print("could not load flood model"); sys.exit(1)
    feats = ["precipitation_7d_mm", "soil_saturation_index", "glofas_discharge_m3s"]

    print("\n=== Out-of-event backtest — flood model on events it NEVER trained on ===\n")
    pooled_y, pooled_s = [], []
    for ev in EVENTS:
        print(f"• {ev['name']} (peak {ev['peak']}) — fetching ERA5 …", flush=True)
        ds = fetch(ev)
        df = features(ds, ev); ds.close()
        df["score"] = scorer.score_dataframe(df[feats].copy())["score"].values
        y = df["y"].values
        if y.sum() == 0 or y.sum() == len(y):
            print("   (no class variation in region — skipping metrics)"); continue
        auc = roc_auc_score(y, df["score"]); ap = average_precision_score(y, df["score"])
        flood_med = df.loc[df.y == 1, "score"].median()
        dry_med = df.loc[df.y == 0, "score"].median()
        print(f"   cells={len(df)}  flood-corridor cells={int(y.sum())}")
        print(f"   median score  flood-corridor={flood_med:.1f}  vs  rest={dry_med:.1f}")
        print(f"   out-of-event ROC-AUC={auc:.3f}  Avg-Precision={ap:.3f}  (base rate {y.mean():.3f})\n")
        pooled_y += y.tolist(); pooled_s += df["score"].tolist()

    if pooled_y:
        py, ps = np.array(pooled_y), np.array(pooled_s)
        print("=== POOLED across held-out events ===")
        print(f"   ROC-AUC={roc_auc_score(py, ps):.3f}  Avg-Precision={average_precision_score(py, ps):.3f}"
              f"  base rate={py.mean():.3f}")
        print("\n   This is the model scoring floods OUTSIDE its training event —")
        print("   the first real test of generalisation. Labels are documented-corridor")
        print("   approximations; treat magnitudes as indicative, direction as the signal.\n")


if __name__ == "__main__":
    main()
