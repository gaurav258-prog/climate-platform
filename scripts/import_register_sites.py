"""Issuers' real sites from public registers (the product owner's decisions of 2026-10-23):

  --climate-trace   record the Climate TRACE sources whose ownership chain names an issuer's LEI as that issuer's sites
                    (weight not stated) and score their cells (services.scoring.on_demand via the job runner)
  --eea             propose the EEA register's functional facilities whose named parent company is, by the rule of
                    services.reference.register_matching, a GLEIF name of an issuer or of an entity it consolidates —
                    pending a person's decision on the platform's Reference data page; nothing is used before it

Writes to the database DATABASE_URL names; run it against the database the work is meant for.

Usage: venv/bin/python -m scripts.import_register_sites [--climate-trace] [--eea] [--no-score]
"""
from __future__ import annotations

import argparse


def main() -> int:
    from core.db.session import get_session
    from services.reference import register_matching as M
    from services.reference import register_sites as R
    ap = argparse.ArgumentParser()
    ap.add_argument("--climate-trace", action="store_true")
    ap.add_argument("--eea", action="store_true")
    ap.add_argument("--no-score", action="store_true", help="record the sites without scoring their cells")
    a = ap.parse_args()
    cells = {}
    with get_session() as s:
        if a.climate_trace:
            found = R.climate_trace_sites(s)
            got = R.record(s, found["sites"])
            s.commit()
            cells.update(got["cells"])
            print({"climate_trace": {"release": found["release"], "by_subsector": found["counts"],
                                     "added": got["added"], "held": got["held"], "new_cells": len(got["cells"])}})
        if a.eea:
            c = M.candidates(s)
            got = M.stage(s, c["proposals"])
            s.commit()
            print({"eea": {"vintage": c["vintage"], "counts": c["counts"], **got}})
    if cells and not a.no_score:
        from services.tasks.jobs import submit
        print({"scoring": submit("scoring.process_cells", cells)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
