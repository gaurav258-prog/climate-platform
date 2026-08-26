"""Ingest REAL price series from the EU Commission agri-food data portal — the authoritative EU source for
commodities the World Bank Pink Sheet doesn't carry: olive oil, wine, and dairy.

  source  : European Commission, agri-food data portal (ec.europa.eu/agrifood/api)
  cadence : weekly member-state prices, aggregated here to a monthly EU mean per product
  licence : EU open data (CC BY 4.0), no key
  feeds   : commodity_price_index (the input-cost-pressure panel), via price_index.ingest

Mappings (Pink Sheet has none of these):
  olive oil  Extra virgin (up to 0.8%)  → 'Olive oil'   (the premium producer reference)
  wine       all EU wine quotations     → 'Wine grapes' (wine price is the market reference for the grape)
  dairy      BUTTER/SMP/WMP/CHEDDAR/...  → catalog additions

Observed agency prices — never a Tellumen forecast. Absolute level is irrelevant to the panel (it reads the
% move vs a trailing baseline), so a monthly EU mean across producing member states is a sound benchmark.

    python -m scripts.ingest_prices_eu_agrifood --dry-run
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import requests

from core.db.session import get_session
from services.intelligence import price_index as PI

API = "https://www.ec.europa.eu/agrifood/api/{ep}/prices"
SOURCE = "EU Commission — agri-food data portal"
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

DAIRY_MAP = {
    "BUTTER": "Butter", "SMP": "Skimmed milk powder", "WMP": "Whole milk powder",
    "CHEDDAR": "Cheddar cheese", "DRINKING MILK": "Drinking milk", "WHEYPOWDER": "Whey powder",
}


def _price(v) -> float | None:
    try:
        return float(str(v).replace("€", "").replace("€", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _ym(begin: str) -> str | None:
    # "DD/MM/YYYY" → "YYYY-MM"
    parts = (begin or "").split("/")
    return f"{parts[2]}-{parts[1]}" if len(parts) == 3 and len(parts[2]) == 4 else None


def _fetch(ep: str) -> list[dict]:
    return requests.get(API.format(ep=ep), timeout=30, headers=UA).json()


def _monthly(rows: list[dict], *, keep, commodity_of) -> dict:
    """Aggregate weekly rows → mean price per (commodity, YYYY-MM). keep(row)->bool, commodity_of(row)->name."""
    acc: dict = defaultdict(list)
    unit: dict = {}
    for r in rows:
        if not keep(r):
            continue
        c = commodity_of(r)
        ym = _ym(r.get("beginDate", ""))
        p = _price(r.get("price"))
        if c and ym and p is not None:
            acc[(c, ym)].append(p)
            unit.setdefault(c, str(r.get("unit") or "").strip())
    out = []
    for (c, ym), vals in acc.items():
        out.append({"source": SOURCE, "commodity": c, "period_ym": ym,
                    "index_value": round(sum(vals) / len(vals), 4), "unit": unit.get(c)})
    return out


def build() -> list[dict]:
    rows = []
    # olive oil — extra virgin, averaged across producing member states
    oo = _fetch("oliveOil")
    rows += _monthly(oo, keep=lambda r: str(r.get("product", "")).lower().startswith("extra virgin"),
                     commodity_of=lambda r: "Olive oil")
    # wine — all EU quotations
    wine = _fetch("wine")
    rows += _monthly(wine, keep=lambda r: _price(r.get("price")) is not None,
                     commodity_of=lambda r: "Wine grapes")
    # dairy — mapped products
    dairy = _fetch("dairy")
    rows += _monthly(dairy, keep=lambda r: str(r.get("product", "")).upper() in DAIRY_MAP,
                     commodity_of=lambda r: DAIRY_MAP[str(r.get("product", "")).upper()])
    return rows


def refresh(session) -> int:
    """Importable entry for the scheduled feed-refresh system. Returns the number of points loaded."""
    rows = build()
    PI.ingest(session, rows)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = build()
    by = defaultdict(lambda: [set(), 0])
    for r in rows:
        by[r["commodity"]][0].add(r["period_ym"]); by[r["commodity"]][1] += 1
    for c, (months, n) in sorted(by.items()):
        print(f"  {c:<22} {n:>4} monthly points  [{min(months)}–{max(months)}]")

    if not args.dry_run and rows:
        with get_session() as s:
            PI.ingest(s, rows)

    print(f"\n{len(rows)} monthly EU price points {'(dry run)' if args.dry_run else 'ingested'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
