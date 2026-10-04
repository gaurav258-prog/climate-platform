"""Run the calibration pipeline (E162): adopt any fit published before the pipeline as a recipe, run every active
recipe (or those reading one yield source) on the data of the day, record each run with its ledger entry, and propose
the runs that would change a publication — one approval request, decided on the approvals page (calibration.review).
Nothing publishes from here.

    python -m scripts.run_calibration_pipeline --dry-run              # show the runs, write nothing
    python -m scripts.run_calibration_pipeline                        # record the runs, propose the changes
    python -m scripts.run_calibration_pipeline --source "FAOSTAT QCL bulk"
"""
from __future__ import annotations

import argparse
import sys

from core.db.session import get_session
from services.calibration import pipeline


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="append", help="only the recipes reading this yield source (repeatable)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    with get_session() as s:
        adopted = pipeline.adopt_legacy(s)
        out = pipeline.run(s, sources=a.source, reason="Calibration pipeline run by an operator")
        print(f"recipes adopted from published fits: {len(adopted)}; runs: {len(out['runs'])}")
        for r in out["runs"]:
            print(f"  {r['commodity'][:12]:12} {r['origin']:3} {r['driver']:10} {r['outcome']:13} r2_oos={r['r2_oos']}"
                  f"  downside={'pass' if r['downside_pass'] else 'held'}  upside={'pass' if r['upside_pass'] else 'held'}"
                  + (f"  ({'; '.join(r['upside_failed'])})" if r["upside_failed"] else ""))
        p = out["proposal"]
        print(f"proposed for review: {p['runs']} run(s), request {p['approval_request_id']}" if p
              else "nothing to propose — every run matches what is published")
        if a.dry_run:
            s.rollback()
            print("dry run — nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
