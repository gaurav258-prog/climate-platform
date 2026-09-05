"""Windstorm calibration backtest — ERA5 gust climatology vs NOAA Storm Events (independent, observed).

NON-CIRCULAR by design: the target is real REPORTED wind events (NOAA Storm Events Database), NOT a
reanalysis-derived footprint (which would share ERA5's wind). We use only the non-convective, non-tropical
wind perils our WINDSTORM channel represents — High Wind, Strong Wind, Blizzard, Dust Storm (+ marine) —
excluding Thunderstorm Wind (convective → severe_convective), Tropical Storm (→ cyclone) and Ice Storm /
Wind Chill (not a wind-speed peril).

These land events are issued by NWS forecast ZONE (no point lat/lon), so we geolocate each to its zone
CENTROID from the NWS public-zone shapefile (STATE + zone → LAT/LON) — no dropping of the land events.

Two independent tests within CONUS:
  1. OCCURRENCE — case-control ROC-AUC: does the climatology rank event zones above background US land?
  2. MAGNITUDE  — Spearman ρ: per 0.5° cell, does the climatology rank cells by their OBSERVED peak gust
     (NOAA MAGNITUDE, knots→m/s)? The direct, non-circular skill test.

Ranking-family gate (ρ/AUC). Run:  PYTHONPATH=. .venv/bin/python scripts/backtest_windstorm_noaa.py
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd
import shapefile
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

GRID = "data/wind/windstorm_gust_climatology.npz"
FILES = "data/windstorm_val/*.csv.gz"
ZONE_SHP = glob.glob("data/windstorm_val/z_*.shp")
WINDSTORM_TYPES = {"High Wind", "Strong Wind", "Blizzard", "Dust Storm", "Marine High Wind", "Marine Strong Wind"}
CONUS = (24.0, 50.0, -125.0, -66.0)
KT_TO_MS = 0.514444
RNG = np.random.default_rng(42)

_ABBR = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO",
    "CONNECTICUT": "CT", "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX",
    "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY", "DISTRICT OF COLUMBIA": "DC",
}


def _zone_centroids() -> dict:
    r = shapefile.Reader(ZONE_SHP[0])
    fields = [f[0] for f in r.fields[1:]]
    si, zi, la, lo = fields.index("STATE"), fields.index("ZONE"), fields.index("LAT"), fields.index("LON")
    out = {}
    for rec in r.records():
        try:
            out[(rec[si], int(rec[zi]))] = (float(rec[la]), float(rec[lo]))
        except (ValueError, TypeError):
            continue
    return out


def _sampler():
    z = np.load(GRID)
    lat, lon, g = z["lat"], z["lon"], z["gust_ms"]

    def sample(las, los):
        return np.array([g[int(np.abs(lat - la).argmin()), int(np.abs(lon - lo).argmin())] for la, lo in zip(las, los)])
    return sample, lat, lon


def main() -> int:
    zc = _zone_centroids()
    frames = [pd.read_csv(f, low_memory=False, compression="gzip",
                          usecols=["EVENT_TYPE", "STATE", "CZ_TYPE", "CZ_FIPS", "BEGIN_LAT", "BEGIN_LON", "MAGNITUDE"])
              for f in sorted(glob.glob(FILES))]
    df = pd.concat(frames, ignore_index=True)
    df = df[df.EVENT_TYPE.isin(WINDSTORM_TYPES)].copy()

    # geolocate: zone events → zone centroid; point/marine events → their own coords
    def _loc(row):
        if pd.notna(row.BEGIN_LAT) and pd.notna(row.BEGIN_LON):
            return row.BEGIN_LAT, row.BEGIN_LON
        c = zc.get((_ABBR.get(str(row.STATE).upper()), int(row.CZ_FIPS)) if pd.notna(row.CZ_FIPS) else None)
        return (c[0], c[1]) if c else (np.nan, np.nan)

    df[["lat", "lon"]] = df.apply(lambda r: pd.Series(_loc(r)), axis=1)
    df = df.dropna(subset=["lat", "lon"])
    df = df[(df.lat.between(*CONUS[:2])) & (df.lon.between(*CONUS[2:]))]
    print(f"NOAA non-convective wind events geolocated in CONUS (2015-2023): {len(df)}")
    print("  by type:", df.EVENT_TYPE.value_counts().to_dict())

    sample, glat, glon = _sampler()

    # 1. occurrence
    cases = sample(df.lat.values, df.lon.values)
    la = RNG.uniform(CONUS[0], CONUS[1], len(cases) * 3); lo = RNG.uniform(CONUS[2], CONUS[3], len(cases) * 3)
    ctrl = sample(la, lo)
    auc = roc_auc_score(np.r_[np.ones(len(cases)), np.zeros(len(ctrl))], np.r_[cases, ctrl])
    hi_ev, hi_bg = float(np.mean(cases >= 50)), float(np.mean(ctrl >= 50))
    print(f"\n1) OCCURRENCE  case-control AUC = {auc:.3f}   "
          f"High+(≥50): events {100*hi_ev:.0f}% vs land {100*hi_bg:.0f}%  lift {hi_ev/max(hi_bg,1e-9):.2f}×")

    # 2. magnitude
    mg = df.dropna(subset=["MAGNITUDE"]); mg = mg[mg.MAGNITUDE > 0]
    gi = np.abs(glat[:, None] - mg.lat.values).argmin(axis=0)
    gj = np.abs(glon[:, None] - mg.lon.values).argmin(axis=0)
    pc = pd.DataFrame({"gi": gi, "gj": gj, "kt": mg.MAGNITUDE.values}).groupby(["gi", "gj"]).agg(
        obs_kt=("kt", "max"), n=("kt", "size")).reset_index()
    pc = pc[pc.n >= 3]
    zg = np.load(GRID)["gust_ms"]
    pc["clim"] = [zg[int(i), int(j)] for i, j in zip(pc.gi, pc.gj)]
    rho, p = spearmanr(pc.clim, pc.obs_kt * KT_TO_MS)
    print(f"2) MAGNITUDE   Spearman ρ = {rho:.3f} (p={p:.1e}) over {len(pc)} cells (≥3 events each)")
    print("               climatological gust vs OBSERVED peak gust per cell — direct, non-circular skill")
    print("\nGate: RANKING family (ρ≥0.35 floor). Independent observed target (NOAA reports), US region.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
