"""
Tropical-cyclone track ingester — IBTrACS (NOAA/NCEI) -> storm_events.

IBTrACS logs one row per ~3-6 hourly track observation (position + intensity), unlike
GVP's coarse multi-year eruption episodes — a storm's whole lifetime is naturally
already broken into individual dated events, so no external "which date exactly"
knowledge is needed the way volcanic needed Fuego's 2018-06-03 paroxysm date.

Scoped to a curated backtest storm (Hurricane Maria, 2017), not a global bulk pull of
IBTrACS's entire multi-basin archive — this is a demo/backtest ingester, not a
monitoring feed. No live near-real-time equivalent exists in this same no-auth style
(disclosed limitation, same class as volcanic's GVP-catalog-only gap).

  python scripts/ingest_ibtracs_storm.py                      # Hurricane Maria (default)
  python scripts/ingest_ibtracs_storm.py --sid 2017260N12310   # explicit IBTrACS SID
"""
from __future__ import annotations

import argparse
import csv
import io
from datetime import datetime, timezone

import h3
import requests
from sqlalchemy import text

from core.db.session import get_session

IBTRACS_NA_CSV = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/"
    "v04r01/access/csv/ibtracs.NA.list.v04r01.csv"
)
NMI_TO_KM = 1.852

# Curated backtest storm set (see docs/STORM_HAZARD_METHODOLOGY.md).
DEFAULT_SID = "2017260N12310"  # Hurricane Maria, 2017 -- IBTrACS SID (NOT the NHC 'AL152017' label)


def _f(v):
    v = (v or "").strip()
    return float(v) if v else None


def fetch_track(sid: str) -> list[dict]:
    r = requests.get(IBTRACS_NA_CSV, timeout=90)
    r.raise_for_status()
    lines = r.text.splitlines()
    header = lines[0].split(",")
    # line[1] is the units row -- data starts at line[2]
    reader = csv.DictReader(lines[2:], fieldnames=header)
    return [row for row in reader if row.get("SID") == sid]


def upsert(sid: str, rows: list[dict]) -> tuple[int, int]:
    if not rows:
        return 0, 0
    name = (rows[0].get("NAME") or "UNNAMED").strip()
    season = rows[0].get("SEASON")
    basin = rows[0].get("BASIN")
    records = []
    for i, row in enumerate(rows):
        lat, lon = _f(row["LAT"]), _f(row["LON"])
        if lat is None or lon is None:
            continue
        rmw_nmi = _f(row.get("USA_RMW"))
        records.append({
            "event_id": f"ibtracs_{sid}_{i:03d}",
            "storm_id": sid, "storm_name": name,
            "season_year": int(season) if season else None, "basin": basin,
            "obs_time": datetime.strptime(row["ISO_TIME"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc),
            "lat": round(lat, 5), "lon": round(lon, 5),
            "h3": h3.latlng_to_cell(lat, lon, 8),
            "wind_kt": _f(row.get("USA_WIND")),
            "pres_mb": _f(row.get("USA_PRES")),
            "rmw_km": round(rmw_nmi * NMI_TO_KM, 2) if rmw_nmi else None,
            "sshs": int(_f(row.get("USA_SSHS"))) if row.get("USA_SSHS") not in (None, "") else None,
        })
    with get_session() as s:
        before = s.execute(text("SELECT count(*) FROM storm_events WHERE storm_id = :sid"), {"sid": sid}).scalar()
        s.execute(text("DELETE FROM storm_events WHERE storm_id = :sid"), {"sid": sid})
        s.execute(text("""
            INSERT INTO storm_events
                (event_id, storm_id, storm_name, season_year, basin, observation_time,
                 lat, lon, h3_cell, max_wind_kt, central_pressure_mb, rmw_km, sshs_category,
                 source_catalog, ingested_at)
            VALUES
                (:event_id, :storm_id, :storm_name, :season_year, :basin, :obs_time,
                 :lat, :lon, :h3, :wind_kt, :pres_mb, :rmw_km, :sshs, 'IBTrACS', now())
        """), records)
        after = s.execute(text("SELECT count(*) FROM storm_events WHERE storm_id = :sid"), {"sid": sid}).scalar()
    return len(records), after - before


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sid", default=DEFAULT_SID, help="IBTrACS storm SID (default: Hurricane Maria 2017)")
    a = ap.parse_args()
    print(f"[IBTrACS] pulling track for SID={a.sid} from NOAA/NCEI …")
    rows = fetch_track(a.sid)
    if not rows:
        print(f"  no rows found for SID {a.sid}"); return
    seen, added = upsert(a.sid, rows)
    peak = max((r for r in rows if _f(r.get("USA_WIND"))), key=lambda r: _f(r["USA_WIND"]))
    print(f"  {rows[0]['NAME'].strip()} ({a.sid}): {len(rows)} track points, {seen} stored, {added} new")
    print(f"  peak: {peak['ISO_TIME']} @ ({peak['LAT']},{peak['LON']}) "
          f"{peak['USA_WIND']}kt Cat{peak['USA_SSHS']}, {peak['USA_PRES']}mb")


if __name__ == "__main__":
    main()
