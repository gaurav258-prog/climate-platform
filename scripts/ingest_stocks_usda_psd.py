"""Ingest REAL world stocks-to-use per commodity-year from the USDA PSD bulk download.

WHY THIS MATTERS MORE THAN IT LOOKS. Price amplification A(s) = (34.7/s)^3.62 is the most
leveraged term in the COGS chain — it is what turns a few-percent supply shock into a doubled
price when the market is tight. We fed it ONE STATIC HAND-ENTERED NUMBER per commodity.

Coffee 2021: we used 40.0%. USDA PSD says 14.2%. A(40)=0.60 (dampening) vs A(14.2)=capped
at 6.0 — a ~10x error on the most sensitive term in the model, in the OPPOSITE direction to
the 13x shock over-attribution we already found. Two compensating errors cancelling into a
plausible price: the model was right by accident.

And stocks are not a constant — coffee ran 18.3/17.0/19.6/14.2/14.2/11.7/10.1 across 2018-24.
The amplification must use the stocks AT THE EVENT.

  dataset : https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip (~10 MB)
            (the PSD *API* returns 403; the bulk file is open)
  derived : stocks_to_use = Ending Stocks / Domestic Consumption, summed over countries

CAVEATS, stated because they bound the result:
  * PSD PUBLISHES NO WORLD ROW — we sum countries, EXCLUDING aggregate rows ('European Union'
    et al.) which would double-count their own member states.
  * PSD DOES NOT TRACK COCOA at all (that is ICCO's domain). Our one published crop therefore
    keeps its hand-entered 26.4% — a known, unclosed gap.
  * Market years are PSD's own convention (split seasons for tropical crops), not calendar
    years. Stored as-is under market_year; align deliberately, do not assume.

    python -m scripts.ingest_stocks_usda_psd --dry-run
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import sys
import urllib.request
import zipfile

from sqlalchemy import text

from core.db.session import get_session

URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip"
CACHE = "data/usda_psd/psd_alldata_csv.zip"
SOURCE = "USDA PSD bulk"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

# PSD commodity description -> our sc_commodities name.
CROP_MAP = {
    "Coffee, Green": "Coffee",
    "Oil, Olive": "Olive oil",
    "Wheat": "Durum wheat",        # PSD does not split durum; world wheat stocks are the
                                   # right market signal for a durum price anyway
    "Almonds, Shelled Basis": "Almonds",
    "Oil, Palm": "Palm oil",
    "Oilseed, Soybean": "Soybean",
    "Rice, Milled": "Rice",
    "Corn": "Maize",
    "Sugar, Centrifugal": "Sugar beet",   # world sugar is one fungible market (beet + cane)
}
# Rows that are aggregates of other rows — summing them double-counts.
AGGREGATE_ROWS = {"European Union", "Other", "Unaccounted"}


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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    z = zipfile.ZipFile(io.BytesIO(_download()))
    tot: dict = collections.defaultdict(lambda: collections.defaultdict(float))
    units: dict = {}
    with z.open("psd_alldata.csv") as f:
        r = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace"))
        for row in r:
            crop = CROP_MAP.get(row["Commodity_Description"])
            if not crop or row["Country_Name"] in AGGREGATE_ROWS:
                continue
            attr = row["Attribute_Description"]
            if attr not in ("Ending Stocks", "Domestic Consumption"):
                continue
            try:
                v = float(row["Value"] or 0)
            except ValueError:
                continue
            tot[(crop, int(row["Market_Year"]))][attr] += v
            units[crop] = row["Unit_Description"]

    rows = []
    for (crop, year), d in sorted(tot.items()):
        es, du = d.get("Ending Stocks"), d.get("Domestic Consumption")
        if not es or not du:
            continue
        rows.append({"c": crop, "y": year, "es": round(es, 3), "du": round(du, 3),
                     "stu": round(es / du * 100, 3), "u": units.get(crop),
                     "note": "world = sum of PSD country rows, aggregates excluded"})

    by_crop = collections.Counter(r["c"] for r in rows)
    for c, n in sorted(by_crop.items()):
        yrs = [r["y"] for r in rows if r["c"] == c]
        recent = {r["y"]: r["stu"] for r in rows if r["c"] == c and r["y"] >= 2020}
        print(f"  {c:12s} {n:>3} yrs [{min(yrs)}-{max(yrs)}]  recent: "
              + " ".join(f"{y}:{v:.1f}%" for y, v in sorted(recent.items())))

    if not args.dry_run and rows:
        with get_session() as s:
            for r_ in rows:
                s.execute(text("""
                    INSERT INTO sc_commodity_stocks
                        (commodity, market_year, ending_stocks, domestic_use,
                         stocks_to_use_pct, unit, source, note)
                    VALUES (:c, :y, :es, :du, :stu, :u, :src, :note)
                    ON CONFLICT (commodity, market_year, source) DO UPDATE SET
                        ending_stocks = EXCLUDED.ending_stocks,
                        domestic_use = EXCLUDED.domestic_use,
                        stocks_to_use_pct = EXCLUDED.stocks_to_use_pct,
                        ingested_at = now()
                """), {**r_, "src": SOURCE})

    print(f"\n{len(rows)} commodity-year stocks rows {'(dry run)' if args.dry_run else 'ingested'}")
    print("NOTE: PSD does not track cocoa — our one published crop keeps its hand-entered 26.4% (ICCO).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
