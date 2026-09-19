"""Wildfire validator beyond Europe — US, Canada and global macro-regions, on held-out burned area.

PRE-REGISTERED DESIGN (written before any number was computed; no tuning afterwards).

Predicted: the PRODUCTION wildfire score, `ml.scoring.wildfire_climatology.score_point_pure(lat, lon,
PRODUCTION_VARIANT)['score']`, at the centre of each 0.5° cell. Cells with burnable_fraction < 0.2 are dropped
(same mask as scripts/backtest_wildfire_climatology.py) — the score is 0 there by construction.

Held-out period (temporal overlap, disclosed): the climatology used fire weather 2006-2020 and burn history
2001-2019 (C3S/ESA-CCI Fire MODIS product). Every target below uses 2021 onward ONLY, so no year of the target
was seen by the score. 2020 is excluded from targets although the FWI term covers it.
  US      MTBS perimeters (fires igniting 2021-2024, wildfire types only) and NIFC interagency perimeters
          (FIRE_YEAR_INT 2021-2024, 'Wildfire' features) — two runs; strata CONUS / Alaska.
  Canada  NFDB polygons YEAR 2021-2024; strata south (<55N) / north (>=55N).
  Global  GFED5.1 ecosystem-file burned_area 2021-2022 (Wageningen; independent of the ESA-CCI product used in the
          history term) and ESA FireCCI51 grid 2021-2022 (SAME MODIS product family as the history term, later
          years only -> partly non-independent, weaker evidence). Strata = ml.validation.regional.macro_region.
          GFED5 published burned-area ends 2022 in the files on disk (BA.zip ends 2020), hence only 2 held-out years.

Target per cell: burned area in the held-out period / cell land-plus-water area (fraction; zeros kept). Perimeter
fires are assigned WHOLE to the cell holding their centroid (very large fires overstate one cell; disclosed).
Gridded targets are summed from 0.25° to 0.5°.

Test: Spearman rho of score vs burned fraction over burnable cells of the region (kind 'rank', the wildfire/EFFIS
magnitude convention). Gate: rho >= RANK_GATE_SPEARMAN (0.35), per-stratum floor REGION_PASS_SPEARMAN, sample floor
MIN_N_REGION_CLAIM, band monotonicity reported (M.band_monotone). Also reported (not gated): occurrence ROC-AUC of
burned>0. Verdict by the engine's _compute; no threshold or weight was adjusted after seeing results.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

import numpy as np

from services.validation.engine import ValidationResult, register

RES = 0.5
MIN_BURNABLE = 0.2
HELD_OUT_FROM = 2021
EARTH_R_M = 6_371_008.8
ROOT = Path(__file__).resolve().parents[3]
RV = ROOT / "data" / "reversal_val"


# ── pure helpers ─────────────────────────────────────────────────────────────────────────────────────────
def cell_index(lat, lon, res: float = RES):
    """(i, j) of the res-degree cell containing each point; lon wrapped into [-180, 180)."""
    lat = np.asarray(lat, float)
    lon = ((np.asarray(lon, float) + 180.0) % 360.0) - 180.0
    n_lat, n_lon = int(round(180 / res)), int(round(360 / res))
    i = np.clip(np.floor((lat + 90.0) / res).astype(int), 0, n_lat - 1)
    j = np.clip(np.floor((lon + 180.0) / res).astype(int), 0, n_lon - 1)
    return i, j


def cell_centre(i, j, res: float = RES):
    return -90.0 + res * (np.asarray(i) + 0.5), -180.0 + res * (np.asarray(j) + 0.5)


def cell_area_ha(i, res: float = RES):
    """Spherical area of a res-degree cell in hectares (depends on latitude row only)."""
    i = np.asarray(i, float)
    lo, hi = np.radians(-90.0 + res * i), np.radians(-90.0 + res * (i + 1))
    return EARTH_R_M ** 2 * np.radians(res) * (np.sin(hi) - np.sin(lo)) / 1e4


def aggregate_points(lat, lon, ha, res: float = RES) -> dict:
    """Sum burned hectares per cell from point-assigned fires -> {(i, j): ha}."""
    i, j = cell_index(lat, lon, res)
    out: dict = {}
    for a, b, h in zip(i.tolist(), j.tolist(), np.asarray(ha, float).tolist()):
        if h > 0 and math.isfinite(h):
            out[(a, b)] = out.get((a, b), 0.0) + h
    return out


def aggregate_grid(values_m2: np.ndarray, lat: np.ndarray, lon: np.ndarray, res: float = RES) -> np.ndarray:
    """Sum a finer lat/lon grid of burned area (m2) into res-degree cells -> ha array [n_lat, n_lon]."""
    v = np.nan_to_num(np.asarray(values_m2, float), nan=0.0)
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    i, j = cell_index(la.ravel(), lo.ravel(), res)
    out = np.zeros((int(round(180 / res)), int(round(360 / res))))
    np.add.at(out, (i, j), v.ravel() / 1e4)
    return out


def burned_fraction(ha: float, area_ha: float) -> float:
    return float(min(max(ha / area_ha, 0.0), 1.0)) if area_ha > 0 else 0.0


def score_cells(i_arr, j_arr) -> tuple[list[int], list[float]]:
    """Production score at each cell centre; returns (kept positions, scores) for burnable cells only."""
    from ml.scoring.wildfire_climatology import PRODUCTION_VARIANT, score_point_pure
    la, lo = cell_centre(i_arr, j_arr)
    keep, sc = [], []
    for k, (a, b) in enumerate(zip(la.tolist(), lo.tolist())):
        r = score_point_pure(a, b, PRODUCTION_VARIANT)
        if r is not None and r["burnable_fraction"] >= MIN_BURNABLE:
            keep.append(k)
            sc.append(float(r["score"]))
    return keep, sc


def auc_occurrence(pred, obs) -> Optional[float]:
    from sklearn.metrics import roc_auc_score
    y = (np.asarray(obs, float) > 0).astype(int)
    return float(roc_auc_score(y, pred)) if 0 < y.sum() < len(y) else None


def country_mask(lat, lon, iso: str) -> np.ndarray:
    """True where the point lies inside (or within 0.5 deg of) the ISO-2 country polygon."""
    from shapely.geometry import Point
    from ml.validation.regional import _index
    tree, geoms, isos = _index()
    out = []
    for a, b in zip(np.asarray(lat).tolist(), np.asarray(lon).tolist()):
        pt = Point(b, a)
        hit = tree.query(pt, predicate="intersects")
        ok = any(isos[int(h)] == iso for h in hit)
        if not ok:
            ii = int(tree.nearest(pt))
            ok = isos[ii] == iso and pt.distance(geoms[ii]) <= 0.5
        out.append(ok)
    return np.array(out, bool)


# ── target loaders (heavy; not unit-tested) ──────────────────────────────────────────────────────────────
def _fires_ha(kind: str, work: Path) -> dict:
    import geopandas as gp
    if kind == "mtbs":
        g = gp.read_file(work / "mtbs_perims_DD.shp", columns=["ig_date", "burnbndac", "incid_type"])
        g = g[(g.ig_date.astype(str).str[:4].astype(int) >= HELD_OUT_FROM) & (g.ig_date.astype(str).str[:4].astype(int) <= 2024)
              & g.incid_type.astype(str).str.contains("Wildfire", case=False)]
        c = g.geometry.centroid
        return aggregate_points(c.y, c.x, g.burnbndac * 0.404686)
    if kind == "nfdb":
        parts = [gp.read_file(work / "NFDB_poly_2021to2024_20250630.shp", columns=["YEAR", "SIZE_HA"])]
        g = parts[0]
        g = g[(g.YEAR >= HELD_OUT_FROM) & (g.YEAR <= 2024)]
        c = g.geometry.centroid.to_crs(4326) if g.crs is not None else g.geometry.centroid
        return aggregate_points(c.y, c.x, g.SIZE_HA)
    if kind == "nifc":
        import glob
        rows = []
        for p in sorted(glob.glob(str(RV / "nifc_perimeters" / "page_*.geojson"))):
            for f in json.load(open(p))["features"]:
                pr = f["properties"]
                if (pr.get("FIRE_YEAR_INT") or 0) >= HELD_OUT_FROM and "wildfire" in str(pr.get("FEATURE_CA", "")).lower() \
                        and f.get("geometry"):
                    rows.append({"geometry": f["geometry"], "ac": pr.get("GIS_ACRES") or 0})
        from shapely.geometry import shape
        cs = [shape(r["geometry"]).centroid for r in rows]
        return aggregate_points([c.y for c in cs], [c.x for c in cs], [r["ac"] * 0.404686 for r in rows])
    raise ValueError(kind)


def _gridded_ha(kind: str, work: Path) -> np.ndarray:
    import xarray as xr
    tot = np.zeros((int(180 / RES), int(360 / RES)))
    for y in (2021, 2022):
        if kind == "gfed5":
            d = xr.open_dataset(work / f"GFED5.1_ecosystem_{y}.nc")
            v = d["burned_area"].sum("time").values
            tot += aggregate_grid(v, d["lat"].values, d["lon"].values)
        else:
            import glob
            for f in sorted(glob.glob(str(work / str(y) / "*.nc"))):
                d = xr.open_dataset(f)
                tot += aggregate_grid(d["burned_area"].values[0], d["lat"].values, d["lon"].values)
    return tot


def _build(kind: str, work: Path) -> ValidationResult:
    from ml.validation.regional import macro_region
    if kind in ("mtbs", "nifc", "nfdb"):
        fires = _fires_ha(kind, work)
        iso = "CA" if kind == "nfdb" else "US"
        lat_rng = (41.0, 84.0) if iso == "CA" else (24.0, 72.0)
        ii, jj = np.meshgrid(np.arange(int(180 / RES)), np.arange(int(360 / RES)), indexing="ij")
        ii, jj = ii.ravel(), jj.ravel()
        la, lo = cell_centre(ii, jj)
        m = (la >= lat_rng[0]) & (la <= lat_rng[1]) & (lo >= -170) & (lo <= -50)
        ii, jj, la, lo = ii[m], jj[m], la[m], lo[m]
        m = country_mask(la, lo, iso)
        ii, jj = ii[m], jj[m]
        ha_of = lambda a, b: fires.get((a, b), 0.0)
        src = {"mtbs": "MTBS perimeters (wildfire, 2021-2024)", "nifc": "NIFC interagency perimeters (wildfire, 2021-2024)",
               "nfdb": "Canada NFDB polygons 2021-2024"}[kind]
    else:
        grid = _gridded_ha(kind, work)
        ii, jj = np.meshgrid(np.arange(grid.shape[0]), np.arange(grid.shape[1]), indexing="ij")
        ii, jj = ii.ravel(), jj.ravel()
        ha_of = lambda a, b: float(grid[a, b])
        iso = None
        src = {"gfed5": "GFED5.1 burned area 2021-2022", "firecci": "ESA FireCCI51 grid burned area 2021-2022"}[kind]
    keep, sc = score_cells(ii, jj)
    ii, jj = ii[keep], jj[keep]
    la, lo = cell_centre(ii, jj)
    ar = cell_area_ha(ii)
    obs = [burned_fraction(ha_of(int(a), int(b)), float(c)) for a, b, c in zip(ii, jj, ar)]
    if kind == "nfdb":
        strata = ["north>=55N" if x >= 55 else "south<55N" for x in la]
    elif iso == "US":
        strata = ["Alaska" if (x > 51 and y < -125) else "CONUS" for x, y in zip(la, lo)]
    else:
        strata = [macro_region(float(a), float(b)) for a, b in zip(la, lo)]
    extra = {"auc_occurrence": auc_occurrence(sc, obs), "cells_with_burn": int(sum(o > 0 for o in obs)),
             "held_out_from": HELD_OUT_FROM}
    return ValidationResult(
        hazard_type="wildfire", kind="rank", predicted=sc, observed=obs, strata=strata, extra=extra,
        labels=[f"{a:.2f},{b:.2f}" for a, b in zip(la, lo)], target_source=src, scope=kind, method="temporal_holdout",
        notes="production wildfire score at 0.5deg cell centres vs held-out (2021+) burned fraction; design in module docstring. "
              "Perimeter fires assigned whole to centroid cell. FireCCI shares the MODIS family with the history term.")


def _workdir() -> Path:
    """Extract only the held-out-period members of the source zips into data/reversal_val/_work (once; gitignored with
    the rest of data/), so the validator reproduces from the repo's data alone. WILDFIRE_REGIONS_WORK overrides."""
    import os
    import zipfile
    if os.environ.get("WILDFIRE_REGIONS_WORK"):
        return Path(os.environ["WILDFIRE_REGIONS_WORK"])
    work = RV / "_work"
    work.mkdir(exist_ok=True)
    wants = [(RV / "mtbs_us" / "mtbs_perimeter_data.zip", lambda n: n.startswith("mtbs_perims_DD.")),
             (RV / "nfdb_canada" / "NFDB_poly.zip", lambda n: "2021to2024" in n),
             (RV / "gfed5" / "GFED5.1_ecosystem.zip", lambda n: n.startswith(("GFED5.1_ecosystem_2021", "GFED5.1_ecosystem_2022"))),
             (RV / "firecci51_grid" / "2021.zip", lambda n: n.endswith(".nc")),
             (RV / "firecci51_grid" / "2022.zip", lambda n: n.endswith(".nc"))]
    for z, keep in wants:
        if not z.exists():
            continue
        with zipfile.ZipFile(z) as zf:
            for m in zf.namelist():
                if keep(m) and not (work / m).exists():
                    zf.extract(m, work)
    return work


for _k in ("mtbs", "nifc", "nfdb", "gfed5", "firecci"):
    register(f"wildfire_{_k}")(lambda session, _k=_k: _build(_k, _workdir()))
