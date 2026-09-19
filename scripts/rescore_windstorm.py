"""Re-score every live windstorm cell with the current model version (v1.1 longitude-wrap fix).

Old rows are retired (valid_to set, never deleted) and new rows inserted, as the flood/subsidence scorers do.
Run once: `python scripts/rescore_windstorm.py` (add --dry-run to only count).
"""
from __future__ import annotations

import sys

import h3
from sqlalchemy import text

from core.db.session import get_session
from ml.scoring import windstorm_point as W


def main(dry: bool) -> None:
    with get_session() as s:
        rows = s.execute(text("""SELECT h3_cell, scenario, time_horizon FROM canonical_scores
                                 WHERE hazard_type='windstorm' AND valid_to IS NULL AND model_version <> :mv"""),
                         {"mv": W.MODEL_VERSION}).fetchall()
    print(f"{len(rows)} stale windstorm rows")
    if dry:
        return
    done = 0
    for cell, sc, hz in rows:
        lat, lon = h3.cell_to_latlng(cell)
        done += W.score_windstorm_point(lat, lon, sc, hz)["status"] == "scored"
    print(f"re-scored {done} of {len(rows)}")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
