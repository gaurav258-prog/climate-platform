"""Build the annual global-warming-level (GWL) trajectory per scenario — the physical time axis the
forward projection is interpolated ALONG (instead of calendar-linear time).

WHY. The engine is modelled at discrete anchor periods, and an intermediate year used to be a straight
calendar-linear blend of the bracketing anchors. But warming is NOT linear in time — SSP5-8.5 goes
~1.9 °C (2050) → ~4.7 °C (2100), so most of the century's warming lands late. Because the hazard
response is (to first order) linear in warming, the physically-correct value at year Y is the anchor
blend weighted by the GLOBAL WARMING LEVEL at Y, not by the calendar fraction. This script writes the
GWL(scenario, year) curve that `services/intelligence/gwl.py` reads to compute that weight.

SOURCES (no fitting, disclosed):
  • Anchor warming per (SSP, period) = the AREA-WEIGHTED GLOBAL MEAN of OUR OWN CMIP6 ensemble ΔT field
    (data/cmip6/cmip6_global_deltas.npz — the same ensemble the local deltas come from), vs the CMIP6
    1995-2014 baseline. So the trajectory is consistent with the deltas the projection actually uses.
  • Present-day node (2025) = +0.30 °C vs 1995-2014 — the observed 2015-2024 global-mean anomaly above
    that baseline (HadCRUT5 / GISTEMP assessed), identical across scenarios in the near term.
  • Between the nodes the annual curve is a MONOTONE (shape-preserving) interpolation — it introduces no
    overshoot and passes exactly through the modelled nodes; the intra-segment curvature comes only from
    the ensemble's own multi-period warming shape.

Output: data/gwl/gwl_annual.csv  (scenario, year, gwl_c)
"""
from __future__ import annotations

import csv
import os

import numpy as np

NPZ = "data/cmip6/cmip6_global_deltas.npz"
OUT = "data/gwl/gwl_annual.csv"

SSP_FOR_SCENARIO = {"orderly_1_5c": "ssp126", "disorderly_2c": "ssp245", "hot_house_3_5c": "ssp585"}
# UI horizon anchor (year) → the CMIP6 period whose global mean sets that anchor's warming level.
PERIOD_YEAR = {"2021-2040": 2030, "2041-2060": 2050, "2081-2100": 2100}
PRESENT_YEAR, PRESENT_GWL = 2025, 0.30   # observed 2015-2024 mean vs 1995-2014 (HadCRUT5/GISTEMP)


def _global_mean(field: np.ndarray, lat: np.ndarray) -> float:
    w = np.cos(np.deg2rad(lat))
    m = np.ma.masked_invalid(field)
    return float(np.ma.average(m, weights=np.broadcast_to(w[:, None], field.shape)))


def _pchip(xs, ys, xq):
    """Monotone cubic (Fritsch–Carlson) — shape-preserving, no overshoot, exact at the nodes.
    Pure-numpy so the build carries no scipy dependency."""
    xs = np.asarray(xs, float); ys = np.asarray(ys, float)
    n = len(xs)
    h = np.diff(xs); delta = np.diff(ys) / h
    d = np.zeros(n)
    d[0], d[-1] = delta[0], delta[-1]
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] <= 0:
            d[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            d[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    out = np.empty_like(np.asarray(xq, float))
    for k, x in enumerate(np.asarray(xq, float)):
        j = min(np.searchsorted(xs, x) - 1, n - 2); j = max(j, 0)
        t = (x - xs[j]) / h[j]
        h00 = 2 * t**3 - 3 * t**2 + 1; h10 = t**3 - 2 * t**2 + t
        h01 = -2 * t**3 + 3 * t**2; h11 = t**3 - t**2
        out[k] = h00 * ys[j] + h10 * h[j] * d[j] + h01 * ys[j + 1] + h11 * h[j] * d[j + 1]
    return out


def main() -> int:
    z = np.load(NPZ)
    lat = z["lat"]
    rows = []
    for scenario, ssp in SSP_FOR_SCENARIO.items():
        nodes = {PRESENT_YEAR: PRESENT_GWL}
        for period, yr in PERIOD_YEAR.items():
            key = f"{ssp}|{period}|dtas_mean"
            if key in z.files:
                nodes[yr] = round(_global_mean(z[key], lat), 3)
        yrs = sorted(nodes)
        gwl = [nodes[y] for y in yrs]
        years = list(range(PRESENT_YEAR, 2101))
        curve = _pchip(yrs, gwl, years)
        # enforce monotone-nondecreasing after the peak is NOT imposed — ssp126 genuinely plateaus/declines,
        # which is real; the shape-preserving interpolant already respects the node ordering.
        for y, g in zip(years, curve):
            rows.append((scenario, y, round(float(g), 4)))
        print(f"{scenario:16s} nodes={ {y: nodes[y] for y in yrs} }")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["scenario", "year", "gwl_c"]); w.writerows(rows)
    print(f"\nwrote {len(rows)} rows → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
