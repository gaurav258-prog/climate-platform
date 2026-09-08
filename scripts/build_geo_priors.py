"""Build the geography priors the Tier-1 plausibility band reads (supervision_geo_prior) from standing canonical scores.

Runs for every basis (scenario × horizon) that has standing scores. Re-run after a scoring refresh.
    .venv/bin/python -m scripts.build_geo_priors [--basis baseline:current]
"""
from __future__ import annotations

import sys
import time

from sqlalchemy import text

from core.db.session import get_session
from services.supervision.geo_prior import build


def main(argv: list[str]) -> int:
    only = [a.split("--basis=", 1)[1] for a in argv if a.startswith("--basis=")]
    with get_session() as s:
        bases = [tuple(r) for r in s.execute(text("""SELECT DISTINCT scenario, time_horizon FROM canonical_scores
                                                     WHERE score_lane = 'standing' AND valid_to IS NULL ORDER BY 1, 2""")).all()]
        if only:
            bases = [b for b in bases if f"{b[0]}:{b[1]}" in only]
        cache: dict = {}
        for sc, hz in bases:
            t = time.time()
            n = build(s, sc, hz, cache); s.commit()
            print(f"{sc} · {hz}: {n} geographies ({time.time() - t:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
