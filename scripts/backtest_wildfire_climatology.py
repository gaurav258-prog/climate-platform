"""Wildfire hazard-climatology backtest — vs EFFIS burn scars 2022-2024 (official, held out in TIME).

NON-CIRCULAR by construction: every climatology input ends in 2020 (fire weather 2006-2020, burn history 2001-2019);
the target is what burned in Europe in 2022-2024 (scripts/fetch_effis_europe.py, 41k JRC-mapped scars). The
'weather_fuel' variant uses no burn observation at all (fully independent target); 'with_history' reuses the
2001-2019 burn record (in-domain — the same caveat landslide/LHASA carries, disclosed). 'history_only' is shown
so the reader can see what the fire-weather term adds.
Tests (Europe box, burnable land):
  1. OCCURRENCE — case-control ROC-AUC: scar centroids vs random burnable-land points (3×), + High+ lift
  2. MAGNITUDE  — Spearman ρ: per 0.5° cell, total hectares burned 2022-24 vs score (cells with ≥3 scars)
Ranking-family gate (ρ≥0.35). Run: PYTHONPATH=. .venv/bin/python scripts/backtest_wildfire_climatology.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from shapely.geometry import shape
from sklearn.metrics import roc_auc_score

from ml.scoring.wildfire_climatology import load_grids, sample_terms, wildfire_hazard

TARGET = "data/wildfire_val/effis_europe_2022_2024.geojson"
EUROPE = (34.0, 72.0, -25.0, 45.0)     # S, N, W, E
RNG = np.random.default_rng(42)
MIN_BURNABLE = 0.2


def _terms(lats, lons, g):
    rows = [sample_terms(float(a), float(b), g) for a, b in zip(lats, lons)]
    return pd.DataFrame(rows)


def main() -> int:
    g = load_grids()
    if g is None:
        print("climatologies not built — run build_fwi_climatology.py and build_burned_area_climatology.py"); return 1
    fc = json.load(open(TARGET))
    cent = [shape(f["geometry"]).centroid for f in fc["features"]]
    cases = pd.DataFrame({"lat": [c.y for c in cent], "lon": [c.x for c in cent],
                          "ha": [float(f["properties"].get("AREA_HA") or 0) for f in fc["features"]]})
    cases = cases[cases.lat.between(EUROPE[0], EUROPE[1]) & cases.lon.between(EUROPE[2], EUROPE[3])]
    print(f"EFFIS scars 2022-2024 in Europe box: {len(cases)}  ({cases.ha.sum():,.0f} ha)  "
          f"fire-weather years {g['fwi_years'].min()}-{g['fwi_years'].max()}, burn history {g['ba_years'].min()}-{g['ba_years'].max()}")

    # controls: random points on burnable land (the layer's own mask), 3× cases
    n = 3 * len(cases); ctrl = []
    while len(ctrl) < n:
        la = RNG.uniform(EUROPE[0], EUROPE[1], 5000); lo = RNG.uniform(EUROPE[2], EUROPE[3], 5000)
        t = _terms(la, lo, g)
        keep = t.burnable_fraction >= MIN_BURNABLE
        ctrl += list(zip(la[keep.values], lo[keep.values]))
    ctrl = pd.DataFrame(ctrl[:n], columns=["lat", "lon"])
    tc, tk = _terms(cases.lat.values, cases.lon.values, g), _terms(ctrl.lat.values, ctrl.lon.values, g)
    print(f"  scar cells: burnable {tc.burnable_fraction.mean():.2f}, extreme days {tc.days_extreme.mean():.1f}/yr | "
          f"land: burnable {tk.burnable_fraction.mean():.2f}, extreme days {tk.days_extreme.mean():.1f}/yr")

    y = np.r_[np.ones(len(tc)), np.zeros(len(tk))]
    for variant in ("weather_fuel", "with_history", "history_only"):
        if variant == "history_only":
            sc = np.r_[wildfire_hazard(0, 1, tc.burned_fraction.values, "with_history")["history_term"],
                       wildfire_hazard(0, 1, tk.burned_fraction.values, "with_history")["history_term"]]
        else:
            sc = np.r_[wildfire_hazard(tc.days_extreme.values, tc.burnable_fraction.values, tc.burned_fraction.values, variant)["score"],
                       wildfire_hazard(tk.days_extreme.values, tk.burnable_fraction.values, tk.burned_fraction.values, variant)["score"]]
        auc = roc_auc_score(y, sc)
        hi_ev, hi_bg = float(np.mean(sc[y == 1] >= 50)), float(np.mean(sc[y == 0] >= 50))
        # magnitude per 0.5° cell
        gi = np.floor(cases.lat.values * 2); gj = np.floor(cases.lon.values * 2)
        pc = pd.DataFrame({"gi": gi, "gj": gj, "ha": cases.ha.values, "s": sc[y == 1]}).groupby(["gi", "gj"]).agg(
            ha=("ha", "sum"), n=("ha", "size"), s=("s", "mean")).reset_index()
        pc = pc[pc.n >= 3]
        rho, p = spearmanr(pc.s, pc.ha)
        print(f"\n[{variant}]  1) OCCURRENCE AUC = {auc:.3f}   High+(≥50): scars {100*hi_ev:.0f}% vs land {100*hi_bg:.0f}%  "
              f"lift {hi_ev/max(hi_bg,1e-9):.2f}×\n{'':18s}2) MAGNITUDE  Spearman ρ = {rho:.3f} (p={p:.1e}) over {len(pc)} cells (≥3 scars)")
    print("\nGate: RANKING family (ρ≥0.35 floor; AUC reported). Independent official target (EFFIS 2022-24 scars), "
          "held out in time; Europe validation region. 'weather_fuel' uses no burn observation; 'with_history' is in-domain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
