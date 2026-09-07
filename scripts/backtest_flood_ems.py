"""Flood backtest — ERA5-Land multi-event model vs Copernicus EMS OFFICIAL observed flood extents (independent).

NON-CIRCULAR by design on the INPUT side: the live flood model scores from ERA5-Land precipitation / soil
saturation / runoff only (ml/features/flood_era5.py). On the LABEL side it was trained on hand-drawn
"documented corridor" rectangles (scripts/build_multievent_flood.py). The target here is the EMS rapid-mapping
observedEventA polygons (scripts/fetch_ems_flood_footprints.py) — the official record of what actually flooded —
for every event that has an EMS activation (2013→). Each event is held out entirely (leave-one-event-out):
  A. train on the corridor labels the production model uses → judge the held-out event on the EMS extent
  B. train AND judge on EMS extents (EMS-era events only)
  reference: corridor-on-corridor over all 16 events (the previously reported LOEO)
Labels are at the panel's own resolution: an ERA5-Land 0.1° node is 'flooded' when the official extent
intersects its grid box. Ranking-family gate (AUC; rank ρ vs the ρ≥0.35 floor).
Run: PYTHONPATH=. .venv/bin/python scripts/backtest_flood_ems.py
"""
from __future__ import annotations

import json
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

from scripts.build_multievent_flood import EVENTS, FEATS
from scripts.fetch_ems_flood_footprints import slug

PANEL = "data/multievent_flood.parquet"
VAL = Path("data/flood_val")
GRID_HALF = 0.05
MIN_POS = 5


def ems_extent(ev: dict):
    p = VAL / f"ems_{slug(ev['name'])}.geojson"
    if not p.exists():
        return None, None
    from shapely.geometry import shape
    from shapely.ops import unary_union
    fc = json.load(p.open())
    return unary_union([shape(f["geometry"]).buffer(0) for f in fc["features"]]), fc


def label_nodes(cells: pd.Series, extent) -> np.ndarray:
    from shapely.geometry import box
    out = np.zeros(len(cells), dtype=int)
    for i, c in enumerate(cells):
        la, lo = h3.cell_to_latlng(c)
        out[i] = int(extent.intersects(box(lo - GRID_HALF, la - GRID_HALF, lo + GRID_HALF, la + GRID_HALF)))
    return out


def loeo(data: pd.DataFrame, train_col: str, test_col: str, title: str, test_events: set[str]) -> None:
    from ml.scoring.ensemble import EnsembleScorer
    print(f"\n=== {title} ===")
    py, ps = [], []
    for held in data.event.unique():
        if held not in test_events:
            continue
        tr, te = data[data.event != held], data[data.event == held]
        if train_col == "y_ems":
            tr = tr[tr.event.isin(test_events)]
        if te[test_col].sum() < MIN_POS or tr[train_col].sum() == 0:
            print(f"  hold out {held:28s} skipped ({int(te[test_col].sum())} positives < {MIN_POS})"); continue
        sc = EnsembleScorer(scale_pos_weight=10.0)
        sc.fit(tr[FEATS].values, tr[train_col].values.astype(int), feature_cols=FEATS)
        s = (sc.score_dataframe(te[FEATS].copy())["score"] / 100.0).values
        y = te[test_col].values.astype(int)
        print(f"  hold out {held:28s} AUC={roc_auc_score(y, s):.3f}  AP={average_precision_score(y, s):.3f}  "
              f"(base {y.mean():.3f}, n={len(y)})")
        py += y.tolist(); ps += s.tolist()
    if not py:
        print("  no event had enough EMS positives"); return
    py, ps = np.array(py), np.array(ps)
    rho, _ = spearmanr(ps, py)
    print(f"  POOLED LOEO  ROC-AUC={roc_auc_score(py, ps):.3f}  Avg-Precision={average_precision_score(py, ps):.3f}  "
          f"base={py.mean():.3f}  rank ρ={rho:.3f}")


def main() -> int:
    data = pd.read_parquet(PANEL).rename(columns={"y": "y_corridor"})
    data["y_ems"] = 0
    ems_events: set[str] = set()
    print("Label agreement per event (ERA5-Land 0.1° nodes; EMS = official extent intersects the node grid box):")
    for ev in EVENTS:
        ext, fc = ems_extent(ev)
        m = data.event == ev["name"]
        if ext is None or ext.is_empty or not m.any():
            print(f"  {ev['name']:28s} no EMS extent — corridor labels only"); continue
        data.loc[m, "y_ems"] = label_nodes(data.loc[m, "h3_cell"], ext)
        ems_events.add(ev["name"])
        c, e = set(data.loc[m & (data.y_corridor == 1), "h3_cell"]), set(data.loc[m & (data.y_ems == 1), "h3_cell"])
        print(f"  {ev['name']:28s} {fc['emsr']}  corridor-nodes {len(c):4d}  EMS-nodes {len(e):4d}  "
              f"overlap {len(c & e):4d}  Jaccard {len(c & e) / max(len(c | e), 1):.2f}  ({fc['flooded_km2']} km² mapped)")
    loeo(data, "y_corridor", "y_ems", "A. model trained on corridor labels, judged on held-out EMS observed extents", ems_events)
    loeo(data, "y_ems", "y_ems", "B. trained and judged on EMS observed extents (EMS-era events)", ems_events)
    loeo(data, "y_corridor", "y_corridor", "reference: corridor-on-corridor (the previously reported LOEO)", set(data.event.unique()))
    print("\nGate: RANKING family (ρ≥0.35 floor; AUC reported). Independent official target (Copernicus EMS observed "
          "flood extents), events held out entirely; inputs are ERA5-Land precipitation/soil/runoff only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
