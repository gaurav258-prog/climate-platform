"""Load ECB euro reference rates into fx_rates now (the daily `fx_ecb` feed does this automatically).

  python -m scripts.load_fx_rates            # the last 90 days (or full history if we hold none)
  python -m scripts.load_fx_rates --full     # every ECB working day since 1999

Direct from the ECB (services/reference/ecb_fx.py). Idempotent: re-running upserts the same (ccy, rate_date) rows.
"""
from __future__ import annotations

import argparse
import sys

from core.db.session import get_session
from services.reference.ecb_fx import refresh


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="load the full ECB history since 1999")
    args = ap.parse_args()
    with get_session() as session:
        out = refresh(session, full=args.full)
    print(f"loaded {out['n_rows']} rates over {out['n_days']} days ({out['from']} → {out['to']}), "
          f"{len(out['currencies'])} currencies; newest {out['newest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
