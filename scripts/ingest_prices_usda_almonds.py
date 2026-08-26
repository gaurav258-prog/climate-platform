"""Ingest REAL almond prices from USDA Market News (MARS) — the one commodity with no free keyless series.

Almonds aren't in the World Bank Pink Sheet or the EU agri-food portal, and USDA's price APIs are key-gated
(free registration). This connector is therefore honestly gated: it activates the moment a free
`USDA_MARS_API_KEY` is set, and no-ops (with a clear message) otherwise — the panel keeps almonds as
'no index' until then, or a buyer loads their own contracted almond price via the CSV upload.

  source  : USDA Agricultural Marketing Service, Market News (marsapi.ams.usda.gov)
  auth    : HTTP Basic — API key as username, blank password (free key: https://mymarketnews.ams.usda.gov)
  report  : configurable via USDA_ALMOND_REPORT (default: the National Almond wholesale report slug)
  feeds   : commodity_price_index → 'Almonds'

    USDA_MARS_API_KEY=... python -m scripts.ingest_prices_usda_almonds --dry-run
"""
from __future__ import annotations

import argparse
import os
from collections import defaultdict

import requests

from core.config import settings
from core.db.session import get_session
from services.intelligence import price_index as PI

SOURCE = "USDA Market News"
REPORT = os.getenv("USDA_ALMOND_REPORT", "2661")   # National Almond Report; override per the report catalog
BASE = "https://marsapi.ams.usda.gov/services/v1.2/reports/{report}"


def _ym(date_str: str) -> str | None:
    # MARS report dates are 'MM/DD/YYYY'
    p = (date_str or "").split("/")
    return f"{p[2]}-{p[0]}" if len(p) == 3 and len(p[2]) == 4 else None


def build() -> list[dict]:
    key = settings.USDA_MARS_API_KEY
    if not key:
        return []
    resp = requests.get(BASE.format(report=REPORT), auth=(key, ""), timeout=30,
                        headers={"Accept": "application/json"})
    resp.raise_for_status()
    payload = resp.json()
    records = payload.get("results") or payload.get("report") or payload if isinstance(payload, list) else payload.get("results", [])
    monthly: dict = defaultdict(list)
    for r in records:
        # tolerate the MARS schema variants — a price-ish numeric field + a report date
        price = r.get("avg_price") or r.get("price") or r.get("wtd_avg") or r.get("price_avg")
        ym = _ym(r.get("report_date") or r.get("report_begin_date") or "")
        try:
            price = float(str(price).replace("$", "").replace(",", "").split("-")[0].strip())
        except (TypeError, ValueError, AttributeError):
            continue
        if ym and price:
            monthly[ym].append(price)
    return [{"source": SOURCE, "commodity": "Almonds", "period_ym": ym,
             "index_value": round(sum(v) / len(v), 4), "unit": "USD/lb"} for ym, v in monthly.items()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not settings.USDA_MARS_API_KEY:
        print("USDA_MARS_API_KEY not set — almond feed is gated. Register a free key at "
              "https://mymarketnews.ams.usda.gov and export USDA_MARS_API_KEY, then re-run.")
        return 0
    rows = build()
    if rows:
        months = sorted(r["period_ym"] for r in rows)
        print(f"  Almonds  {len(rows)} monthly points  [{months[0]}–{months[-1]}]")
    if not args.dry_run and rows:
        with get_session() as s:
            PI.ingest(s, rows)
    print(f"\n{len(rows)} monthly almond price points {'(dry run)' if args.dry_run else 'ingested'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
