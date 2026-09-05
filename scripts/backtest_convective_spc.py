"""Severe-convective calibration backtest — ERA5 CAPE×shear potential vs observed US tornadoes (NOAA SPC).

Honest within-region case-control: does our convective-potential field rank REAL tornado locations above random
CONUS land? Testing WITHIN the US (not tornadoes-vs-oceans) is the fair question — does the potential capture
tornado alley? Cases = SPC tornado start points; controls = random CONUS points. We also report the stricter
significant-tornado (EF2+) subset, which is far less population-biased than weak-tornado reports.

Ranking-family discrimination test (gate ρ/AUC), an environment index — never a tornado-frequency figure.
Run:  PYTHONPATH=. .venv/bin/python scripts/backtest_convective_spc.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

GRID = "data/convective/convective_potential.npz"
SPC = "data/convective/spc_tornadoes.csv"
CONUS = (24.0, 50.0, -125.0, -66.0)   # lat_min, lat_max, lon_min, lon_max
RNG = np.random.default_rng(42)


def _sampler():
    d = np.load(GRID)
    lat, lon, pot = d["lat"], d["lon"], d["potential"]
    lat_i = np.argsort(lat)
    lat_s = lat[lat_i]

    def sample(las, los):
        out = np.empty(len(las))
        for k, (la, lo) in enumerate(zip(las, los)):
            i = lat_i[min(np.searchsorted(lat_s, la), len(lat_s) - 1)]
            j = int(np.argmin(np.abs(lon - lo)))
            out[k] = pot[i, j]
        return out
    return sample


def _auc_lift(sample, case_la, case_lo, label):
    cases = sample(case_la, case_lo)
    la = RNG.uniform(CONUS[0], CONUS[1], len(cases) * 3)
    lo = RNG.uniform(CONUS[2], CONUS[3], len(cases) * 3)
    ctrl = sample(la, lo)
    y = np.r_[np.ones(len(cases)), np.zeros(len(ctrl))]
    s = np.r_[cases, ctrl]
    auc = roc_auc_score(y, s)
    hi_ev = float(np.mean(cases >= 50)); hi_bg = float(np.mean(ctrl >= 50))
    print(f"  {label:26s} n={len(cases):6d}  AUC={auc:.3f}  "
          f"High+(≥50): events {100*hi_ev:.0f}% vs land {100*hi_bg:.0f}%  lift {hi_ev/max(hi_bg,1e-9):.2f}×")
    return auc


def main() -> int:
    df = pd.read_csv(SPC, low_memory=False)
    df = df[(df.slat.between(*CONUS[:2])) & (df.slon.between(*CONUS[2:]))]
    df = df[(df.slat != 0) & (df.slon != 0)]
    sample = _sampler()
    print(f"SPC tornadoes in CONUS with coords: {len(df)}\n")
    _auc_lift(sample, df.slat.values, df.slon.values, "all tornadoes")
    sig = df[df.mag >= 2]
    _auc_lift(sample, sig.slat.values, sig.slon.values, "significant (EF2+)")
    print("\n  Ranking gate: AUC/ρ. Environment index, US validation region (SPC). Caveat: weak-tornado reports")
    print("  carry population bias; the EF2+ subset is the more honest signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
