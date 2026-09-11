"""Subsidence validator — the Herrera GSS susceptibility class against OBSERVED InSAR vertical ground motion
(Copernicus EGMS Ortho L3, 2020–2024, 100 m, GNSS-calibrated; scripts/fetch_egms_tiles.py).

This is the target the GNSS test could not be: InSAR measures the ground itself — soft sediments, peat, built-up
land — not an antenna on bedrock. Each EGMS tile is reduced to 1 km blocks (10 × 10 pixels, ≥ MIN_PIXELS valid);
the block's mean vertical velocity is the observed quantity (sign flipped: subsidence positive) and the GSS class
at the block centre is the prediction. `rank` kind, Spearman ≥ 0.35 with monotone bands, over a fixed random
sample of blocks (SAMPLE, seed stated); the share of blocks subsiding faster than SUBSIDING_MM_YR per class is
reported alongside. Scope Europe (EGMS coverage). Tiles not yet on disk are simply absent.

Glacial rebound is excluded by a declared rule (north of 55 °N between 4 °E and 35 °E: Fennoscandia and the Baltic
shield). Uplift is not subsidence: with those blocks in, class-1 bedrock rising 3.4 mm/yr makes the rank
correlation 0.55 for the wrong reason; without them it is 0.10 (2026-09-11, 180,932 blocks) — the class does not
rank where the ground actually sinks in Europe, and the channel stays Screening. Recorded, not tuned around.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

TILES = Path("data/egms")
BLOCK = 10                    # 10 × 100 m = 1 km, the GSS model's own resolution
MIN_PIXELS = 20
SAMPLE, SEED = 300_000, 7
SUBSIDING_MM_YR = 2.0
REBOUND = (55.0, 4.0, 35.0)   # lat >, lon between: glacial-isostatic uplift region excluded (uplift is not subsidence)


def _blocks(path: Path):
    """(lon, lat, mean_velocity_mm_yr) per 1 km block with enough measured pixels."""
    import rasterio
    from rasterio.warp import transform
    with rasterio.open(path) as ds:
        a = ds.read(1).astype("float32")
        nod = ds.nodata
        a[(a == nod) if nod is not None else ~np.isfinite(a)] = np.nan
        h, w = (a.shape[0] // BLOCK) * BLOCK, (a.shape[1] // BLOCK) * BLOCK
        b = a[:h, :w].reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK)
        n = np.isfinite(b).sum(axis=(1, 3))
        with np.errstate(invalid="ignore"):
            mean = np.nanmean(b, axis=(1, 3))
        rows, cols = np.where(n >= MIN_PIXELS)
        if len(rows) == 0:
            return np.empty(0), np.empty(0), np.empty(0)
        xs, ys = ds.xy(rows * BLOCK + BLOCK / 2, cols * BLOCK + BLOCK / 2)
        lon, lat = transform(ds.crs, "EPSG:4326", list(xs), list(ys))
        return np.asarray(lon), np.asarray(lat), mean[rows, cols]


def _run(session: Session) -> ValidationResult:
    from ml.scoring.subsidence_point import _RASTER_PATH, CLASS_SCORE
    from services.geo.raster_sampler import sample
    tiles = sorted(TILES.glob("EGMS_L3_*_U_*.tiff"))
    if not tiles:
        return ValidationResult(hazard_type="subsidence", kind="rank", predicted=[], observed=[], labels=[],
                                target_source="Copernicus EGMS Ortho L3 vertical velocity 2020–2024", scope="EU", method="out_of_sample",
                                notes="no EGMS tiles under data/egms — run scripts/fetch_egms_tiles.py (needs EGMS_TOKEN)")
    lon, lat, vel, tile_of = [], [], [], []
    for t in tiles:
        lo, la, v = _blocks(t)
        lon.append(lo); lat.append(la); vel.append(v); tile_of += [t.stem.split("_")[2]] * len(v)
    lon, lat, vel = np.concatenate(lon), np.concatenate(lat), np.concatenate(vel); tile_of = np.asarray(tile_of)
    rebound = (lat > REBOUND[0]) & (lon >= REBOUND[1]) & (lon <= REBOUND[2])
    lon, lat, vel, tile_of = lon[~rebound], lat[~rebound], vel[~rebound], tile_of[~rebound]
    idx = np.arange(len(vel))
    if len(idx) > SAMPLE:
        idx = np.sort(np.random.default_rng(SEED).choice(idx, SAMPLE, replace=False))
    pred, obs, labels, cls_all = [], [], [], []
    pts = [(float(lon[i]), float(lat[i])) for i in idx]
    for s0 in range(0, len(pts), 5000):
        got = sample(_RASTER_PATH, pts[s0:s0 + 5000]) or []
        for i, g in zip(idx[s0:s0 + 5000], got):
            c = int(g[0]) if g else 0
            if 1 <= c <= 6:
                pred.append(CLASS_SCORE[c]); obs.append(float(-vel[i])); labels.append(f"{tile_of[i]} {lat[i]:.3f},{lon[i]:.3f}"); cls_all.append(c)
    cls_all = np.asarray(cls_all); o = np.asarray(obs)
    by_class = {int(c): {"n": int((cls_all == c).sum()), "median_subsidence_mm_yr": round(float(np.median(o[cls_all == c])), 2),
                         "share_subsiding": round(float((o[cls_all == c] > SUBSIDING_MM_YR).mean()), 3)} for c in np.unique(cls_all)}
    return ValidationResult(hazard_type="subsidence", kind="rank", predicted=pred, observed=obs, labels=labels,
                            target_source="Copernicus EGMS Ortho L3 InSAR vertical ground velocity 2020–2024 (GNSS-calibrated, 100 m), 1 km block means",
                            scope="EU", method="out_of_sample", data_vintage=f"EGMS 2020–2024, {len(tiles)} tiles, seed {SEED}",
                            notes=(f"GSS susceptibility class vs observed subsidence rate per 1 km block, glacial-rebound region (>{REBOUND[0]:.0f}°N, "
                                   f"{REBOUND[1]:.0f}–{REBOUND[2]:.0f}°E) excluded ({int(rebound.sum())} blocks; with it in the rank is 0.55 for the wrong "
                                   f"reason — rising bedrock); {len(pred)} of {len(vel)} blocks sampled. By class {by_class}. InSAR measures the ground "
                                   f"itself, so this supersedes the GNSS test (ρ 0.21) as the subsidence target"),
                            extra={"by_class": by_class, "n_tiles": len(tiles), "rebound_blocks_excluded": int(rebound.sum())})


register("subsidence_egms")(_run)
