"""Load ECB reference FX rates into fx_rates.

The ECB publishes daily euro reference rates for free, no licence and no API key,
via the Frankfurter service (a thin, cached wrapper over the ECB dataset). We
store them as EUR-per-one-unit-of-currency so a native-currency holding converts
with a single multiply.

  python -m scripts.load_fx_rates                 # latest rates
  python -m scripts.load_fx_rates --date 2023-12-29
  python -m scripts.load_fx_rates --history 2020-01-01   # every ECB working day since

Idempotent: re-running upserts the same (ccy, rate_date) rows. Offline/tests do
not need this — the migration seeds a labelled fallback set.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

from sqlalchemy import text

from core.db.session import get_session

_BASE = "https://api.frankfurter.dev/v1"


def _fetch(path: str) -> dict:
    with urllib.request.urlopen(f"{_BASE}/{path}", timeout=30) as r:
        return json.loads(r.read().decode())


def _upsert(session, rate_date: str, rates: dict) -> int:
    """rates is {ccy: units_per_eur} (ECB quotes foreign-per-EUR). We invert to
    EUR-per-unit and store. EUR itself is the base (implicitly 1.0)."""
    n = 0
    for ccy, units_per_eur in rates.items():
        if not units_per_eur:
            continue
        eur_per_unit = round(1.0 / float(units_per_eur), 8)
        session.execute(text("""
            INSERT INTO fx_rates (ccy, rate_date, eur_per_unit, source)
            VALUES (:c, :d, :r, 'ecb')
            ON CONFLICT (ccy, rate_date) DO UPDATE SET eur_per_unit = EXCLUDED.eur_per_unit, source = 'ecb'
        """), {"c": ccy, "d": rate_date, "r": eur_per_unit})
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="single date YYYY-MM-DD (default: latest)")
    ap.add_argument("--history", metavar="FROM", help="load every ECB working day since FROM to today")
    args = ap.parse_args()

    with get_session() as session:
        if args.history:
            data = _fetch(f"{args.history}..?base=EUR")
            total = 0
            for d, rates in sorted(data.get("rates", {}).items()):
                total += _upsert(session, d, rates)
            session.commit()
            print(f"loaded {total} rate rows across {len(data.get('rates', {}))} dates")
        else:
            path = f"{args.date}?base=EUR" if args.date else "latest?base=EUR"
            data = _fetch(path)
            n = _upsert(session, data["date"], data["rates"])
            session.commit()
            print(f"loaded {n} rates for {data['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
