"""
Multi-event flood training + leave-one-event-out backtest.

The flood model failed to generalise because it was trained on ONE event. This
fetches ERA5 for several real European floods, builds the same three features for
each, labels the documented flood corridor, then runs leave-one-event-out (LOEO):
for each event, train on the OTHER events and score the held-out one. The pooled
LOEO AUC/AP is the honest measure of whether the model can forecast a flood it has
never seen.

Labels are documented-corridor approximations (geographic, NOT derived from the
features), so the test is honest about direction even if magnitudes are noisy.

Fetched data is cached to data/multievent_flood.parquet so re-runs skip CDS.

Run:  python scripts/build_multievent_flood.py
"""
import os
import sys
import warnings
from datetime import date

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from backtest_external_events import fetch, features

CACHE = "data/multievent_flood.parquet"

# Real European floods. fetch_area / flood_bbox are [N, W, S, E].
# `mech` = hydrological mechanism (the physics we'd split on, NOT a label of convenience):
#   riverine = slow-onset, large-basin, soil-saturation + river-discharge driven, multi-day
#   flash    = convective/short-duration intense rain, fast response, steep or Mediterranean
EVENTS = [
    {"name": "2002 Elbe/Vltava",      "mech": "riverine", "peak": date(2002, 8, 13), "fetch_area": [52.0, 11.0, 48.0, 16.0], "flood_bbox": [51.2, 13.4, 50.0, 14.6]},
    {"name": "2005 Alpine (Tyrol/Bavaria)", "mech": "riverine", "peak": date(2005, 8, 23), "fetch_area": [49.0, 9.0, 46.0, 14.0], "flood_bbox": [48.0, 10.5, 47.0, 12.5]},
    {"name": "2010 Vistula (Poland)",  "mech": "riverine", "peak": date(2010, 5, 19), "fetch_area": [53.0, 17.0, 49.0, 22.0], "flood_bbox": [51.0, 18.5, 49.8, 21.0]},
    {"name": "2013 Danube (Passau)",   "mech": "riverine", "peak": date(2013, 6, 3),  "fetch_area": [51.0, 10.0, 47.5, 15.0], "flood_bbox": [49.2, 12.8, 48.2, 14.2]},
    {"name": "2014 Sava (Balkans)",    "mech": "riverine", "peak": date(2014, 5, 16), "fetch_area": [46.5, 16.0, 43.5, 21.0], "flood_bbox": [45.3, 18.0, 44.4, 20.4]},
    {"name": "2016 Seine (Paris)",     "mech": "riverine", "peak": date(2016, 6, 1),  "fetch_area": [49.5, 1.0, 47.0, 4.5],   "flood_bbox": [49.0, 2.0, 48.3, 3.2]},
    {"name": "2021 Rhine/Ahr",         "mech": "flash",    "peak": date(2021, 7, 14), "fetch_area": [52.0, 5.0, 49.0, 9.0],   "flood_bbox": [50.9, 6.3, 50.2, 7.4]},
    {"name": "2024 Storm Boris",       "mech": "riverine", "peak": date(2024, 9, 15), "fetch_area": [51.0, 12.0, 48.0, 19.0], "flood_bbox": [50.6, 16.0, 49.4, 18.0]},
    # Second batch — wider geography (France, UK, Italy, Spain) for generalisation.
    {"name": "2002 Gard (France)",     "mech": "flash",    "peak": date(2002, 9, 9),  "fetch_area": [45.0, 3.0, 43.0, 5.5],   "flood_bbox": [44.3, 3.8, 43.6, 4.7]},
    {"name": "2007 England (Severn)",  "mech": "riverine", "peak": date(2007, 7, 21), "fetch_area": [53.5, -3.0, 51.0, 0.5],  "flood_bbox": [52.5, -2.5, 51.5, -1.2]},
    {"name": "2011 Genoa (Liguria)",   "mech": "flash",    "peak": date(2011, 11, 4), "fetch_area": [45.0, 7.5, 43.5, 10.0],  "flood_bbox": [44.6, 8.7, 44.3, 9.3]},
    {"name": "2013 Sardinia",          "mech": "flash",    "peak": date(2013, 11, 18),"fetch_area": [41.5, 8.0, 39.5, 10.0],  "flood_bbox": [41.0, 9.2, 40.5, 9.9]},
    {"name": "2019 Spain DANA",        "mech": "flash",    "peak": date(2019, 9, 13), "fetch_area": [39.5, -1.5, 37.5, 0.5],  "flood_bbox": [38.4, -1.0, 37.9, -0.5]},
    {"name": "2020 Storm Alex",        "mech": "flash",    "peak": date(2020, 10, 3), "fetch_area": [45.0, 6.5, 43.5, 8.0],   "flood_bbox": [44.2, 7.2, 43.8, 7.7]},
    {"name": "2023 Emilia-Romagna",    "mech": "riverine", "peak": date(2023, 5, 16), "fetch_area": [45.0, 10.5, 43.5, 13.0], "flood_bbox": [44.7, 11.2, 44.2, 12.3]},
    {"name": "2024 Valencia DANA",     "mech": "flash",    "peak": date(2024, 10, 29),"fetch_area": [40.0, -1.5, 38.5, 0.5],  "flood_bbox": [39.6, -0.9, 39.2, -0.2]},
]

FEATS = ["precipitation_7d_mm", "soil_saturation_index", "glofas_discharge_m3s"]


def build_dataset():
    """Incremental: load cache, fetch only events not already cached, append."""
    cached = pd.read_parquet(CACHE) if os.path.exists(CACHE) else pd.DataFrame()
    have = set(cached.event.unique()) if len(cached) else set()
    frames = [cached] if len(cached) else []
    for ev in EVENTS:
        if ev["name"] in have:
            continue
        print(f"• {ev['name']} ({ev['peak']}) — fetching ERA5 …", flush=True)
        try:
            ds = fetch(ev); df = features(ds, ev); ds.close()
        except Exception as e:
            print(f"   FAILED: {str(e)[:120]} — skipping"); continue
        df["event"] = ev["name"]
        print(f"   {len(df)} cells, {int(df.y.sum())} corridor cells, precip max {df.precipitation_7d_mm.max():.0f}mm")
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)
    os.makedirs("data", exist_ok=True)
    data.to_parquet(CACHE)
    print(f"cached {len(data)} rows across {data.event.nunique()} events → {CACHE}")
    return data


def leave_one_event_out(data):
    from ml.scoring.ensemble import EnsembleScorer
    events = list(data.event.unique())
    print(f"\n=== Leave-one-event-out backtest ({len(events)} events) ===\n")
    pooled_y, pooled_s = [], []
    for held in events:
        train = data[data.event != held]
        test = data[data.event == held]
        if test.y.sum() == 0 or train.y.sum() == 0:
            continue
        sc = EnsembleScorer(scale_pos_weight=10.0)
        sc.fit(train[FEATS].values, train.y.values.astype(int), feature_cols=FEATS)
        s = (sc.score_dataframe(test[FEATS].copy())["score"] / 100.0).values
        y = test.y.values.astype(int)
        auc = roc_auc_score(y, s) if len(np.unique(y)) > 1 else float("nan")
        ap = average_precision_score(y, s)
        print(f"  hold out {held:26s} AUC={auc:.3f}  AP={ap:.3f}  (base {y.mean():.3f})")
        pooled_y += y.tolist(); pooled_s += s.tolist()
    py, ps = np.array(pooled_y), np.array(pooled_s)
    print(f"\n  POOLED LOEO  ROC-AUC={roc_auc_score(py, ps):.3f}  "
          f"Avg-Precision={average_precision_score(py, ps):.3f}  base={py.mean():.3f}")
    print(f"\n  This is forecasting skill: each event scored by a model trained only on")
    print(f"  the OTHERS. AUC≈0.5 = no skill; meaningfully >0.5 = the model generalises.\n")


if __name__ == "__main__":
    data = build_dataset()
    leave_one_event_out(data)
