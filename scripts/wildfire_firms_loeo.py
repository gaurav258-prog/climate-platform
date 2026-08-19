"""
Wildfire LOEO with REAL FIRMS labels — the proper test.

Two things were wrong with the failed wildfire model: (1) no fuel features,
(2) crude hand-drawn bounding-box labels. We now have both fixes:
  - fuel features (LAI + soil moisture) in data/multievent_wildfire_fuel.parquet
  - real burn labels in data/firms_burned_cells.json (VIIRS active fire)

ERA5-Land cells are ~9-11 km apart; FIRMS is 375 m. So we SNAP FIRMS onto the
ERA5 grid: a feature cell is 'burned' if a detection lands within SNAP_KM of it.

Then leave-one-event-out, isolating each fix:
  weather-only   (3 feat)  vs  weather+fuel (5 feat)   — both with FIRMS labels
compared against the bbox-label baselines (0.444 / 0.421).
"""
import json
import warnings

warnings.filterwarnings("ignore")
import h3
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from ml.scoring.ensemble import EnsembleScorer

PARQUET = "data/multievent_wildfire_fuel.parquet"
FIRMS = "data/firms_burned_cells.json"
WEATHER = ["gfs_wind_speed_ms", "gfs_relative_humidity_pct", "days_since_last_rain"]
FUEL = WEATHER + ["fuel_load_lai", "soil_moisture"]
SNAP_KM = 6.0   # ≈ half the ERA5-Land grid spacing


def _haversine(la1, lo1, la2, lo2):
    r = 6371.0
    dp = np.radians(la2 - la1); dl = np.radians(lo2 - lo1)
    a = np.sin(dp / 2) ** 2 + np.cos(np.radians(la1)) * np.cos(np.radians(la2)) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def relabel(data, firms):
    """y_firms = 1 if the ERA5 cell is within SNAP_KM of any FIRMS detection cell."""
    data = data.copy()
    data["y_firms"] = 0
    cc = {c: h3.cell_to_latlng(c) for c in data.h3_cell.unique()}
    for ev, sub in data.groupby("event"):
        fcells = firms.get(ev, {}).get("cells", [])
        if not fcells:
            continue
        flat = np.array([h3.cell_to_latlng(c)[0] for c in fcells])
        flon = np.array([h3.cell_to_latlng(c)[1] for c in fcells])
        for idx in sub.index:
            la, lo = cc[data.at[idx, "h3_cell"]]
            if _haversine(la, lo, flat, flon).min() <= SNAP_KM:
                data.at[idx, "y_firms"] = 1
    return data


def loeo(data, feats, label):
    py, ps = [], []
    for held in data.event.unique():
        tr, te = data[data.event != held], data[data.event == held]
        if te[label].sum() == 0 or tr[label].sum() == 0:
            continue
        sc = EnsembleScorer(scale_pos_weight=8.0)
        sc.fit(tr[feats].values, tr[label].values.astype(int), feature_cols=feats)
        s = (sc.score_dataframe(te[feats].copy())["score"] / 100.0).values
        y = te[label].values.astype(int)
        py += y.tolist(); ps += s.tolist()
    py = np.array(py)
    return roc_auc_score(py, ps), average_precision_score(py, ps), py.mean()


def main():
    data = pd.read_parquet(PARQUET)
    firms = json.load(open(FIRMS))
    data = relabel(data, firms)

    print("label comparison (positives per event):")
    print(f"  {'event':30s} {'bbox':>6s} {'FIRMS':>6s} {'cells':>6s}")
    for ev, sub in data.groupby("event"):
        print(f"  {ev:30s} {int(sub.y.sum()):>6d} {int(sub.y_firms.sum()):>6d} {len(sub):>6d}")

    print("\nleave-one-event-out (FIRMS labels):")
    for feats, name in [(WEATHER, "weather-only "), (FUEL, "weather+fuel ")]:
        auc, ap, base = loeo(data, feats, "y_firms")
        print(f"  {name}: AUC={auc:.3f}  AP={ap:.3f}  (base {base:.3f})")
    print("\n  baselines with crude bbox labels: weather-only 0.444 / weather+fuel 0.421")


if __name__ == "__main__":
    main()
