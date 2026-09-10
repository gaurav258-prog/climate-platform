"""Flood validator — the JRC river-flood channel (v3) against Copernicus EMS OFFICIAL observed flood extents.

Target: EMS rapid-mapping observed-event polygons for the six EMS-era events in the flood panel (2019 Spain DANA,
2020 Storm Alex, 2021 Rhine/Ahr, 2023 Emilia-Romagna, 2024 Storm Boris, 2024 Valencia DANA), at the panel's own
0.1° node grid: the observed quantity is the SHARE of each node box inside the mapped flooded extent (a binary
"touches" label made every box near a stream a positive and scored 0.16; the share is the quantity the map predicts).
Nodes inside the event box AND the mapped area only — outside the mapped area a node is unobserved, not dry. The JRC maps are a
hydrological/hydrodynamic model driven by reanalysis climatology — no EMS extent enters them — so every event is
out of sample. Predictor: the v3 cell statistic on the node box (share of the box in the 1-in-100-year floodplain ×
depth–damage fraction). Pooled over events: `rank` kind (Spearman ≥ 0.35 + monotone bands); AUC at share > 2 % reported alongside.
Flash-flood events (DANA, Storm Alex) are a fair test of the map's limit, not of its river skill; they stay in.
"""
from __future__ import annotations

from pathlib import Path

import h3
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from sqlalchemy.orm import Session

from ml.scoring.flood_jrc import TileReader, flood_score, tile_name
from services.validation.engine import ValidationResult, register

PANEL = Path("data/multievent_flood.parquet")
GRID_HALF = 0.05


def _run(session: Session) -> ValidationResult:
    from shapely.geometry import box

    from scripts.backtest_flood_ems import EVENTS, ems_extent
    if not PANEL.exists():
        return ValidationResult(hazard_type="flood", kind="rank", predicted=[], observed=[], labels=[],
                                target_source="Copernicus EMS observed flood extents", scope="Europe", method="out_of_sample",
                                notes=f"{PANEL} not present — run scripts/build_multievent_flood.py and scripts/fetch_ems_flood_footprints.py")
    data = pd.read_parquet(PANEL)
    pred, obs, labels, per_event = [], [], [], {}
    readers: dict = {}
    for ev in EVENTS:
        ext, fc = ems_extent(ev)
        m = data.event == ev["name"]
        if ext is None or ext.is_empty or not m.any():
            continue
        n, w, s_, e = ev["flood_bbox"]
        hull = ext.convex_hull                      # the mapped area: outside it a node is unobserved, not dry
        p, o = [], []
        for c in data.loc[m, "h3_cell"].drop_duplicates():
            la, lo = h3.cell_to_latlng(c)
            if not (s_ <= la <= n and w <= lo <= e):
                continue
            b = box(lo - GRID_HALF, la - GRID_HALF, lo + GRID_HALF, la + GRID_HALF)
            if not hull.intersects(b):
                continue
            name = tile_name(la, lo)
            if name not in readers:
                readers[name] = TileReader(name) if name else None
            r = readers[name]
            st = r.polygon_stats(b) if r and r.complete() else None
            if st is None:
                continue
            p.append(flood_score(*st[100][:2])); o.append(float(ext.intersection(b).area / b.area)); labels.append(f"{ev['name']} {c}")
        if len(p) >= 10:
            y = np.asarray(o) > 0.02
            per_event[ev["name"]] = {"n": len(p), "rho": round(float(spearmanr(p, o)[0]), 3),
                                     "auc_share_gt_2pct": round(float(roc_auc_score(y, p)), 3) if 0 < y.sum() < len(y) else None}
        pred += p; obs += o
    for r in readers.values():
        if r:
            r.close()
    y = np.asarray(obs) > 0.02
    return ValidationResult(hazard_type="flood", kind="rank", predicted=pred, observed=obs, labels=labels,
                            target_source="Copernicus EMS rapid-mapping observed flood extents (official), six events 2019–2024: share of each 0.1° node flooded",
                            scope="Europe", method="out_of_sample", data_vintage="JRC flood hazard maps v2.1.2 (RP100) vs EMS 2019–2024",
                            notes=(f"per-event {per_event}; pooled AUC(share>2%) {round(float(roc_auc_score(y, pred)), 3) if 0 < y.sum() < len(y) else None}. "
                                   "Predictor: share of the node box in the 1-in-100-year floodplain × depth–damage; observed: share of the box inside the "
                                   "EMS flooded extent; nodes inside the event box and the mapped area only (outside the mapped area a node is unobserved). "
                                   "No EMS data enters the maps; flash-flood events (Ahr, Alex, the two DANAs) are the fluvial map's limit and stay in"),
                            extra={"per_event": per_event})


register("flood_jrc_ems")(_run)
