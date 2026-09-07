"""Coastal-flood calibration check — freeboard screen vs NOAA CO-OPS OBSERVED extreme water levels (independent).

The coastal_flood channel is a deterministic freeboard screen: DEM elevation vs (SURGE_ALLOWANCE_M + SLR), within
COAST_KM of the coast (ml/scoring/sea_level.py). It has NO site-specific surge/tide term — SURGE_ALLOWANCE_M = 2.0 m
is one disclosed constant for every coast. The independent target is what the sea actually did: verified NOAA
tide-gauge monthly HIGHEST water levels 2014-2023 (scripts/fetch_coops_extremes.py), relative to each gauge's own
MHHW and MSL datums. Two questions, CONUS gauges only:
  1. CALIBRATION of the constant — where does 2.0 m above MSL sit against the observed 10-year maximum still-water
     level at real gauges? (percentile, share of gauges above it)
  2. RANKING — does today's score at the gauge rank gauges by their observed extreme? Expected weak: the score
     carries elevation + distance only, so any ρ is elevation-vs-surge coincidence, not modelled surge.
Ranking-family gate (ρ≥0.35). Run: PYTHONPATH=. .venv/bin/python scripts/backtest_coastal_coops.py
"""
from __future__ import annotations

import json
import urllib.request

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ml.scoring.coastal_flood_point import _ZERO, _coastline
from ml.scoring.sea_level import COAST_KM, SURGE_ALLOWANCE_M, coastal_flood_score

CSV = "data/coastal_val/coops_monthly_extremes.csv"
CONUS = (24.0, 50.0, -125.0, -66.0)
MIN_MONTHS = 60


def _elevations(lats, lons) -> list:
    out: list = []
    for i in range(0, len(lats), 100):
        la = ",".join(f"{x:.5f}" for x in lats[i:i + 100]); lo = ",".join(f"{x:.5f}" for x in lons[i:i + 100])
        with urllib.request.urlopen(f"https://api.open-meteo.com/v1/elevation?latitude={la}&longitude={lo}", timeout=60) as r:
            out += json.load(r)["elevation"]
    return out


def main() -> int:
    d = pd.read_csv(CSV)
    d = d[(d.highest_m_above_mhhw > -1.0)]                       # drop datum-glitch months
    d["highest_m_above_msl"] = d.highest_m_above_mhhw - d.msl_m_above_mhhw
    st = d.groupby(["station", "name", "state", "lat", "lon"]).agg(
        n=("highest_m_above_mhhw", "size"), max_mhhw=("highest_m_above_mhhw", "max"),
        max_msl=("highest_m_above_msl", "max"), typical_mhhw=("highest_m_above_mhhw", "median")).reset_index()
    st = st[(st.n >= MIN_MONTHS) & st.lat.between(CONUS[0], CONUS[1]) & st.lon.between(CONUS[2], CONUS[3])]
    print(f"NOAA CO-OPS CONUS gauges with ≥{MIN_MONTHS} verified months 2014-2023: {len(st)}")

    q = st.max_msl.quantile([0.1, 0.25, 0.5, 0.75, 0.9, 0.99]).round(2).to_dict()
    above = float((st.max_msl > SURGE_ALLOWANCE_M).mean())
    print(f"\n1) CALIBRATION  observed 10-yr max still-water level ABOVE MSL, per gauge: "
          f"p10 {q[0.1]}  p25 {q[0.25]}  median {q[0.5]}  p75 {q[0.75]}  p90 {q[0.9]}  p99 {q[0.99]} m")
    print(f"   SURGE_ALLOWANCE_M = {SURGE_ALLOWANCE_M} m sits at the {100*float((st.max_msl < SURGE_ALLOWANCE_M).mean()):.0f}th "
          f"percentile of gauges; {100*above:.0f}% of gauges saw a higher 10-yr maximum")
    top = st.nlargest(6, "max_msl")[["name", "state", "max_msl"]]
    print("   highest observed:", "; ".join(f"{r.name} {r.state} {r.max_msl:.2f} m" for r in top.itertuples()))
    print("   by coast (median 10-yr max above MSL):",
          st.assign(coast=np.where(st.lon < -100, "Pacific", np.where(st.state.isin(["TX", "LA", "MS", "AL", "FL"]), "Gulf/FL", "Atlantic")))
            .groupby("coast").max_msl.median().round(2).to_dict())

    from shapely.geometry import Point
    from shapely.ops import nearest_points
    coast = _coastline()
    st["elev"] = _elevations(st.lat.values, st.lon.values)
    st["dist_km"] = [h3_dist(la, lo, coast, Point, nearest_points) for la, lo in zip(st.lat, st.lon)]
    st["score"] = [coastal_flood_score(e, dk, _ZERO)[0] for e, dk in zip(st.elev, st.dist_km)]
    st = st.dropna(subset=["score"])
    rho, p = spearmanr(st.score, st.max_mhhw)
    print(f"\n2) RANKING  today's coastal score at the gauge vs observed 10-yr max above MHHW: "
          f"Spearman ρ = {rho:.3f} (p={p:.1e}, n={len(st)}); score = elevation/freeboard only "
          f"(gauge elev median {st.elev.median():.1f} m, {100*float((st.dist_km <= COAST_KM).mean()):.0f}% within {COAST_KM:.0f} km)")
    print("\nGate: RANKING family (ρ≥0.35 floor). Independent observed target (NOAA CO-OPS verified water levels), "
          "US region. The channel has no modelled surge term; (1) is a calibration check of the disclosed constant.")
    return 0


def h3_dist(lat, lon, coast, Point, nearest_points) -> float:
    import h3
    near = nearest_points(coast, Point(lon, lat))[0]
    return float(h3.great_circle_distance((lat, lon), (near.y, near.x), unit="km"))


if __name__ == "__main__":
    raise SystemExit(main())
