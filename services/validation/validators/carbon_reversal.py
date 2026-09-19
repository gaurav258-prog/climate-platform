"""Carbon-credit reversal PILOT validator — our wildfire score at forest-project boundaries vs observed subsequent forest loss.

PRE-REGISTERED DESIGN (fixed before any number was computed; no tuning, one run).
Cohort: Berkeley VROD v2026-06 forestry-scope projects with credits issued > 0 and a first issuance year <= 2020, that have a
boundary in Karnik et al. (Zenodo 11459391, project geometry) or CARB/CarbonPlan (California) AND whose whole footprint lies
inside pulled Hansen tiles (Amazon, Congo, SE Asia, boreal N. America, western US). Outside those tiles: excluded, counted.
Predictor: production wildfire climatology (ml.scoring.wildfire_climatology, PRODUCTION_VARIANT with_history) at the boundary
centroid; the fully burn-independent `weather_fuel` variant is reported alongside. No re-fitting, no re-weighting.
Outcome (test a): share of the project polygon whose Hansen GFC 2024 v1.12 lossyear is 2021-2024 (post-issuance for every
project, loss share = loss pixels / all pixels in polygon; treecover2000 is not on disk, so non-forest pixels stay in the
denominator). Hansen loss is ALL stand-replacing loss (fire + clearing + logging); the WRI driver layer was not used
(band semantics unverified), so this is an upper-bound proxy for fire reversal, disclosed. Polygon read at a decimated grid
(<= 3000 px on the long side, nearest) for very large projects.
Metric: Spearman rho, kind `rank`, pooled and per macro-region (VROD Region); regions with n < 10 are not scored.
Test (b): projects with a CARB wildfire reversal-risk rating: Spearman + Kendall tau-b of our score vs the rating, and mean
score by rating group. Descriptive, ordinal, ties are heavy (most ratings are 0.04); not a pass/fail gate.
Overlap statement: score inputs are FWI 2006-2020 and burned-area history 2001-2019; outcome years 2021-2024 do NOT overlap
the score-building years (no leakage). Caveats: 2021-2024 is a short window; project boundary vintages differ; the score is
0.25 degree, coarse against small polygons; Verra/Gold Standard data were not used.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

ROOT = Path(__file__).resolve().parents[3]
VROD = ROOT / "data/carbon_val/berkeley_vrod/vrod_v2026-06_projects.csv"
KARNIK = ROOT / "data/carbon_val/karnik_boundaries"
CARB_DIR = ROOT / "data/carbon_val/carb_ca_forest/carb-forest-offset-boundaries/boundaries"
CARB_RATINGS = ROOT / "data/carbon_val/carb_ca_forest/carb-wildfire-risk-ratings.json"
HANSEN = ROOT / "data/reversal_val/hansen_gfc_2024"
LOSS_YEARS = (2021, 2024)          # inclusive, calendar years
MAX_PX = 3000
MIN_N_REGION = 10


# ── pure helpers ────────────────────────────────────────────────────────────────────────────────────────
def tile_name(lat: float, lon: float) -> str:
    """Hansen 10-degree tile named by its upper-left corner, e.g. 00N_010E, 20S_060W."""
    top = int(np.ceil(lat / 10.0) * 10)
    left = int(np.floor(lon / 10.0) * 10)
    return f"{abs(top):02d}{'N' if top >= 0 else 'S'}_{abs(left):03d}{'E' if left >= 0 else 'W'}"


def tiles_for_bounds(minx: float, miny: float, maxx: float, maxy: float) -> list:
    out = []
    for la in np.arange(np.floor(miny / 10) * 10, maxy + 1e-9, 10.0):
        for lo in np.arange(np.floor(minx / 10) * 10, maxx + 1e-9, 10.0):
            n = tile_name(la + 5.0, lo + 5.0)
            if n not in out:
                out.append(n)
    return out


def loss_counts(lossyear: np.ndarray, mask: np.ndarray, y0: int = LOSS_YEARS[0], y1: int = LOSS_YEARS[1]) -> tuple:
    """(loss pixels with year in [y0,y1], pixels in mask). lossyear coding: 0 none, 1..24 = 2001..2024."""
    m = mask.astype(bool)
    ly = lossyear[m]
    return int(((ly >= y0 - 2000) & (ly <= y1 - 2000)).sum()), int(m.sum())


def safe_spearman(x, y) -> Optional[float]:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    return round(float(spearmanr(x, y)[0]), 3)


def by_stratum(pred, obs, strata, min_n: int = MIN_N_REGION) -> dict:
    out = {}
    for s in sorted(set(strata)):
        idx = [i for i, t in enumerate(strata) if t == s]
        out[s] = {"n": len(idx), "rho": safe_spearman([pred[i] for i in idx], [obs[i] for i in idx]) if len(idx) >= min_n else None}
    return out


def carb_agreement(score, rating) -> dict:
    score, rating = np.asarray(score, float), np.asarray(rating, float)
    if len(score) < 3 or np.ptp(rating) == 0 or np.ptp(score) == 0:
        return {"n": int(len(score)), "spearman": None, "kendall_tau_b": None}
    return {"n": int(len(score)), "spearman": round(float(spearmanr(score, rating)[0]), 3),
            "kendall_tau_b": round(float(kendalltau(score, rating)[0]), 3),
            "mean_score_by_rating": {str(r): round(float(score[rating == r].mean()), 1) for r in sorted(set(rating))},
            "n_by_rating": {str(r): int((rating == r).sum()) for r in sorted(set(rating))}}


# ── data ────────────────────────────────────────────────────────────────────────────────────────────────
def load_cohort() -> pd.DataFrame:
    v = pd.read_csv(VROD, low_memory=False)
    v = v[v["Scope"] == "Forestry & Land Use"].copy()
    v["issued"] = pd.to_numeric(v["Total Credits  Issued"], errors="coerce").fillna(0)
    yrs = [str(y) for y in range(1996, 2027)]
    iss = v[yrs].apply(pd.to_numeric, errors="coerce").fillna(0)
    first = iss.gt(0).idxmax(axis=1).astype(float).where(iss.gt(0).any(axis=1))
    v["first_issuance"] = first
    v = v[(v.issued > 0) & (v.first_issuance <= 2020)]
    return v[["Project ID", "Region", "Country", "first_issuance", "issued"]].rename(columns={"Project ID": "pid"})


def load_geometries() -> dict:
    import geopandas as gpd
    geoms = {}
    for f in sorted(KARNIK.glob("*.gpkg")):
        g = gpd.read_file(f)
        for pid, geom in zip(g["ProjectID"], g.geometry):
            if geom is not None and not geom.is_empty:
                geoms.setdefault(str(pid), geom)
    for d in ("active", "listed"):
        for f in (CARB_DIR / d).glob("*.json"):
            pid = f.stem
            if pid in geoms:
                continue
            g = gpd.read_file(f)
            if len(g):
                geoms[pid] = g.geometry.union_all() if hasattr(g.geometry, "union_all") else g.geometry.unary_union
    return geoms


def hansen_loss_share(geom) -> Optional[dict]:
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds
    from shapely.geometry import mapping
    minx, miny, maxx, maxy = geom.bounds
    loss = tot = 0
    for t in tiles_for_bounds(minx, miny, maxx, maxy):
        p = HANSEN / f"Hansen_GFC-2024-v1.12_lossyear_{t}.tif"
        if not p.exists():
            return None
    for t in tiles_for_bounds(minx, miny, maxx, maxy):
        with rasterio.open(HANSEN / f"Hansen_GFC-2024-v1.12_lossyear_{t}.tif") as ds:
            b = ds.bounds
            gx0, gy0, gx1, gy1 = max(minx, b.left), max(miny, b.bottom), min(maxx, b.right), min(maxy, b.top)
            if gx0 >= gx1 or gy0 >= gy1:
                continue
            w = from_bounds(gx0, gy0, gx1, gy1, ds.transform).round_offsets().round_lengths()
            w = Window(w.col_off, w.row_off, max(w.width, 1), max(w.height, 1))
            f = max(1.0, max(w.width, w.height) / MAX_PX)
            oh, ow = max(1, int(w.height / f)), max(1, int(w.width / f))
            arr = ds.read(1, window=w, out_shape=(oh, ow), resampling=rasterio.enums.Resampling.nearest)
            tr = ds.window_transform(w) * rasterio.Affine.scale(w.width / ow, w.height / oh)
            mask = ~geometry_mask([mapping(geom)], out_shape=arr.shape, transform=tr, all_touched=False)
            l, n = loss_counts(arr, mask)
            loss += l; tot += n
    return {"share": loss / tot, "px": tot} if tot > 0 else None


def _run(session: Session) -> ValidationResult:
    from ml.scoring.wildfire_climatology import score_point_pure
    cohort, geoms = load_cohort(), load_geometries()
    ratings = json.loads(CARB_RATINGS.read_text())
    rows, excl = [], {"no_geometry": 0, "outside_hansen_tiles": 0, "no_score": 0}
    for r in cohort.itertuples():
        g = geoms.get(r.pid)
        if g is None:
            excl["no_geometry"] += 1; continue
        c = g.centroid
        s = score_point_pure(c.y, c.x, "with_history"); s2 = score_point_pure(c.y, c.x, "weather_fuel")
        if s is None or s2 is None:
            excl["no_score"] += 1; continue
        h = hansen_loss_share(g)
        rows.append({"pid": r.pid, "region": r.Region, "score": s["score"], "score_wf": s2["score"],
                     "loss": None if h is None else h["share"]})
        if h is None:
            excl["outside_hansen_tiles"] += 1
    df = pd.DataFrame(rows)
    a = df.dropna(subset=["loss"])
    pred, obs, strata = a.score.tolist(), a.loss.tolist(), a.region.tolist()
    reg = by_stratum(pred, obs, strata)
    rho_wf = safe_spearman(a.score_wf, a.loss)
    cb = df[df.pid.isin(ratings)]
    agree = carb_agreement(cb.score, [ratings[p] for p in cb.pid])
    agree_wf = carb_agreement(cb.score_wf, [ratings[p] for p in cb.pid])
    return ValidationResult(
        hazard_type="carbon_reversal", kind="rank", predicted=pred, observed=obs, labels=a.pid.tolist(), strata=strata,
        target_source="Hansen GFC 2024 v1.12 loss share 2021-2024 inside project boundaries (Karnik/CARB), Berkeley VROD cohort",
        scope="forest carbon projects in pulled Hansen tiles", method="temporal_holdout",
        data_vintage="wildfire-climatology-v1 (FWI 2006-2020, BA 2001-2019) vs Hansen loss 2021-2024; no year overlap",
        notes=(f"PILOT. n={len(a)}; pooled rho {safe_spearman(pred, obs)}; weather_fuel rho {rho_wf}; per-region {reg}; excluded {excl}; "
               f"CARB agreement (with_history) {agree}; (weather_fuel) {agree_wf}. Outcome is all forest loss, not fire only."),
        extra={"per_region": reg, "carb_agreement": agree, "carb_agreement_weather_fuel": agree_wf, "excluded": excl,
               "rho_weather_fuel": rho_wf})


register("carbon_reversal_wildfire_pilot")(_run)
