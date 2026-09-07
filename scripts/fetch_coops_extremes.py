"""NOAA CO-OPS tide gauges — observed monthly extreme water levels (independent coastal-flood target).

Pulls, for every NOAA water-level station, the verified MONTHLY MEANS product 2014-2023 relative to the
station's MHHW datum; each row carries the month's HIGHEST observed water level (tide + surge). That is a
real, observed extreme still-water level at the coast — independent of our coastal-flood freeboard model
(DEM elevation + distance-to-coast + a generic surge allowance). Lands data/coastal_val/coops_monthly_extremes.csv.
Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_coops_extremes.py
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import requests

STATIONS = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=waterlevels"
DATA = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
OUT = Path("data/coastal_val/coops_monthly_extremes.csv")
BEGIN, END = "20140101", "20231231"


def main() -> int:
    st = requests.get(STATIONS, timeout=60).json()["stations"]
    print(f"{len(st)} NOAA water-level stations")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n_ok = n_empty = 0
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station", "name", "state", "lat", "lon", "year", "month", "highest_m_above_mhhw", "msl_m_above_mhhw"])
        for i, s in enumerate(st):
            try:
                r = requests.get(DATA, params={
                    "product": "monthly_mean", "application": "tellumen_backtest", "begin_date": BEGIN, "end_date": END,
                    "datum": "MHHW", "station": s["id"], "time_zone": "GMT", "units": "metric", "format": "json",
                }, timeout=60)
                rows = r.json().get("data", [])
            except Exception as e:  # one bad station must not kill the pull
                print(f"  {s['id']} {s['name']}: {e}")
                rows = []
            if not rows:
                n_empty += 1
                continue
            n_ok += 1
            for d in rows:
                if d.get("highest") in (None, ""):
                    continue
                w.writerow([s["id"], s["name"], s.get("state"), s["lat"], s["lng"], d["year"], d["month"],
                            d["highest"], d.get("MSL")])
            if i % 25 == 0:
                print(f"  {i}/{len(st)} … ok={n_ok} empty={n_empty}")
            time.sleep(0.15)
    print(f"wrote {OUT}: stations with data {n_ok}, without {n_empty}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
