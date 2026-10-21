"""Run the pre-registered US storm loss test (data/reference/loss_protocol.json 'us_storm_loss_test';
services/loss/us_storm_loss_test.py).

--winds-only reads the storm layer's wind at every LitPop cell of the forecast zones in scope (about 115,000 cells, four
processes) and saves it under data/loss_val/us_storm_loss_test: nothing is compared with reported damage and nothing is
recorded. Without it, the test runs once per US curve and each result is recorded — in the validation ledger and on the
curve. Run it from this file (the worker processes import it), never from stdin.

Usage: PYTHONPATH=. venv/bin/python -m scripts.run_us_storm_loss_test [--winds-only] [--workers 4]
"""
from __future__ import annotations

import argparse
import logging

from services.loss import us_storm_loss_test as T


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--winds-only", action="store_true", help="read the winds at the cells and record nothing")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.winds_only:
        c = T.cells(T.zones())
        w = T.winds(c, workers=args.workers)
        print({"cells": len(c), "zones_with_cells": int(c["zone"].nunique()), "winds": list(w.shape)})
        return
    from core.db.session import get_session
    with get_session() as session:
        out = T.run(session, workers=args.workers)
    for k, r in out.items():
        print(k, {x: r[x] for x in ("office_areas_tested", "spearman", "spearman_with_surge_information", "monotonic", "passed")})


if __name__ == "__main__":
    main()
