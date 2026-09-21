"""Global flood validator — the JRC river-flood channel against the Global Flood Database (GFD) outside Europe.

PRE-REGISTERED DESIGN (fixed before any result was computed; no tuning afterwards):
  • Target: Global Flood Database v1.4 (Tellman et al. 2021, Nature 596:80–86; Cloud to Street / Dartmouth Flood Observatory),
    913 flood events 2000–2018, MODIS 250 m flood extents. Licence CC BY-NC 4.0 (README_GFD.pdf) — INTERNAL validation use only;
    the raw rasters are never redistributed or shipped (see data/flood_val/gfd/MANIFEST.md).
  • Observed, per event and 0.25° cell (cell edges at multiples of 0.25°; a 250 m pixel belongs to the cell holding its centre):
    FLOODED SHARE = flooded pixels / valid pixels, where a valid pixel has clear_views > 0 (MODIS actually saw the ground) and is
    not JRC permanent water (a lake or river channel is water, not flooded land — same rule as the predictor). A cell is observed
    only if valid pixels ≥ 50 % of the pixels a full cell holds; a cell outside the event map or under persistent cloud is
    unobserved, not dry. Share, not "touches" (the label lesson of flood_jrc.py). Across events a cell takes the MAX share
    (the worst observed 2000–2018 flood, the quantity a 1-in-100-year floodplain map is a proxy for; summing would reward
    cells merely covered by more event maps).
  • Predicted: the production flood score (ml.scoring.flood_jrc: share of the cell in the JRC RP100 floodplain × Huizinga depth–damage)
    on the same 0.25° box, read with the production TileReader (permanent water excluded). Cells with no complete JRC tile drop.
  • Strata: ml.validation.regional.macro_region of the cell centre (open ocean / Antarctica unassigned and dropped).
    At most PER_REGION_CAP cells per macro-region, fixed SEED, drawn before scoring (so drops from missing tiles are not selected on).
  • Test: `rank`, pooled Spearman ≥ 0.35 + monotone bands; per region judged by ml.validation.regional.stratified_report
    (n ≥ min_n, ρ ≥ 0.35). AUC at share > 2 % reported alongside per region. Europe is reported but is a different sample from the EMS
    test (different events, MODIS rather than EMS polygons).
Independence / overlap: the JRC maps are LISFLOOD hydrology + LISFLOOD-FP driven by reanalysis climatology and calibrated on river
discharge gauges; no GFD/MODIS extent enters them, and the depth–damage curve is a cited one, not fitted. What cannot be ruled out:
gauge calibration is not enumerated per event, and the forcing period overlaps 2000–2018. Neither is a use of the observed extents.
Known limits: MODIS 250 m sees large, long-lasting river/coastal/surge floods and misses flash and urban floods; the GFD includes
coastal and rain-driven floods the fluvial map does not model; cloud-limited events under-observe; GFD events are the DFO-catalogued
(news-reported) ones, biased toward damaging events.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

GFD_DIR = Path("data/flood_val/gfd")
ZIPS = GFD_DIR / "zips"
CELLS = GFD_DIR / "cell_share.parquet"          # derived cache (cell, max share, n events) — not the raw data
CELL_DEG = 0.25
MIN_COVERAGE = 0.5
PER_REGION_CAP = 800
SEED = 17
SHARE_EVENT_MIN = 0.02


def aggregate_block(flooded, views, water, lats, lons, cell: float = CELL_DEG) -> dict:
    """Per-cell (valid pixel count, flooded pixel count) for one raster block. `lats`/`lons` are the 1-D pixel-centre
    coordinates of the block's rows/cols. Valid = MODIS saw the ground (clear_views > 0), finite, not permanent water."""
    valid = np.isfinite(flooded) & np.isfinite(views) & (views > 0)
    valid &= ~(np.nan_to_num(water, nan=0.0) == 1)
    iy = np.floor(lats / cell).astype(np.int64)
    ix = np.floor(lons / cell).astype(np.int64)
    key = (iy[:, None] + 100000) * 1_000_000 + (ix[None, :] + 100000)
    fl = valid & (np.nan_to_num(flooded, nan=0.0) == 1)
    k = key[valid]
    if k.size == 0:
        return {}
    uk, inv = np.unique(k, return_inverse=True)
    nv = np.bincount(inv)
    nf = np.bincount(inv, weights=fl[valid].astype(float))
    return {(int(u // 1_000_000) - 100000, int(u % 1_000_000) - 100000): (int(a), int(b)) for u, a, b in zip(uk, nv, nf)}


def event_cells(zip_path: Path) -> dict:
    """{(iy, ix): flooded share} for the cells of one GFD event that are observed (coverage ≥ MIN_COVERAGE)."""
    import rasterio
    tif = next(n for n in zipfile.ZipFile(zip_path).namelist() if n.lower().endswith(".tif"))
    acc: dict = {}
    with rasterio.open(f"zip://{zip_path}!{tif}") as ds:
        names = {d: i + 1 for i, d in enumerate(ds.descriptions)}
        res = abs(ds.transform.a)
        full = (CELL_DEG / res) ** 2
        lons_all = ds.transform.c + (np.arange(ds.width) + 0.5) * ds.transform.a
        step = 512
        for r0 in range(0, ds.height, step):
            h = min(step, ds.height - r0)
            win = rasterio.windows.Window(0, r0, ds.width, h)
            fl, vw, wt = (ds.read(names[b], window=win).astype("float32") for b in ("flooded", "clear_views", "jrc_perm_water"))
            lats = ds.transform.f + (np.arange(r0, r0 + h) + 0.5) * ds.transform.e
            for kx, (a, b) in aggregate_block(fl, vw, wt, lats, lons_all).items():
                o = acc.get(kx, (0, 0))
                acc[kx] = (o[0] + a, o[1] + b)
    return {kx: b / a for kx, (a, b) in acc.items() if a >= MIN_COVERAGE * full}


def _event_worker(p: str) -> dict:
    return event_cells(Path(p))


def build_cells(workers: int = 6) -> pd.DataFrame:
    """Max flooded share per cell over all 913 events (cached). The cache is derived data, deterministic from the zips."""
    if CELLS.exists():
        return pd.read_parquet(CELLS)
    from multiprocessing import Pool
    zs = sorted(str(p) for p in ZIPS.glob("*.zip"))
    best: dict = {}
    cnt: dict = {}
    with Pool(workers) as pool:
        for d in pool.imap_unordered(_event_worker, zs):
            for kx, s in d.items():
                best[kx] = max(best.get(kx, 0.0), s)
                cnt[kx] = cnt.get(kx, 0) + 1
    df = pd.DataFrame([(iy, ix, s, cnt[(iy, ix)]) for (iy, ix), s in best.items()], columns=["iy", "ix", "share", "n_events"])
    df["lat"] = (df.iy + 0.5) * CELL_DEG
    df["lon"] = (df.ix + 0.5) * CELL_DEG
    df.to_parquet(CELLS)
    return df


def cap_per_region(df: pd.DataFrame, cap: int, seed: int) -> pd.DataFrame:
    """At most `cap` rows per region, seeded and order-stable (drawn before scoring)."""
    rng = np.random.default_rng(seed)
    parts = []
    for reg in sorted(df.region.unique()):
        m = df[df.region == reg].sort_values(["iy", "ix"])
        if len(m) > cap:
            m = m.iloc[np.sort(rng.choice(len(m), cap, replace=False))]
        parts.append(m)
    return pd.concat(parts) if parts else df


def _run(session: Session) -> ValidationResult:
    from shapely.geometry import box
    from sklearn.metrics import roc_auc_score
    from scipy.stats import spearmanr
    from ml.scoring.flood_jrc import TileReader, flood_score, tile_name
    from ml.validation.regional import macro_region

    if not ZIPS.exists() or not any(ZIPS.glob("*.zip")):
        return ValidationResult(hazard_type="flood", kind="rank", predicted=[], observed=[], labels=[],
                                target_source="Global Flood Database v1.4 (MODIS)", scope="global_gfd", method="out_of_sample",
                                notes=f"{ZIPS} not present — see data/flood_val/gfd/MANIFEST.md")
    df = build_cells()
    df["region"] = [macro_region(la, lo) for la, lo in zip(df.lat, df.lon)]
    df = cap_per_region(df.dropna(subset=["region"]), PER_REGION_CAP, SEED)
    pred, obs, strata, labels = [], [], [], []
    readers: dict = {}
    h = CELL_DEG / 2
    for r in df.itertuples():
        name = tile_name(r.lat, r.lon)
        if name is None:
            continue
        if name not in readers:
            readers[name] = TileReader(name)
        rd = readers[name]
        st = rd.polygon_stats(box(r.lon - h, r.lat - h, r.lon + h, r.lat + h)) if rd.complete() else None
        if st is None:
            continue
        pred.append(flood_score(*st[100][:2])); obs.append(float(r.share)); strata.append(r.region)
        labels.append(f"{r.region} {r.lat:.3f},{r.lon:.3f} ev{r.n_events}")
    for rd in readers.values():
        rd.close()
    p, o, s = np.asarray(pred), np.asarray(obs), np.asarray(strata, dtype=object)
    per = {}
    for reg in sorted(set(s)):
        m = s == reg
        y = o[m] > SHARE_EVENT_MIN
        per[reg] = {"n": int(m.sum()), "rho": round(float(spearmanr(p[m], o[m])[0]), 3) if m.sum() > 2 else None,
                    "auc_share_gt_2pct": round(float(roc_auc_score(y, p[m])), 3) if 0 < y.sum() < len(y) else None,
                    "share_gt_2pct": round(float(y.mean()), 3)}
    return ValidationResult(
        hazard_type="flood", kind="rank", predicted=pred, observed=obs, labels=labels, strata=strata,
        target_source="Global Flood Database v1.4 (MODIS, 913 events 2000–2018; CC BY-NC, internal): max flooded share per 0.25° cell",
        scope="global_gfd", method="out_of_sample", data_vintage="JRC flood hazard maps v2.1.2 (RP100) vs GFD v1.4",
        notes=(f"per-region {per}. Predictor: production JRC v3 score on the 0.25° box; observed: max over events of flooded share of "
               "MODIS-valid land pixels; cells capped per region (seeded). MODIS misses flash/urban floods; GFD includes coastal/pluvial "
               "floods the fluvial map does not model; no GFD data enters the maps (gauge calibration/forcing-period overlap not enumerable)."),
        extra={"per_region": per})


register("flood_gfd_global")(_run)
