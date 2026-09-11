"""Score subsidence v2 (observed EGMS rate) for every exposure cell and every existing subsidence cell inside EGMS
coverage; the v1 class row of a scored cell is retired (append-only lane). Cells outside coverage or with too few
measured pixels are left on v1 and counted. Run: PYTHONPATH=. .venv/bin/python -m scripts.score_subsidence_egms
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.subsidence_egms import PCT, SUBSIDENCE_MODEL_VERSION, TileReader, tile_for

EXPOSURE_TABLES = ("bank_assets", "sc_company_sites", "sc_sourcing_plots", "assetmgmt_holdings", "insurance_policies", "issuer_facilities",
                   "realestate_properties", "portfolio_entities", "third_party", "coastal_exposure")


def main() -> int:
    now = datetime.now(timezone.utc); t0 = time.time()
    with get_session() as s:
        cells = set(s.execute(text("SELECT DISTINCT h3_cell FROM canonical_scores WHERE hazard_type='subsidence' AND valid_to IS NULL")).scalars())
        for t in EXPOSURE_TABLES:
            try:
                cells |= set(s.execute(text(f"SELECT DISTINCT h3_cell FROM {t} WHERE h3_cell IS NOT NULL")).scalars())
            except Exception:
                s.rollback()
    cells = [c for c in cells if h3.get_resolution(c) == 8]
    by_tile: dict = defaultdict(list); outside = 0
    for c in cells:
        la, lo = h3.cell_to_latlng(c)
        name = tile_for(lo, la)
        if name is None:
            outside += 1
        else:
            by_tile[name].append(c)
    print(f"{len(cells)} cells: {outside} outside EGMS coverage (stay on v1), {len(cells) - outside} over {len(by_tile)} tiles", flush=True)
    scored, sparse = 0, 0
    for name, cs in by_tile.items():
        r = TileReader(name); rows = []
        for c in cs:
            st = r.cell_rate(c)
            if st is None:
                sparse += 1; continue
            rows.append({"id": str(uuid.uuid4()), "c": c, "score": st["score"], "b": score_to_bucket(st["score"]).value, "mv": SUBSIDENCE_MODEL_VERSION, "now": now,
                         "shap": json.dumps({**st, "tile": name, "source": "Copernicus EGMS Ortho L3 vertical velocity 2020–2024 (100 m)",
                                             "method": f"{PCT}th percentile of observed subsidence rate over the cell's measured pixels → anchored 0–100 scale"})})
        r.close()
        with get_session() as s:
            s.execute(text("""UPDATE canonical_scores SET valid_to = :now WHERE hazard_type='subsidence' AND scenario='baseline' AND time_horizon='current'
                              AND valid_to IS NULL AND h3_cell = ANY(:cells)"""), {"now": now, "cells": [x["c"] for x in rows]})
            for i in range(0, len(rows), 2000):
                s.execute(text("""INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon, risk_score, risk_bucket,
                                  model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
                                  VALUES (:id,:c,8,'subsidence','baseline','current',:score,:b,:mv,:now,CAST(:shap AS jsonb),:now,:now,NULL)"""), rows[i:i + 2000])
        scored += len(rows)
    print(f"scored {scored} cells on {SUBSIDENCE_MODEL_VERSION} ({time.time() - t0:.0f}s); {sparse} cells had < 20 measured pixels (stay on v1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
