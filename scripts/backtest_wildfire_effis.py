"""Wildfire backtest — ERA5-Land fire-weather/fuel model vs EFFIS OFFICIAL burnt-area polygons (independent).

NON-CIRCULAR by design on the INPUT side: the live wildfire model scores from ERA5-Land fire weather + fuel only
(wind, RH, days-since-rain, LAI, soil water — ml/features/wildfire_era5.py); no fire detection is an input.
On the LABEL side, the model was trained on VIIRS active-fire hotspots (FIRMS). The target here is different:
the JRC/EFFIS burnt-area MAPPING (burn scars delineated from MODIS imagery, scripts/fetch_effis_burnt_area.py) —
the official European record of what actually burned. We hold each event out ENTIRELY (leave-one-event-out):
the fold's model never sees that fire, under either label. Two runs:
  A. train on the FIRMS labels the production model uses → test the held-out event against EFFIS burn scars
     (the model as built, judged by the official record)
  B. train AND test on EFFIS labels (does the official record change the learned relationship?)
Plus the label agreement itself (FIRMS hotspot cells vs EFFIS scar cells) so the two views are comparable.
Ranking-family gate (AUC, plus rank ρ vs the ρ≥0.35 floor). Run: PYTHONPATH=. .venv/bin/python scripts/backtest_wildfire_effis.py
"""
from __future__ import annotations

import json
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

from scripts.build_multievent_wildfire import EVENTS, FEATS
from scripts.fetch_effis_burnt_area import slug

PANEL = "data/multievent_wildfire_fuel.parquet"
VAL = Path("data/wildfire_val")
H3_RES = 8
GRID_HALF = 0.05          # half of the ERA5-Land 0.1° grid spacing
MIN_POS = 5


def effis_scar(ev: dict):
    """Union of the event's EFFIS burn-scar polygons (shapely), or None if not fetched."""
    p = VAL / f"effis_{slug(ev['name'])}.geojson"
    if not p.exists():
        return None
    from shapely.geometry import shape
    from shapely.ops import unary_union
    return unary_union([shape(f["geometry"]).buffer(0) for f in json.load(p.open())["features"]])


def label_nodes(cells: pd.Series, scar) -> np.ndarray:
    """The panel is the ERA5-Land 0.1° node grid (one H3 res-8 cell per node), so a node is 'burned' when the
    official scar intersects the node's 0.1° grid box — the same footprint the node's weather/fuel values stand for.
    Testing only the ~0.7 km² node cell itself would miss almost every scar at this resolution."""
    from shapely.geometry import box
    out = np.zeros(len(cells), dtype=int)
    for i, c in enumerate(cells):
        la, lo = h3.cell_to_latlng(c)
        out[i] = int(scar.intersects(box(lo - GRID_HALF, la - GRID_HALF, lo + GRID_HALF, la + GRID_HALF)))
    return out


def loeo(data: pd.DataFrame, train_col: str, test_col: str, title: str) -> None:
    from ml.scoring.ensemble import EnsembleScorer
    print(f"\n=== {title} ===")
    py, ps = [], []
    for held in data.event.unique():
        tr, te = data[data.event != held], data[data.event == held]
        if te[test_col].sum() < MIN_POS or tr[train_col].sum() == 0:
            print(f"  hold out {held:30s} skipped ({int(te[test_col].sum())} positives < {MIN_POS})")
            continue
        sc = EnsembleScorer(scale_pos_weight=8.0)
        sc.fit(tr[FEATS].values, tr[train_col].values.astype(int), feature_cols=FEATS)
        s = (sc.score_dataframe(te[FEATS].copy())["score"] / 100.0).values
        y = te[test_col].values.astype(int)
        print(f"  hold out {held:30s} AUC={roc_auc_score(y, s):.3f}  AP={average_precision_score(y, s):.3f}  "
              f"(base {y.mean():.3f}, n={len(y)})")
        py += y.tolist(); ps += s.tolist()
    py, ps = np.array(py), np.array(ps)
    rho, _ = spearmanr(ps, py)
    print(f"  POOLED LOEO  ROC-AUC={roc_auc_score(py, ps):.3f}  Avg-Precision={average_precision_score(py, ps):.3f}  "
          f"base={py.mean():.3f}  rank ρ={rho:.3f}")


def main() -> int:
    data = pd.read_parquet(PANEL).rename(columns={"y": "y_firms"})
    data["y_effis"] = 0
    print("Label agreement per event (ERA5-Land 0.1° nodes; EFFIS = scar intersects the node grid box):")
    for ev in EVENTS:
        scar = effis_scar(ev)
        m = data.event == ev["name"]
        if scar is None or scar.is_empty or not m.any():
            print(f"  {ev['name']:30s} no EFFIS scar / no panel — skipped"); continue
        data.loc[m, "y_effis"] = label_nodes(data.loc[m, "h3_cell"], scar)
        f, e = set(data.loc[m & (data.y_firms == 1), "h3_cell"]), set(data.loc[m & (data.y_effis == 1), "h3_cell"])
        j = len(f & e) / max(len(f | e), 1)
        print(f"  {ev['name']:30s} FIRMS-cells {len(f):4d}  EFFIS-cells {len(e):4d}  overlap {len(f & e):4d}  Jaccard {j:.2f}")
    loeo(data, "y_firms", "y_effis", "A. model trained on FIRMS hotspots, judged on held-out EFFIS burn scars")
    loeo(data, "y_effis", "y_effis", "B. trained and judged on EFFIS burn scars")
    loeo(data, "y_firms", "y_firms", "reference: FIRMS-on-FIRMS (the previously reported LOEO)")
    print("\nGate: RANKING family (ρ≥0.35 floor; AUC reported). Independent official target (EFFIS burnt-area "
          "mapping), events held out entirely; inputs are ERA5-Land weather/fuel only (no fire detection).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
