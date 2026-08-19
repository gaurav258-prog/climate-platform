"""
Global tropical-cyclone track ingester — IBTrACS (NOAA/NCEI) -> storm_events,
ALL basins, a real historical window. Extends scripts/ingest_ibtracs_storm.py's
single-curated-storm scope (kept as-is, still the Hurricane Maria backtest
ingester) to genuine global coverage, the same move already made for seismic
(scripts/ingest_usgs_seismic.py --days 3650 --min-mag 5.0, 259 -> 17,939 rows).

No server-side date/basin filtering exists on IBTrACS's flat-file archive
(confirmed: only a single combined "ALL basins, full 1842-present history"
CSV, ~330MB) -- downloaded once, filtered client-side to a recent window and
a minimum intensity, same pattern as the seismic ingester's own min-magnitude
cutoff.

  python scripts/ingest_ibtracs_global.py --years 10 --min-wind 34
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

import h3
import pandas as pd
import requests
from sqlalchemy import text

from core.db.session import get_session

IBTRACS_ALL_CSV = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/"
    "v04r01/access/csv/ibtracs.ALL.list.v04r01.csv"
)
NMI_TO_KM = 1.852
LOCAL_PATH = "/tmp/ibtracs_all.csv"


def download(path: str = LOCAL_PATH) -> str:
    import os
    if os.path.exists(path):
        print(f"[fetch] using cached {path}")
        return path
    print("[fetch] downloading IBTrACS ALL-basins archive (~330MB, one-time)...")
    r = requests.get(IBTRACS_ALL_CSV, timeout=300, stream=True)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    print(f"[fetch] saved to {path}")
    return path


def load_filtered(path: str, min_season: int, min_wind: float) -> pd.DataFrame:
    """Row 0 is the header, row 1 is a units row (not data) -- skip it. Read in
    chunks and filter as we go so we never hold the full 330MB parsed in memory
    at once.

    keep_default_na=False is load-bearing, not cosmetic: pandas' default null
    detection treats the literal string "NA" as a missing value -- which is
    also IBTrACS's basin code for North Atlantic. Confirmed live: without this,
    every North Atlantic storm's BASIN silently becomes NaN instead of "NA"
    (8,329 real North Atlantic track points mislabeled in an early run of this
    exact script, caught by checking the basin distribution rather than
    assuming the ingest was clean)."""
    cols = ["SID", "SEASON", "BASIN", "NAME", "ISO_TIME", "LAT", "LON",
            "USA_WIND", "USA_PRES", "USA_RMW", "USA_SSHS"]
    chunks = []
    reader = pd.read_csv(path, skiprows=[1], usecols=cols, dtype=str,
                          keep_default_na=False, na_values=[""],
                          chunksize=200_000, low_memory=False)
    for chunk in reader:
        chunk["SEASON_NUM"] = pd.to_numeric(chunk["SEASON"], errors="coerce")
        chunk["WIND_NUM"] = pd.to_numeric(chunk["USA_WIND"], errors="coerce")
        keep = chunk[(chunk["SEASON_NUM"] >= min_season) & (chunk["WIND_NUM"] >= min_wind)]
        if not keep.empty:
            chunks.append(keep)
    if not chunks:
        return pd.DataFrame(columns=cols)
    return pd.concat(chunks, ignore_index=True)


def _f(v):
    try:
        return float(v) if v not in (None, "", "nan") else None
    except (TypeError, ValueError):
        return None


def upsert(df: pd.DataFrame, source_tag: str = "IBTrACS-global") -> int:
    records = []
    for i, row in enumerate(df.itertuples(index=False)):
        lat, lon = _f(row.LAT), _f(row.LON)
        if lat is None or lon is None:
            continue
        rmw_nmi = _f(row.USA_RMW)
        sshs = _f(row.USA_SSHS)
        try:
            obs_time = datetime.strptime(row.ISO_TIME, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        records.append({
            "event_id": f"ibtracs_{row.SID}_{i:05d}",
            "storm_id": row.SID, "storm_name": (row.NAME or "UNNAMED").strip(),
            "season_year": int(row.SEASON_NUM) if pd.notna(row.SEASON_NUM) else None,
            "basin": row.BASIN, "obs_time": obs_time, "lat": round(lat, 5), "lon": round(lon, 5),
            "h3": h3.latlng_to_cell(lat, lon, 8),
            "wind_kt": _f(row.USA_WIND), "pres_mb": _f(row.USA_PRES),
            "rmw_km": round(rmw_nmi * NMI_TO_KM, 2) if rmw_nmi else None,
            "sshs": int(sshs) if sshs is not None else None,
        })
    if not records:
        return 0
    with get_session() as s:
        # dedupe: same convention as ingest_ibtracs_storm.py -- replace this
        # storm_id's existing rows entirely rather than trying to merge
        storm_ids = list({r["storm_id"] for r in records})
        for i in range(0, len(storm_ids), 500):
            batch_ids = storm_ids[i:i + 500]
            s.execute(text("DELETE FROM storm_events WHERE storm_id = ANY(:ids)"), {"ids": batch_ids})
        batch = 20_000
        for i in range(0, len(records), batch):
            s.execute(text("""
                INSERT INTO storm_events
                    (event_id, storm_id, storm_name, season_year, basin, observation_time,
                     lat, lon, h3_cell, max_wind_kt, central_pressure_mb, rmw_km, sshs_category,
                     source_catalog, ingested_at)
                VALUES
                    (:event_id, :storm_id, :storm_name, :season_year, :basin, :obs_time,
                     :lat, :lon, :h3, :wind_kt, :pres_mb, :rmw_km, :sshs, :source, now())
                ON CONFLICT (event_id) DO NOTHING
            """), [{**r, "source": source_tag} for r in records[i:i + batch]])
    return len(records)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=10, help="how many recent seasons to ingest")
    ap.add_argument("--min-wind", type=float, default=34.0, help="min USA_WIND (kt) -- 34kt = tropical storm strength")
    a = ap.parse_args()

    this_year = datetime.now(timezone.utc).year
    min_season = this_year - a.years

    path = download()
    print(f"[filter] season >= {min_season}, USA_WIND >= {a.min_wind}kt...")
    df = load_filtered(path, min_season, a.min_wind)
    print(f"[filter] {len(df)} track points across {df['SID'].nunique() if len(df) else 0} storms")

    n = upsert(df)
    print(f"[done] {n} track points ingested/updated in storm_events")


if __name__ == "__main__":
    main()
