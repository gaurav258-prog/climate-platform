"""Aggregate the non-European GTN-P borehole record (US, CA, CN, AQ; fetched from the public GTN-P API,
CC BY 4.0) to one MAGT per borehole, using EXACTLY the conventions of scripts/build_permafrost_boreholes.py
(depth closest to 10 m with >=300 readings over >=1 year; 'suspicious value' flagged rows dropped; plain mean).

Input:  data/permafrost_val/permafrost_ground_temp_global_new.csv, boreholes_global_nonrussia_meta.json
Output: data/permafrost_val/borehole_magt_global.csv (same columns as borehole_magt.csv)
Run:    PYTHONPATH=. .venv/bin/python -m scripts.build_permafrost_boreholes_global
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.build_permafrost_boreholes import pick_depth

RAW = Path("data/permafrost_val/permafrost_ground_temp_global_new.csv")
META = Path("data/permafrost_val/boreholes_global_nonrussia_meta.json")
OUT = Path("data/permafrost_val/borehole_magt_global.csv")


def main() -> int:
    meta = {int(r["borehole_id"]): r for r in json.loads(META.read_text())}
    df = pd.read_csv(RAW, usecols=["date", "depth", "temperature", "flag", "borehole_id"])
    df = df[df["flag"].isna() | (df["flag"] != "suspicious value - please check")]
    df = df.dropna(subset=["temperature", "depth"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    rows = []
    for bh, g in df.groupby("borehole_id"):
        m = meta.get(int(bh))
        if not m or m.get("lat") is None or m.get("lon") is None:
            continue
        p = pick_depth(g)
        if p is None:
            continue
        depth, n_obs, n_years, sub = p
        rows.append({"borehole_id": int(bh), "lat": float(m["lat"]), "lon": float(m["lon"]),
                     "country": m.get("country_iso_a2"), "permafrost_zone": m.get("permafrost_zone"),
                     "depth_m": float(depth), "magt_c": round(float(sub["temperature"].mean()), 4),
                     "n_obs": int(n_obs), "n_years": int(n_years),
                     "first_year": int(sub["date"].dt.year.min()), "last_year": int(sub["date"].dt.year.max())})
    pd.DataFrame(rows).sort_values("borehole_id").to_csv(OUT, index=False)
    print(f"{len(rows)} boreholes of {df['borehole_id'].nunique()} with data -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
