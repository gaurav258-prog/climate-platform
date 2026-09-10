"""GESLA-3 tide gauges → observed monthly extreme still-water levels (the coastal-flood channel's site term + target).

Source: the GESLA-3 hourly sea-level compilation (Haigh et al. 2023) served by the University of Hawaii Sea Level
Center ERDDAP (`global_hourly_gesla`, 6.5k records, 100+ agencies incl. NOAA, RWS, WSV, BOM, CMEMS). Per record we
ask the server for the monthly MAXIMUM and monthly MEAN of the quality-flagged hourly series 1979–2020 (two
`orderBy` queries; the server does the aggregation, ~3 s each). Datums differ by provider, so every level is later
expressed relative to the record's own mean sea level. Lands data/tide_gauges/gesla_monthly.csv (git-ignored,
resumable) and loads table `tide_gauge_extremes`.

Usage: PYTHONPATH=. .venv/bin/python scripts/ingest_gesla_extremes.py [--threads 8] [--load-only]
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

BASE = "https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_gesla.csv"
OUT = Path("data/tide_gauges/gesla_monthly.csv")
DONE = Path("data/tide_gauges/gesla_done.txt")
Y0, Y1 = 1979, 2020
COLS = ["record_id", "station_name", "country", "agency", "lat", "lon", "year", "month", "max_m", "mean_m"]
_lock = threading.Lock()


def _get(query: str, tries: int = 3) -> list[list[str]]:
    for i in range(tries):
        try:
            r = requests.get(BASE + query, timeout=120)
            if r.status_code == 404:                       # "no matching results": an empty window, not an error
                return []
            r.raise_for_status()
            rows = list(csv.reader(io.StringIO(r.text)))
            return rows[2:]                                # header + units rows
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
    return []


def records() -> list[dict]:
    rows = _get("?record_id,station_name,station_country_code,agency_id,latitude,longitude&distinct()")
    out = []
    for rid, name, cc, ag, la, lo in rows:
        lon = float(lo)
        out.append({"record_id": rid, "station_name": name, "country": cc, "agency": ag,
                    "lat": float(la), "lon": lon - 360.0 if lon > 180 else lon})
    return out


def _monthly(rid: str, agg: str) -> dict[tuple[int, int], float]:
    order = 'orderByMax("record_id,time/1month,sea_level")' if agg == "max" else 'orderByMean("record_id,time/1month")'
    q = (f'?record_id,time,sea_level&record_id="{rid}"&time>={Y0}-01-01&time<{Y1 + 1}-01-01'
         f'&sea_level!=NaN&flag2=1&{order}')
    return {(int(t[:4]), int(t[5:7])): float(v) for _, t, v in _get(q) if v not in ("", "NaN")}


def pull(rec: dict, done: set) -> int:
    if rec["record_id"] in done:
        return 0
    mx, mn = _monthly(rec["record_id"], "max"), _monthly(rec["record_id"], "mean")
    rows = [[rec["record_id"], rec["station_name"], rec["country"], rec["agency"], rec["lat"], rec["lon"],
             y, m, mx[(y, m)], mn.get((y, m))] for (y, m) in sorted(mx) if (y, m) in mn]
    with _lock:
        with OUT.open("a", newline="") as f:
            csv.writer(f).writerows(rows)
        with DONE.open("a") as f:
            f.write(rec["record_id"] + "\n")
    return len(rows)


def load() -> None:
    import pandas as pd
    from sqlalchemy import text

    from core.db.session import get_session
    d = pd.read_csv(OUT, names=COLS, header=None)
    d = d.dropna(subset=["max_m", "mean_m"]).drop_duplicates(["record_id", "year", "month"])
    # GESLA carries river, estuary and marsh gauges (USGS, CRMS, WSV inland stations); tag every location with its
    # distance to the coastline so the channel can read sea gauges only. Same coastline as the coastal scorer.
    import h3
    from shapely.geometry import Point
    from shapely.ops import nearest_points

    from ml.scoring.coastal_flood_point import _coastline
    coast = _coastline()
    dist: dict[tuple, float] = {}
    for la, lo in d[["lat", "lon"]].drop_duplicates().itertuples(index=False):
        near = nearest_points(coast, Point(lo, la))[0]
        dist[(la, lo)] = float(h3.great_circle_distance((la, lo), (near.y, near.x), unit="km"))
    d["dist_to_coast_km"] = [round(dist[(la, lo)], 2) for la, lo in zip(d.lat, d.lon)]
    with get_session() as s:
        s.execute(text("DELETE FROM tide_gauge_extremes"))
        payload = d.to_dict("records")
        for i in range(0, len(payload), 5000):
            s.execute(text("""INSERT INTO tide_gauge_extremes (record_id, station_name, country, agency, lat, lon, year, month, max_m, mean_m, dist_to_coast_km)
                              VALUES (:record_id,:station_name,:country,:agency,:lat,:lon,:year,:month,:max_m,:mean_m,:dist_to_coast_km)"""), payload[i:i + 5000])
        n = s.execute(text("SELECT count(*), count(DISTINCT record_id) FROM tide_gauge_extremes")).first()
    print(f"loaded tide_gauge_extremes: {n[0]} station-months over {n[1]} records")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--load-only", action="store_true")
    a = ap.parse_args()
    if not a.load_only:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        done = set(DONE.read_text().split()) if DONE.exists() else set()
        recs = records()
        todo = [r for r in recs if r["record_id"] not in done]
        print(f"{len(recs)} GESLA records, {len(todo)} to pull", flush=True)
        t0 = time.time(); n = [0]
        with ThreadPoolExecutor(a.threads) as ex:
            for i, k in enumerate(ex.map(lambda r: pull(r, done), todo)):
                n[0] += k
                if i % 200 == 0:
                    print(f"  {i}/{len(todo)} records · {n[0]} station-months · {time.time() - t0:.0f}s", flush=True)
        print(f"pulled {n[0]} station-months in {time.time() - t0:.0f}s")
    load()
    return 0


if __name__ == "__main__":
    sys.exit(main())
