"""Ingest GLOBAL crop production/area/yield labels from the FAOSTAT bulk download.

WHY. Eurostat gave us the EU crops, but the crops that actually publish euros today (cocoa
West Africa, coffee Brazil) and every Tier-1 global crop (palm, soy, cane sugar, rice) are
outside the EU. FAOSTAT's *API* returns 401 and USDA PSD's returns 403 — but the FAOSTAT
BULK download is wide open, and it is the real prize: every country x crop x year, 1961-2024.

  dataset : Production_Crops_Livestock_E_All_Data_(Normalized).zip  (~34 MB)
  elements: Production (t) · Area harvested (ha) · Yield
  licence : FAO CC BY 4.0 (attribution required)

TWO TRAPS THIS FILE HANDLES, both of which fail SILENTLY:

1. ENCODING. The CSV is UTF-8. Read as latin-1, "Côte d'Ivoire" becomes "CÃ´te d'Ivoire"
   and simply stops matching — you lose ~45% of world cocoa with no error, no warning. We
   read utf-8-sig and match on FAO's numeric Area Code, never on the display name.

2. SEASON vs CALENDAR YEAR. FAO reports CALENDAR years. Cocoa/coffee trade on split seasons
   (cocoa 2023/24 = Oct-Sep). FAO's 2023 CI cocoa is -22.7%; our curated label for the
   2023/24 season is -23.9% (USDA FAS) — the same event under two conventions. We store the
   FAO calendar year as-is and say so in `note` + a distinct `source`, so a backtest can
   align deliberately instead of silently comparing the wrong year against a coefficient.

    python -m scripts.ingest_crop_yield_faostat --dry-run
    python -m scripts.ingest_crop_yield_faostat --commodity Cocoa
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import urllib.request
import zipfile

from sqlalchemy import text

from core.db.session import get_session

URL = ("https://bulks-faostat.fao.org/production/"
       "Production_Crops_Livestock_E_All_Data_(Normalized).zip")
CACHE = "data/faostat/Production_Crops_Livestock_E_All_Data_(Normalized).zip"
SOURCE = "FAOSTAT QCL bulk"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

# our commodity name -> FAO item name. FAO item names are stable; we still resolve areas by
# NUMERIC code (below) because THOSE are what the accents break.
ITEM_MAP = {
    "Cocoa":       "Cocoa beans",
    "Coffee":      "Coffee, green",
    "Palm oil":    "Oil palm fruit",
    "Soybean":     "Soya beans",
    "Cane sugar":  "Sugar cane",
    "Sugar beet":  "Sugar beet",
    "Rice":        "Rice",
    "Wheat":       "Wheat",
    "Maize":       "Maize (corn)",
    "Olive oil":   "Olives",
    "Almonds":     "Almonds, in shell",
    "Wine grapes": "Grapes",
}

# FAO numeric Area Code -> ISO-2 we store. Matching on the CODE, not the display name, is what
# makes "Côte d'Ivoire" safe regardless of how any downstream tool mangles the accent.
AREA_MAP = {
    107: "CI",   # Côte d'Ivoire
    81:  "GH",   # Ghana
    21:  "BR",   # Brazil
    101: "ID",   # Indonesia
    131: "MY",   # Malaysia
    100: "IN",   # India
    216: "TH",   # Thailand
    237: "VN",   # Viet Nam
    231: "US",   # United States of America
    203: "ES",   # Spain
    174: "PT",   # Portugal
    106: "IT",   # Italy
    84:  "GR",   # Greece
    68:  "FR",   # France
    79:  "DE",   # Germany
    5000: "WLD",  # World
}

ELEMENTS = {"Production": "prod", "Area harvested": "area", "Yield": "yield"}


def _download() -> bytes:
    if os.path.exists(CACHE):
        print(f"using cached {CACHE}")
        return open(CACHE, "rb").read()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    print(f"downloading {URL} …", flush=True)
    data = urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=600).read()
    open(CACHE, "wb").write(data)
    print(f"cached {len(data)/1e6:.1f} MB -> {CACHE}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commodity", help="only this commodity (default: all mapped)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = {args.commodity: ITEM_MAP[args.commodity]} if args.commodity else ITEM_MAP
    fao_item_to_commodity = {v: k for k, v in items.items()}

    z = zipfile.ZipFile(io.BytesIO(_download()))
    member = [n for n in z.namelist() if n.endswith("(Normalized).csv")][0]

    # (commodity, iso2, year) -> {prod, area, yield}
    rows: dict = {}
    with z.open(member) as f:
        # utf-8-sig, NOT latin-1 — see the module docstring.
        r = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="strict"))
        for rec in r:
            item = rec["Item"]
            commodity = fao_item_to_commodity.get(item)
            if not commodity:
                continue
            field = ELEMENTS.get(rec["Element"])
            if not field or not rec["Value"]:
                continue
            try:
                iso2 = AREA_MAP.get(int(rec["Area Code"]))
            except ValueError:
                continue
            if not iso2:
                continue
            key = (commodity, iso2, int(rec["Year"]))
            rows.setdefault(key, {})[field] = float(rec["Value"])
            if field == "yield":
                rows[key]["yield_unit"] = rec["Unit"]

    # year-on-year within each (commodity, country) production series
    by_series: dict = {}
    for (c, geo, yr), v in rows.items():
        by_series.setdefault((c, geo), {})[yr] = v.get("prod")

    out = []
    for (c, geo, yr), v in sorted(rows.items()):
        prod = v.get("prod")
        prev = by_series[(c, geo)].get(yr - 1)
        yoy = round((prod - prev) / prev * 100, 2) if (prod and prev) else None
        # FAO publishes Yield in kg/ha (or 100g/ha for some items). Rather than trust the
        # unit string, derive t/ha from production/area — the two absolutes we know.
        yld = round(prod / v["area"], 4) if (prod and v.get("area")) else None
        out.append({
            "c": c, "geo": geo, "yr": yr,
            "prod": prod, "area": v.get("area"), "yld": yld, "yoy": yoy,
            "note": f"FAOSTAT QCL, FAO CALENDAR year (not a split crop season); "
                    f"yield derived = production/area",
        })

    counts: dict = {}
    for r_ in out:
        counts.setdefault(r_["c"], set()).add(r_["geo"])
    for c, geos in sorted(counts.items()):
        n = len([r_ for r_ in out if r_["c"] == c])
        print(f"  {c:12s} {n:>5} country-years across {len(geos)} origins: {','.join(sorted(geos))}")

    if not args.dry_run and out:
        with get_session() as s:
            for r_ in out:
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
                """), {**r_, "src": SOURCE})

    print(f"\n{len(out)} country-year labels {'(dry run)' if args.dry_run else 'ingested'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
