"""
Global earthquake ingester — USGS FDSN feed → seismic_events.

The EMSC adapter only covers Europe (lat 34-71, lon -30..45), so it misses events
like the 2026-06-24 M7.5 Venezuela sequence. USGS is the authoritative global
catalog. This ingests recent significant quakes worldwide (default M>=4.5),
upserting by USGS event id so re-runs only add/refresh.

  python scripts/ingest_usgs_seismic.py                 # last 7 days, global, M>=4.5
  python scripts/ingest_usgs_seismic.py --days 14 --min-mag 4.0
  python scripts/ingest_usgs_seismic.py --watch 60      # poll every 60s (constantly updated)
  python scripts/ingest_usgs_seismic.py --bbox 0 14 -74 -59   # Venezuela region only

'constantly updated' in production = run --watch under a process manager, or
schedule this script (cron / scheduled_task) every minute.
"""
import argparse
import time
from datetime import datetime, timedelta, timezone

import h3
import requests
from sqlalchemy import text

from core.db.session import get_session

USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def fetch(days: int, min_mag: float, bbox=None) -> list[dict]:
    params = {
        "format": "geojson",
        "starttime": (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d"),
        "minmagnitude": min_mag,
        "orderby": "time",
    }
    if bbox:  # [minlat, maxlat, minlon, maxlon]
        params.update(minlatitude=bbox[0], maxlatitude=bbox[1],
                      minlongitude=bbox[2], maxlongitude=bbox[3])
    r = requests.get(USGS, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("features", [])


def upsert(features: list[dict]) -> tuple[int, int]:
    rows = []
    for f in features:
        p = f["properties"]; lon, lat, depth = f["geometry"]["coordinates"]
        if p.get("mag") is None:
            continue
        rows.append({
            "event_id": "usgs_" + f["id"],
            "magnitude": round(float(p["mag"]), 2),
            "mag_type": p.get("magType"),
            "depth_km": float(depth) if depth is not None else None,
            "lat": round(float(lat), 5), "lon": round(float(lon), 5),
            "h3": h3.latlng_to_cell(float(lat), float(lon), 8),
            "origin_time": datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc),
            "region": p.get("place"),
            "status": p.get("status", "automatic"),
        })
    if not rows:
        return 0, 0
    with get_session() as s:
        before = s.execute(text("SELECT count(*) FROM seismic_events")).scalar()
        s.execute(text("""
            INSERT INTO seismic_events
                (event_id, magnitude, mag_type, depth_km, epicentre_lat, epicentre_lon,
                 epicentre_h3, origin_time, region_name, source_catalog, review_status,
                 ingested_at, damage_assessment_status)
            VALUES
                (:event_id, :magnitude, :mag_type, :depth_km, :lat, :lon,
                 :h3, :origin_time, :region, 'USGS', :status, now(), 'pending')
            ON CONFLICT (event_id) DO UPDATE
                SET magnitude = EXCLUDED.magnitude,
                    review_status = EXCLUDED.review_status,
                    depth_km = EXCLUDED.depth_km
        """), rows)
        after = s.execute(text("SELECT count(*) FROM seismic_events")).scalar()
    return len(rows), after - before


def run_once(days, min_mag, bbox):
    feats = fetch(days, min_mag, bbox)
    seen, added = upsert(feats)
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] USGS: {len(feats)} events, {seen} stored, {added} new")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-mag", type=float, default=4.5)
    ap.add_argument("--bbox", type=float, nargs=4, default=None,
                    help="minlat maxlat minlon maxlon")
    ap.add_argument("--watch", type=int, default=0, help="poll interval seconds (0 = once)")
    a = ap.parse_args()
    if a.watch:
        print(f"watching USGS every {a.watch}s (Ctrl-C to stop) …")
        while True:
            try:
                run_once(a.days, a.min_mag, a.bbox)
            except Exception as e:
                print(f"  poll error: {str(e)[:120]}")
            time.sleep(a.watch)
    else:
        run_once(a.days, a.min_mag, a.bbox)


if __name__ == "__main__":
    main()
