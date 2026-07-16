"""Ingest REAL crop production/area/yield labels from Eurostat into crop_yield_observations.

WHY. The whole COGS-at-risk chain is calibrated against crop-failure labels, and we had
THIRTEEN — hand-typed from ICCO/COCOBOD/USDA press figures, covering two crops. That label
set, not the hazard data, is what caps the product at two backtested crops. FAOSTAT's API
now returns 401 (it previously 521'd) and USDA PSD returns 403, but Eurostat's dissemination
API is open, keyless and carries exactly the crops the demo book holds — with ~26 years of
history per crop per country.

  dataset : apro_cpsh1 "Crop production in EU standard humidity"
  measures: AR_THS_HA (area, kha) · HPRD_HUMD_EU_THS_T (production, kt) · YLD_HUMD_EU_T_HA
  licence : Eurostat open data, free reuse with attribution

HONESTY NOTE THAT MATTERS FOR CALIBRATION. A big negative year is NOT automatically a climate
signal. Spanish olives alternate-bear hard (2012 -53%, 2013 +154%, 2014 -53%, 2018 +54%,
2019 -39%) — a biennial cycle with no weather in it. Wine grapes and almonds do this too.
So we ingest the raw series and let the backtest decompose the biennial component from the
climate component; we never hand a -52% year straight to a drought coefficient.

    python -m scripts.ingest_crop_yield_eurostat            # all mapped crops, all countries
    python -m scripts.ingest_crop_yield_eurostat --commodity "Olive oil"
    python -m scripts.ingest_crop_yield_eurostat --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

from sqlalchemy import text

from core.db.session import get_session

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpsh1"
SOURCE = "EUROSTAT apro_cpsh1"

# our sc_commodities name -> Eurostat crop code. Only crops we actually hold; adding a crop
# here is a one-line change, not a new script.
CROP_MAP = {
    "Olive oil":   "O1910",   # Olives for oil (not table olives)
    "Citrus":      "T0000",   # Citrus fruits
    "Durum wheat": "C1120",   # Durum wheat
    "Wine grapes": "W1100",   # Grapes for wines
    "Almonds":     "F4300",   # Almonds
    "Sugar beet":  "R2000",   # Sugar beet (excluding seed)
}

# The origins we care about + the other big EU producers, which give the world-share context
# a per-origin calibration needs.
GEOS = ["ES", "PT", "IT", "EL", "FR", "DE", "EU27_2020"]

MEASURES = {
    "area_kha":        "AR_THS_HA",
    "production_kt":   "HPRD_HUMD_EU_THS_T",
    "yield_t_ha":      "YLD_HUMD_EU_T_HA",
}

# crop_yield_observations.country is the ISO-2 origin (varchar 3). Eurostat's aggregate geo
# is 'EU27_2020'; store it as 'EU' and keep the exact source geo in the note.
GEO_TO_COUNTRY = {"EU27_2020": "EU", "EL": "GR"}   # EL is Eurostat's code for Greece


def _country(geo: str) -> str:
    return GEO_TO_COUNTRY.get(geo, geo)


def _fetch(crop_code: str, measure: str) -> dict:
    q = urllib.parse.urlencode({"format": "JSON", "crops": crop_code, "strucpro": measure}, safe="")
    url = f"{BASE}?{q}&" + "&".join(f"geo={g}" for g in GEOS)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (tellumen-crop-ingest)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _series(doc: dict) -> dict:
    """JSON-stat -> {(geo, year): value}. The value map is keyed by a flat index over the
    dimension sizes, so we decode it rather than assuming a shape."""
    ids, size = doc["id"], doc["size"]
    idx = {d: doc["dimension"][d]["category"]["index"] for d in ids}
    inv = {d: {v: k for k, v in idx[d].items()} for d in ids}
    out = {}
    for flat, val in doc.get("value", {}).items():
        rem, coords = int(flat), []
        for dim_size in reversed(size):
            coords.append(rem % dim_size)
            rem //= dim_size
        coords.reverse()
        pos = dict(zip(ids, coords))
        out[(inv["geo"][pos["geo"]], inv["time"][pos["time"]])] = val
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commodity", help="only this commodity (default: all mapped)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    crops = {args.commodity: CROP_MAP[args.commodity]} if args.commodity else CROP_MAP
    total = 0

    for commodity, code in crops.items():
        data = {}
        for field, measure in MEASURES.items():
            try:
                data[field] = _series(_fetch(code, measure))
            except Exception as e:
                print(f"  ! {commodity}/{measure}: {type(e).__name__}: {e}")
                data[field] = {}

        keys = sorted(set().union(*[set(d) for d in data.values()]) if any(data.values()) else [])
        # year-on-year is computed per (commodity, country) series, in year order
        by_geo: dict = {}
        for geo, year in keys:
            by_geo.setdefault(geo, []).append(year)

        rows = []
        for geo, years in by_geo.items():
            for year in sorted(years):
                prod = data["production_kt"].get((geo, year))
                prev = data["production_kt"].get((geo, str(int(year) - 1)))
                yoy = round((prod - prev) / prev * 100, 2) if (prod and prev) else None
                rows.append({
                    "c": commodity, "geo": _country(geo), "yr": int(year),
                    # Eurostat publishes thousands; crop_yield_observations stores absolutes
                    "prod": round(prod * 1000, 3) if prod is not None else None,
                    "area": round(data["area_kha"].get((geo, year)) * 1000, 3)
                            if data["area_kha"].get((geo, year)) is not None else None,
                    "yld": data["yield_t_ha"].get((geo, year)),
                    "yoy": yoy,
                    "note": f"Eurostat apro_cpsh1 crop={code} geo={geo}",
                })

        print(f"{commodity:12s} ({code}): {len(rows)} country-years "
              f"[{min((r['yr'] for r in rows), default='-')}..{max((r['yr'] for r in rows), default='-')}]")
        if not args.dry_run and rows:
            with get_session() as s:
                for r in rows:
                    s.execute(text("""
                        INSERT INTO crop_yield_observations
                            (commodity, country, season_year, production_tonnes, area_harvested_ha,
                             yield_tonnes_ha, yoy_change_pct, source, note)
                        VALUES (:c, :geo, :yr, :prod, :area, :yld, :yoy, :src, :note)
                        ON CONFLICT (commodity, country, season_year, source) DO UPDATE SET
                            production_tonnes = EXCLUDED.production_tonnes,
                            area_harvested_ha = EXCLUDED.area_harvested_ha,
                            yield_tonnes_ha   = EXCLUDED.yield_tonnes_ha,
                            yoy_change_pct    = EXCLUDED.yoy_change_pct,
                            note              = EXCLUDED.note,
                            ingested_at       = now()
                    """), {**r, "src": SOURCE})
        total += len(rows)

    print(f"\n{total} country-year labels {'(dry run)' if args.dry_run else 'ingested'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
