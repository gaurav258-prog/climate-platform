"""Landslide calibration backtest — NASA/LHASA susceptibility vs the observed Global Landslide Catalog.

Honest case-control test: does our terrain-susceptibility score rank REAL landslides (NASA GLC, ~9.5k
geolocated events) above background land? Cases = GLC event coordinates; controls = random land points where
the raster has coverage. We sample the susceptibility class (0-5 → 0-100, the production mapping) at each and
report ROC-AUC (case vs control) plus the class LIFT (share of events in High+ classes vs share of land),
which is less sensitive to the GLC's known reporting bias toward populated/English-speaking regions.

This is a susceptibility→occurrence discrimination test (RANKING family, gate ρ/AUC), not a €-severity model.
Run:  PYTHONPATH=. .venv/bin/python scripts/backtest_landslide_glc.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import roc_auc_score

from ml.scoring.landslide_point import _NODATA, _RASTER_PATH, CLASS_SCORE

GLC = "data/landslide/glc.csv"
RNG = np.random.default_rng(42)


def _sample(src, lats, lons) -> np.ndarray:
    """Susceptibility class at each (lat,lon); NaN off-raster/nodata."""
    out = np.full(len(lats), np.nan)
    band = src.read(1)
    for i, (la, lo) in enumerate(zip(lats, lons)):
        if not (src.bounds.bottom <= la <= src.bounds.top and src.bounds.left <= lo <= src.bounds.right):
            continue
        r, c = src.index(lo, la)
        if 0 <= r < band.shape[0] and 0 <= c < band.shape[1]:
            v = band[r, c]
            if v != _NODATA:
                out[i] = v
    return out


def main() -> int:
    df = pd.read_csv(GLC, low_memory=False).dropna(subset=["latitude", "longitude"])
    df = df[(df.latitude.between(-90, 90)) & (df.longitude.between(-180, 180))]
    with rasterio.open(_RASTER_PATH) as src:
        case_cls = _sample(src, df.latitude.values, df.longitude.values)
        # background land controls: random points, keep those on the raster, match the case count
        n_need = int(np.isfinite(case_cls).sum())
        ctrl_cls: list[float] = []
        while len(ctrl_cls) < n_need * 3:
            la = RNG.uniform(-56, 72, 20000); lo = RNG.uniform(-180, 180, 20000)
            s = _sample(src, la, lo)
            ctrl_cls.extend(s[np.isfinite(s)].tolist())
    case_cls = case_cls[np.isfinite(case_cls)]
    ctrl_cls = np.array(ctrl_cls[: n_need * 3])

    case_score = np.array([CLASS_SCORE[int(v)] for v in case_cls])
    ctrl_score = np.array([CLASS_SCORE[int(v)] for v in ctrl_cls])

    y = np.r_[np.ones(len(case_score)), np.zeros(len(ctrl_score))]
    s = np.r_[case_score, ctrl_score]
    auc = roc_auc_score(y, s)

    print(f"cases (GLC events on raster): {len(case_score)}   controls (background land): {len(ctrl_score)}")
    print("\nsusceptibility class distribution (share):")
    print(f"  {'class':>5} {'events%':>9} {'land%':>9} {'lift':>6}")
    for k in range(6):
        ev = float(np.mean(case_cls == k)); bg = float(np.mean(ctrl_cls == k))
        lift = ev / bg if bg > 0 else float("nan")
        print(f"  {k:>5} {100*ev:>8.1f}% {100*bg:>8.1f}% {lift:>6.2f}")
    hi_ev = float(np.mean(case_cls >= 3)); hi_bg = float(np.mean(ctrl_cls >= 3))
    print(f"\n  High+ (class≥3): events {100*hi_ev:.1f}%  vs land {100*hi_bg:.1f}%  → lift {hi_ev/hi_bg:.2f}×")
    print(f"\n  ROC-AUC (susceptibility ranks real landslides vs background land) = {auc:.3f}")
    print("  Caveat: GLC over-reports populated/English-speaking regions; random controls don't correct for that,")
    print("  so AUC is an upper-ish estimate — the class-lift is the more bias-robust signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
