"""Aggregate the raw GTN-P European borehole ground-temperature record into one observed statistic per
borehole: Mean Annual Ground Temperature (MAGT) at the depth closest to the zero-annual-amplitude (ZAA) zone.

Why MAGT-at-depth is the right independent observed signal: GTN-P's own permafrost-monitoring convention uses
MAGT near the depth where the seasonal temperature cycle has damped out (roughly 10-20 m at most sites) as the
standard indicator of permafrost presence/condition — colder MAGT means permafrost is present and stable,
MAGT near or above 0 degC means the ground is thawed or actively degrading. This is a real thermal measurement,
independent of the Obu et al. (2019) TTOP probability raster the platform's permafrost_thaw channel reads, so
rank-correlating the raster-derived score against per-site MAGT is a non-circular backtest.

Input:  data/permafrost_val/permafrost_ground_temp_europe.csv (id, date, depth, temperature, flag, dataset_id,
        borehole_id, site_id — 4.9M daily/sub-daily rows, 389 GTN-P boreholes)
        data/permafrost_val/boreholes_europe_meta.json (borehole_id -> lat/lon/country/permafrost_zone/...)
Output: data/permafrost_val/borehole_magt.csv — one row per qualifying borehole:
        borehole_id, lat, lon, country, permafrost_zone, depth_m, magt_c, n_obs, n_years, first_year, last_year

Depth selection per borehole: among depths with >= MIN_OBS readings spanning >= MIN_YEARS distinct calendar
years, prefer the one closest to TARGET_DEPTH_M (10 m); ties broken by more observations. Readings flagged
"suspicious value - please check" are dropped; "no data entry" rows (temperature already NaN) are dropped by
the NaN filter. MAGT is the plain mean of all qualifying daily readings at the chosen depth (not a true annual
cycle fit) — a caveat carried into the validator's notes for shallow/short-record sites.

Run:  .venv/bin/python -m scripts.build_permafrost_boreholes
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RAW_CSV = Path("data/permafrost_val/permafrost_ground_temp_europe.csv")
META_JSON = Path("data/permafrost_val/boreholes_europe_meta.json")
OUT_CSV = Path("data/permafrost_val/borehole_magt.csv")

TARGET_DEPTH_M = 10.0
MIN_OBS = 300          # roughly a year of daily readings at the chosen depth
MIN_YEARS = 1


def _load_meta() -> dict[int, dict]:
    rows = json.loads(META_JSON.read_text())
    return {int(r["borehole_id"]): r for r in rows}


def pick_depth(g: pd.DataFrame) -> pd.DataFrame | None:
    """Among depths with enough qualifying readings, the one closest to TARGET_DEPTH_M (ties: more obs)."""
    by_depth = g.groupby("depth")
    candidates = []
    for depth, sub in by_depth:
        n_obs = len(sub)
        n_years = sub["date"].dt.year.nunique()
        if n_obs >= MIN_OBS and n_years >= MIN_YEARS:
            candidates.append((depth, n_obs, n_years, sub))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (abs(t[0] - TARGET_DEPTH_M), -t[1]))
    depth, n_obs, n_years, sub = candidates[0]
    return depth, n_obs, n_years, sub


def main() -> int:
    meta = _load_meta()
    df = pd.read_csv(RAW_CSV, usecols=["date", "depth", "temperature", "flag", "borehole_id"])
    df = df[df["flag"].isna() | (df["flag"] != "suspicious value - please check")]
    df = df.dropna(subset=["temperature", "depth"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    out_rows = []
    for bh_id, g in df.groupby("borehole_id"):
        m = meta.get(int(bh_id))
        if not m or m.get("lat") is None or m.get("lon") is None:
            continue
        picked = pick_depth(g)
        if picked is None:
            continue
        depth, n_obs, n_years, sub = picked
        out_rows.append({
            "borehole_id": int(bh_id),
            "lat": float(m["lat"]),
            "lon": float(m["lon"]),
            "country": m.get("country_iso_a2") or m.get("country_name"),
            "permafrost_zone": m.get("permafrost_zone"),
            "depth_m": float(depth),
            "magt_c": round(float(sub["temperature"].mean()), 4),
            "n_obs": int(n_obs),
            "n_years": int(n_years),
            "first_year": int(sub["date"].dt.year.min()),
            "last_year": int(sub["date"].dt.year.max()),
        })

    out = pd.DataFrame(out_rows).sort_values("borehole_id")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"{len(out)} boreholes with a qualifying depth (of {df['borehole_id'].nunique()} in the raw record) "
          f"-> {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
