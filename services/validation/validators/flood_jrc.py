"""Flood validator — the JRC river-flood channel (v3) against Copernicus EMS OFFICIAL observed flood extents.

Target: EMS rapid-mapping observed-event polygons for the six EMS-era events in the flood panel (2019 Spain DANA,
2020 Storm Alex, 2021 Rhine/Ahr, 2023 Emilia-Romagna, 2024 Storm Boris, 2024 Valencia DANA), at the panel's own
0.1° node grid: the observed quantity is the SHARE of each node box's mapped part inside the flooded extent (a binary
"touches" label made every box near a stream a positive and scored 0.16; the share is the quantity the map predicts).
Nodes inside the event box with at least half the box inside the area EMS mapped (the union of its products' own
outlines, E172) — outside the mapped area a node is unobserved, not dry. The JRC maps are a
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

from ml.scoring.flood_jrc import TileSet, flood_score
from services.validation.engine import ValidationResult, register

PANEL = Path("data/multievent_flood.parquet")
GRID_HALF = 0.05
MAPPED_MIN = 0.5      # a node is judged when at least half its box lies in the mapped area (the rest was not observed)


def event_nodes(cells: pd.Series, ev: dict, mapped):
    """(h3 cell, node box) for every panel node of one event that the observation can judge: inside the event box and
    inside the area EMS mapped — the union of its products' own outlines (E172; not the observed polygons' convex hull,
    which spans the unmapped land between activations). Outside the mapped area a node is unobserved, not dry. Shared
    with the 30 m refinement's test (services/loss/refine30.py), so both are judged on the same nodes."""
    from shapely.geometry import box
    n, w, s_, e = ev["flood_bbox"]
    for c in cells.drop_duplicates():
        la, lo = h3.cell_to_latlng(c)
        if not (s_ <= la <= n and w <= lo <= e):
            continue
        b = box(lo - GRID_HALF, la - GRID_HALF, lo + GRID_HALF, la + GRID_HALF)
        if mapped.intersection(b).area >= MAPPED_MIN * b.area:
            yield c, b


def observed_share(ext, mapped, b) -> float:
    """The share of a node's MAPPED part that EMS observed flooded — what was looked at, not the whole box."""
    seen = mapped.intersection(b).area
    return float(ext.intersection(b).intersection(mapped).area / seen) if seen else 0.0


def _run(session: Session) -> ValidationResult:
    from scripts.backtest_flood_ems import EVENTS, ems_extent, ems_mapped
    if not PANEL.exists():
        return ValidationResult(hazard_type="flood", kind="rank", predicted=[], observed=[], labels=[],
                                target_source="Copernicus EMS observed flood extents", scope="Europe", method="out_of_sample",
                                notes=f"{PANEL} not present — run scripts/build_multievent_flood.py and scripts/fetch_ems_flood_footprints.py")
    data = pd.read_parquet(PANEL)
    pred, obs, labels, per_event = [], [], [], {}
    tiles = TileSet()
    for ev in EVENTS:
        ext, fc = ems_extent(ev)
        mapped = ems_mapped(ev)
        m = data.event == ev["name"]
        if ext is None or ext.is_empty or mapped is None or not m.any():
            continue
        p, o = [], []
        for c, b in event_nodes(data.loc[m, "h3_cell"], ev, mapped):
            st = tiles.stats(b)                     # read from every tile the node touches
            if st is None:
                continue
            p.append(flood_score(*st[100][:2])); o.append(observed_share(ext, mapped, b)); labels.append(f"{ev['name']} {c}")
        if len(p) >= 10:
            y = np.asarray(o) > 0.02
            per_event[ev["name"]] = {"n": len(p), "rho": round(float(spearmanr(p, o)[0]), 3),
                                     "auc_share_gt_2pct": round(float(roc_auc_score(y, p)), 3) if 0 < y.sum() < len(y) else None}
        pred += p; obs += o
    tiles.close()
    y = np.asarray(obs) > 0.02
    return ValidationResult(hazard_type="flood", kind="rank", predicted=pred, observed=obs, labels=labels,
                            target_source="Copernicus EMS rapid-mapping observed flood extents (official), six events 2019–2024: share of each 0.1° node flooded",
                            scope="Europe", method="out_of_sample", data_vintage="JRC flood hazard maps v2.1.2 (RP100) vs EMS 2019–2024",
                            notes=(f"per-event {per_event}; pooled AUC(share>2%) {round(float(roc_auc_score(y, pred)), 3) if 0 < y.sum() < len(y) else None}. "
                                   "Predictor: share of the node box in the 1-in-100-year floodplain × depth–damage; observed: share of the box's mapped part "
                                   "inside the EMS flooded extent; nodes inside the event box with at least half the box in the area EMS mapped (the union "
                                   "of its accepted products' outlines; a layer listed under another activation is refused — E172). "
                                   "No EMS data enters the maps; flash-flood events (Ahr, Alex, the two DANAs) are the fluvial map's limit and stay in"),
                            extra={"per_event": per_event})


register("flood_jrc_ems")(_run)
