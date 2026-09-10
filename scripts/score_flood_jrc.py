"""Score the flood channel (v3, JRC river-flood maps) for every cell the platform carries a flood score for, plus
every exposure cell. Per tile: open the RP10/RP100/RP500 rasters once, read each cell's window, compute the
inundated share and mean depth, score = 100 × frac_RP100 × DDF(depth). Retires the prior standing rows of the
cells it scores (append-only lane); cells whose tile is not on disk are left untouched and counted.

Run: PYTHONPATH=. .venv/bin/python -m scripts.score_flood_jrc
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
from ml.scoring.flood_jrc import (
    FLOOD_MODEL_VERSION,
    TileReader,
    cell_polygon,
    stats_to_row,
    tile_name,
)

EXPOSURE_TABLES = ("bank_assets", "sc_company_sites", "sc_sourcing_plots", "assetmgmt_holdings", "insurance_policies", "issuer_facilities",
                   "realestate_properties", "portfolio_entities", "third_party", "coastal_exposure")


def _cells(s) -> dict[str, tuple[float, float]]:
    cells = set(s.execute(text("SELECT DISTINCT h3_cell FROM canonical_scores WHERE hazard_type='flood' AND valid_to IS NULL")).scalars())
    for t in EXPOSURE_TABLES:
        try:
            cells |= set(s.execute(text(f"SELECT DISTINCT h3_cell FROM {t} WHERE h3_cell IS NOT NULL")).scalars())
        except Exception:
            s.rollback()
    return {c: h3.cell_to_latlng(c) for c in cells if h3.get_resolution(c) == 8}


def main() -> int:
    now = datetime.now(timezone.utc); t0 = time.time()
    with get_session() as s:
        cells = _cells(s)
    by_tile: dict = defaultdict(list)
    for c, (la, lo) in cells.items():
        by_tile[tile_name(la, lo)].append(c)
    print(f"{len(cells)} flood cells over {len(by_tile)} tiles", flush=True)
    scored, missing, empty, retire = 0, 0, 0, []
    for name, cs in sorted(by_tile.items(), key=lambda kv: -len(kv[1])):
        if name is None:
            missing += len(cs); retire += cs; continue
        r = TileReader(name)
        if not r.complete():
            r.close(); missing += len(cs); continue          # tile not fetched yet: leave the cell's row as it is
        rows = []
        for c in cs:
            st = r.polygon_stats(cell_polygon(c))
            if st is None:
                empty += 1; retire.append(c); continue        # sea / permanent water: the current version has no answer
            row = stats_to_row(st)
            rows.append({"id": str(uuid.uuid4()), "c": c, "score": row["score"], "b": score_to_bucket(row["score"]).value,
                         "mv": FLOOD_MODEL_VERSION, "now": now,
                         "shap": json.dumps({**row, "source": "JRC/CEMS global river flood hazard maps v2.1.2 (LISFLOOD-FP, 90 m)",
                                             "method": "share of the cell in the 1-in-100-year floodplain × Huizinga 2017 residential depth–damage fraction"})})
        r.close()
        with get_session() as s:
            s.execute(text("""UPDATE canonical_scores SET valid_to = :now WHERE hazard_type='flood' AND scenario='baseline' AND time_horizon='current'
                              AND valid_to IS NULL AND COALESCE(score_lane,'standing')='standing' AND h3_cell = ANY(:cells)"""),
                      {"now": now, "cells": [x["c"] for x in rows]})
            for i in range(0, len(rows), 2000):
                s.execute(text("""INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon, risk_score, risk_bucket,
                                  model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to, score_lane)
                                  VALUES (:id,:c,8,'flood','baseline','current',:score,:b,:mv,:now,CAST(:shap AS jsonb),:now,:now,NULL,'standing')"""), rows[i:i + 2000])
        scored += len(rows)
        print(f"  {name}: {len(rows)} cells · total {scored} · {time.time() - t0:.0f}s", flush=True)
    if retire:
        # a cell the current version cannot score keeps no older-version row alive (the same rule as the storm scorer)
        with get_session() as s:
            s.execute(text("""UPDATE canonical_scores SET valid_to = :now WHERE hazard_type='flood' AND scenario='baseline' AND time_horizon='current'
                              AND valid_to IS NULL AND COALESCE(score_lane,'standing')='standing' AND h3_cell = ANY(:cells)"""), {"now": now, "cells": retire})
    print(f"scored {scored} cells on {FLOOD_MODEL_VERSION}; {missing} cells outside every tile; {empty} had no land pixels; "
          f"{len(retire)} older-version rows retired as undetermined")
    return 0


if __name__ == "__main__":
    sys.exit(main())
