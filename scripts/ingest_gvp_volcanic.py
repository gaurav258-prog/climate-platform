"""
Volcano + eruption catalog ingester — Smithsonian Global Volcanism Program (GVP)
GeoServer WFS -> volcanic_events.

Unlike EMSC/USGS (discrete origin-time events) GVP's Holocene_Eruptions layer logs
eruptive EPISODES, which can span years for a persistently active volcano. Fuego
(Guatemala) is the clearest case: its whole 2002-present episode is ONE row
(VEI 3 max) — the catastrophic June 3, 2018 pyroclastic-flow paroxysm is a
sub-episode within it, not a separately dated GVP record. So this ingester stores
the episode as-is (start/end year/month/day, VEI) — the specific backtest date
(e.g. 2018-06-03 for Fuego) is supplied separately to scripts/score_volcanic_event.py,
not read from this catalog. Documented explicitly so nobody assumes GVP gives
daily eruption dating it doesn't.

Scoped to a small curated volcano list (the backtest set), not a global pull of
~1500 Holocene volcanoes — this is a demo/backtest ingester, not a monitoring feed.

The GeoServer at webservices.volcano.si.edu 403s/challenges requests without a
browser-like User-Agent (Cloudflare bot protection) — a plain User-Agent header
is required, no API key.

  python scripts/ingest_gvp_volcanic.py                       # curated default set (Fuego, Taal)
  python scripts/ingest_gvp_volcanic.py --volcano-number 342090   # just Fuego
"""
from __future__ import annotations

import argparse

import h3
import requests
from sqlalchemy import text

from core.db.session import get_session

GVP_WFS = "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TellumenClimatePlatform/1.0)"}

# Curated backtest volcano set (see docs/VOLCANIC_HAZARD_METHODOLOGY.md).
DEFAULT_VOLCANOES = {
    342090: "Fuego",   # Guatemala — primary backtest (2018-06-03 paroxysm)
    273070: "Taal",    # Philippines — secondary backtest (2020-01 eruption)
}


def _wfs_get(type_name: str, cql_filter: str) -> list[dict]:
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeName": type_name, "outputFormat": "application/json",
        "CQL_FILTER": cql_filter,
    }
    r = requests.get(GVP_WFS, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("features", [])


def fetch_volcano(volcano_number: int) -> dict | None:
    feats = _wfs_get(
        "GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes",
        f"Volcano_Number={volcano_number}",
    )
    return feats[0]["properties"] if feats else None


def fetch_eruptions(volcano_number: int) -> list[dict]:
    feats = _wfs_get(
        "GVP-VOTW:Smithsonian_VOTW_Holocene_Eruptions",
        f"Volcano_Number={volcano_number}",
    )
    return [f["properties"] for f in feats]


def upsert(volcano_number: int, volcano_name: str, lat: float, lon: float,
           eruptions: list[dict]) -> tuple[int, int]:
    rows = []
    for e in eruptions:
        rows.append({
            "event_id": f"gvp_{volcano_number}_{e['Eruption_Number']}",
            "volcano_number": volcano_number,
            "volcano_name": volcano_name,
            "vei": e.get("ExplosivityIndexMax"),
            "activity_type": e.get("Activity_Type"),
            "start_year": e.get("StartDateYear"),
            "start_month": e.get("StartDateMonth") or None,
            "start_day": e.get("StartDateDay") or None,
            "end_year": e.get("EndDateYear"),
            "end_month": e.get("EndDateMonth") or None,
            "end_day": e.get("EndDateDay") or None,
            "lat": round(lat, 5), "lon": round(lon, 5),
            "h3": h3.latlng_to_cell(lat, lon, 8),
        })
    if not rows:
        return 0, 0
    with get_session() as s:
        before = s.execute(text("SELECT count(*) FROM volcanic_events")).scalar()
        s.execute(text("""
            INSERT INTO volcanic_events
                (event_id, volcano_number, volcano_name, vei, activity_type,
                 start_year, start_month, start_day, end_year, end_month, end_day,
                 epicentre_lat, epicentre_lon, epicentre_h3, source_catalog, ingested_at)
            VALUES
                (:event_id, :volcano_number, :volcano_name, :vei, :activity_type,
                 :start_year, :start_month, :start_day, :end_year, :end_month, :end_day,
                 :lat, :lon, :h3, 'GVP', now())
            ON CONFLICT (event_id) DO UPDATE
                SET vei = EXCLUDED.vei,
                    end_year = EXCLUDED.end_year,
                    end_month = EXCLUDED.end_month,
                    end_day = EXCLUDED.end_day
        """), rows)
        after = s.execute(text("SELECT count(*) FROM volcanic_events")).scalar()
    return len(rows), after - before


def run_once(volcano_number: int, volcano_name: str | None = None):
    v = fetch_volcano(volcano_number)
    if not v:
        print(f"  volcano {volcano_number}: not found in GVP catalog")
        return 0
    name = v["Volcano_Name"]
    lat, lon = v["Latitude"], v["Longitude"]
    eruptions = fetch_eruptions(volcano_number)
    seen, added = upsert(volcano_number, name, lat, lon, eruptions)
    print(f"  {name} ({volcano_number}) @ ({lat:.4f},{lon:.4f}): "
          f"{len(eruptions)} eruption episodes, {seen} stored, {added} new")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--volcano-number", type=int, default=None,
                     help="pull just this GVP volcano number (default: curated set)")
    a = ap.parse_args()
    print("[GVP] pulling eruption catalog from Smithsonian Global Volcanism Program …")
    targets = {a.volcano_number: None} if a.volcano_number else DEFAULT_VOLCANOES
    for num in targets:
        run_once(num)


if __name__ == "__main__":
    main()
