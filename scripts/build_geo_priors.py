"""Build the geography priors the Tier-1 plausibility band reads (supervision_geo_prior) from standing canonical scores.

The worker does this daily and after every feed refresh (services/tasks/supervision_tasks.py); run by hand after a
scoring change:   .venv/bin/python -m scripts.build_geo_priors [--basis=baseline:current ...]
"""
from __future__ import annotations

import sys

from services.supervision.geo_prior import rebuild_all


def main(argv: list[str]) -> int:
    only = [a.split("--basis=", 1)[1] for a in argv if a.startswith("--basis=")] or None
    for basis, r in rebuild_all(only).items():
        print(f"{basis}: {r['geographies']} geographies ({r['seconds']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
