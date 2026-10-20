"""Run the pre-registered European flood loss test (data/reference/loss_protocol.json 'europe_loss_test';
services/loss/europe_loss_test.py).

The pass over the maps reads every European flood map once through the isolated sampler and is saved under
data/loss_val/europe_loss_test (reused while the layer version, the regions and the curves' points are unchanged).
--maps-only makes that pass and stops: nothing is computed against the reported losses and nothing is recorded.
Without it the test runs once per curve and each result is recorded — in the validation ledger and on the curve.

Usage: PYTHONPATH=. venv/bin/python -m scripts.run_europe_loss_test [--maps-only]
"""
from __future__ import annotations

import argparse
import logging

from services.loss import curves
from services.loss import europe_loss_test as T


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps-only", action="store_true", help="make the pass over the maps and record nothing")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.maps_only:
        fam = curves.families()[T.FAMILY]
        tested = [next(c for c in fam["curves"] if c["key"] == k) for k in T.protocol()["curves"]]
        obs, selection = T.observed()
        T.check_region_sets(selection)
        prof = T.maps_pass(list(obs.index), T.edges_for(tested))
        print({"regions_in_scope": selection["regions_in_scope"], "with_a_polygon": len(prof),
               "with_zone_cells": sum(1 for p in prof.values() if p["zone"])})
        return
    from core.db.session import get_session
    with get_session() as session:
        out = T.run(session)
    for k, r in out.items():
        print(k, {x: r[x] for x in ("regions_tested", "spearman", "spearman_undefended", "monotonic", "passed")})


if __name__ == "__main__":
    main()
