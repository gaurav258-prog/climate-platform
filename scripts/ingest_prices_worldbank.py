"""Ingest REAL monthly commodity prices from the World Bank "Pink Sheet".

WHY. The price move is the OUTPUT of the whole COGS chain — it is what every calibration is
scored against — and we had no price series at all. Every "observed" price move in our
validation records was a hand-typed figure from a press article. That is how cocoa came to be
validated against an observed "+177%" that no reference series reproduces (see below).

  source  : World Bank Commodity Markets "Pink Sheet", CMO-Historical-Data-Monthly.xlsx
  span    : monthly from 1960M01, ~0.8 MB, open (no key)
  licence : World Bank open data (CC BY 4.0)
  note    : the Pink Sheet's Cocoa quote IS the ICCO daily average price — the industry
            reference for cocoa — so it is the right yardstick, not an alternative one.

Other price routes were tried and are blocked from this environment: FRED (timeout), Yahoo
Finance (429), Stooq (JS browser-check). The Pink Sheet is the one that answers.

CROP-YEAR vs CALENDAR YEAR matters enormously here and is why we store MONTHLY and aggregate
deliberately at the call site. Cocoa 2023/24:
    crop-year mean (Oct-Sep, the trade convention) = +115.8%
    calendar-2024 mean                             = +123.4%
    April-2024 peak                                = +307%
Three defensible numbers for one event; quote the wrong one and a calibration is fitted to a
fiction.

    python -m scripts.ingest_prices_worldbank --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request

from sqlalchemy import text

from core.db.session import get_session

URL = ("https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/"
       "related/CMO-Historical-Data-Monthly.xlsx")
CACHE = "data/worldbank/CMO-Historical-Data-Monthly.xlsx"
SOURCE = "World Bank Pink Sheet"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

# Pink Sheet column header -> our sc_commodities name. Header text is matched case-insensitively
# and exactly (after strip), so a renamed column fails loudly instead of silently binding to
# the wrong series.
COLUMN_MAP = {
    "Cocoa": "Cocoa",
    "Coffee, Arabica": "Coffee",
    "Palm oil": "Palm oil",
    "Soybeans": "Soybean",
    "Maize": "Maize",
    "Wheat, US SRW": "Wheat",         # soft red winter — the reference for common (bread) wheat
    "Wheat, US HRW": "Durum wheat",   # no durum quote; HRW is the closest liquid wheat ref
    "Sugar, world": "Sugar beet",     # world sugar is one fungible market (beet + cane)
    "Rice, Thai 5%": "Rice",
    "Orange": "Citrus",
}


def _download() -> str:
    if os.path.exists(CACHE):
        print(f"using cached {CACHE}")
        return CACHE
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    print(f"downloading {URL} …", flush=True)
    data = urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=300).read()
    open(CACHE, "wb").write(data)
    print(f"cached {len(data)/1e6:.2f} MB -> {CACHE}")
    return CACHE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import openpyxl
    wb = openpyxl.load_workbook(_download(), read_only=True, data_only=True)
    rows = list(wb["Monthly Prices"].iter_rows(values_only=True))
    names, units = rows[4], rows[5]

    cols = {}
    for i, n in enumerate(names):
        key = str(n).strip() if n else ""
        if key in COLUMN_MAP:
            cols[i] = (COLUMN_MAP[key], str(units[i]).strip("() ") if units[i] else None)
    missing = set(COLUMN_MAP.values()) - {c for c, _ in cols.values()}
    if missing:
        print(f"  ! Pink Sheet columns not found for: {sorted(missing)} — headers may have changed")

    out = []
    for r in rows[6:]:
        label = str(r[0]) if r[0] else ""
        if "M" not in label:
            continue
        y, m = label.split("M")
        for i, (commodity, unit) in cols.items():
            v = r[i]
            if isinstance(v, (int, float)):
                out.append({"c": commodity, "y": int(y), "m": int(m),
                            "p": round(float(v), 6), "u": unit})

    by = {}
    for r_ in out:
        by.setdefault(r_["c"], []).append(r_["y"])
    for c, ys in sorted(by.items()):
        print(f"  {c:12s} {len(ys):>5} months  [{min(ys)}-{max(ys)}]  unit="
              f"{next(u for _, u in cols.values() if True) if False else ''}"
              f"{[u for cc, u in cols.values() if cc == c][0]}")

    if not args.dry_run and out:
        with get_session() as s:
            for r_ in out:
                s.execute(text("""
                    INSERT INTO sc_commodity_prices (commodity, year, month, price, unit, source)
                    VALUES (:c, :y, :m, :p, :u, :src)
                    ON CONFLICT (commodity, year, month, source) DO UPDATE SET
                        price = EXCLUDED.price, unit = EXCLUDED.unit, ingested_at = now()
                """), {**r_, "src": SOURCE})
            # Feed the input-cost-pressure panel (commodity_price_index) from the SAME authoritative series —
            # one Pink Sheet, both the COGS-validation prices and the observed price-pressure surface.
            import services.intelligence.price_index as PI
            PI.ingest(s, [{"source": SOURCE, "commodity": r_["c"], "period_ym": f"{r_['y']}-{r_['m']:02d}",
                           "index_value": r_["p"], "unit": r_["u"]} for r_ in out])

    print(f"\n{len(out)} monthly price points {'(dry run)' if args.dry_run else 'ingested'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
