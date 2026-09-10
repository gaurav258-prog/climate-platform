"""Observed daily extremes 1991–2020 at GHCN-Daily stations (NOAA NCEI access service) → station_extremes.

The independent target for the cold-wave, chronic-heat and heavy-precipitation backtests: stations measure the
weather; our channels are built from reanalysis and gridded climatologies. Selection: one station per 1°×1° box
with TMIN/TMAX/PRCP records spanning 1991–2020, across Europe and the contiguous US (data/ghcn/stations_selected.json,
from ghcnd-inventory.txt). A station with fewer than 20 complete years is skipped, never filled.
Run:  PYTHONPATH=. .venv/bin/python scripts/ingest_ghcn_extremes.py
"""
from __future__ import annotations

import json
import time

import h3
import numpy as np
import requests
from sqlalchemy import text

from core.db.session import get_session

URL = "https://www.ncei.noaa.gov/access/services/data/v1"
SEL = "data/ghcn/stations_selected.json"


def fetch(sid: str) -> list[dict]:
    for attempt in range(3):
        try:
            r = requests.get(URL, params={"dataset": "daily-summaries", "stations": sid, "startDate": "1991-01-01", "endDate": "2020-12-31",
                                          "dataTypes": "TMIN,TMAX,PRCP", "format": "json", "units": "metric"}, timeout=120)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(2 + 3 * attempt)
    return []


def extremes(rows: list[dict]) -> dict | None:
    by_year: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        y = r["DATE"][:4]
        d = by_year.setdefault(y, {"TMIN": [], "TMAX": [], "PRCP": []})
        for k in ("TMIN", "TMAX", "PRCP"):
            v = r.get(k)
            if v not in (None, ""):
                try:
                    d[k].append(float(v))
                except ValueError:
                    pass
    full = [y for y, d in by_year.items() if len(d["TMIN"]) >= 330 and len(d["TMAX"]) >= 330 and len(d["PRCP"]) >= 330]
    if len(full) < 20:
        return None
    tmin_all = np.array([v for y in full for v in by_year[y]["TMIN"]])
    ann_min = np.array(sorted(min(by_year[y]["TMIN"]) for y in full))
    ann_tmax = np.array([max(by_year[y]["TMAX"]) for y in full])
    hot = np.array([sum(1 for v in by_year[y]["TMAX"] if v >= 30.0) for y in full])
    p1 = np.array([max(by_year[y]["PRCP"]) for y in full])
    wet = np.array([v for y in full for v in by_year[y]["PRCP"] if v >= 1.0])
    return {"n_years": len(full), "coldest_1in10_c": float(np.quantile(ann_min, 0.10)), "design_c": float(np.quantile(tmin_all, 0.004)),
            "tmax_annual_max_c": float(ann_tmax.mean()), "hot_days_per_yr": float(hot.mean()), "prcp_1day_max_mm": float(p1.mean()),
            "prcp_p99_mm": float(np.quantile(wet, 0.99)) if len(wet) > 50 else None}


def main() -> None:
    sel = json.load(open(SEL))
    t0 = time.time(); n_ok = n_skip = 0
    with get_session() as s:
        done = {r[0] for r in s.execute(text("SELECT station_id FROM station_extremes")).fetchall()}
        for region, stations in sel.items():
            for sid, lat, lon, name in stations:
                if sid in done:
                    continue
                ex = extremes(fetch(sid))
                if not ex:
                    n_skip += 1; continue
                s.execute(text("""INSERT INTO station_extremes (station_id, name, region, latitude, longitude, h3_cell, n_years, coldest_1in10_c, design_c, tmax_annual_max_c,
                                                                hot_days_per_yr, prcp_1day_max_mm, prcp_p99_mm, source)
                                  VALUES (:sid, :name, :reg, :lat, :lon, :cell, :n, :c10, :dc, :tx, :hd, :p1, :p99, 'NOAA NCEI GHCN-Daily daily-summaries 1991-2020')
                                  ON CONFLICT (station_id) DO NOTHING"""),
                          {"sid": sid, "name": name, "reg": region, "lat": lat, "lon": lon, "cell": h3.latlng_to_cell(lat, lon, 8), "n": ex["n_years"], "c10": ex["coldest_1in10_c"], "dc": ex["design_c"],
                           "tx": ex["tmax_annual_max_c"], "hd": ex["hot_days_per_yr"], "p1": ex["prcp_1day_max_mm"], "p99": ex["prcp_p99_mm"]})
                s.commit(); n_ok += 1
                if n_ok % 25 == 0:
                    print(f"  {n_ok} stations · {time.time()-t0:.0f}s", flush=True)
    print(f"done: {n_ok} stations ingested, {n_skip} skipped (<20 complete years), {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
