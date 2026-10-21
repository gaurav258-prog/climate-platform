"""Score the flood channel for every cell the platform carries a flood score for, plus every exposure cell: the JRC
European maps in the countries they cover (v4), the global maps elsewhere (v3) — ml.scoring.flood_jrc.read_cell, the
same choice the point scorer and the loss engine make. Per cell: the RP10/RP100/RP500 inundated share and mean depth,
score = 100 × frac_RP100 × DDF(depth); a cell that straddles a global tile edge is read from every tile it touches.
Retires the prior standing rows of the cells whose score or map changes (append-only lane) — a cell whose live row
already carries the same score from the same maps keeps it, so a re-run only writes what moved; cells whose maps are
not on disk are left untouched and counted. Pass --project to re-project the changed cells forward
(scripts.project_scenarios.project_cells).

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
    EUROPE_MODEL_VERSION,
    FLOOD_MODEL_VERSION,
    SOURCES,
    EuropeMaps,
    TileSet,
    cell_polygon,
    read_cell,
    stats_to_row,
    tile_name,
    tiles_for_bounds,
    uses_europe,
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


def main(project: bool = False) -> int:
    now = datetime.now(timezone.utc); t0 = time.time()
    with get_session() as s:
        cells = _cells(s)
        live = {r[0]: (float(r[1]), r[2]) for r in s.execute(text(
            """SELECT h3_cell, risk_score, model_version FROM canonical_scores WHERE hazard_type='flood' AND scenario='baseline'
               AND time_horizon='current' AND valid_to IS NULL AND COALESCE(score_lane,'standing')='standing'
               AND model_version IN (:g, :e)"""), {"g": FLOOD_MODEL_VERSION, "e": EUROPE_MODEL_VERSION}).all()}
    by_tile: dict = defaultdict(list)
    for c, (la, lo) in cells.items():                         # grouped only for read locality: the European maps
        by_tile["europe" if uses_europe(c) else tile_name(la, lo)].append(c)   # are one file per return period
    print(f"{len(cells)} flood cells over {len(by_tile)} tiles", flush=True)
    scored, unchanged, missing, empty, retire, changed = 0, 0, 0, 0, [], []
    ts, eu = TileSet(), EuropeMaps()
    for name, cs in sorted(by_tile.items(), key=lambda kv: (kv[0] is None, -len(kv[1]))):
        rows = []
        for c in cs:
            poly = cell_polygon(c)
            europe = name == "europe"
            if not europe and not tiles_for_bounds(*poly.bounds):
                missing += 1; retire.append(c); continue      # outside every tile
            if not europe and not ts.readable(poly):
                missing += 1; continue                        # a tile not fetched yet: leave the cell's row as it is
            version, st = read_cell(c, tiles=ts, europe=eu)
            if st is None and europe and tiles_for_bounds(*poly.bounds) and not ts.readable(poly):
                missing += 1; continue                        # neither map readable here: leave the cell's row as it is
            if st is None:
                empty += 1; retire.append(c); continue        # sea / permanent water: the current version has no answer
            row = stats_to_row(st)
            if c in live and live[c][1] == version and abs(live[c][0] - row["score"]) <= 0.01:
                unchanged += 1; continue                      # same maps, within the score's 2-dp rounding: keep the row
            rows.append({"id": str(uuid.uuid4()), "c": c, "score": row["score"], "b": score_to_bucket(row["score"]).value,
                         "mv": version, "now": now,
                         "shap": json.dumps({**row, "source": SOURCES[version],
                                             "method": "share of the cell in the 1-in-100-year floodplain × Huizinga 2017 residential depth–damage fraction"})})
        if rows:
            with get_session() as s:
                s.execute(text("""UPDATE canonical_scores SET valid_to = :now WHERE hazard_type='flood' AND scenario='baseline' AND time_horizon='current'
                                  AND valid_to IS NULL AND COALESCE(score_lane,'standing')='standing' AND h3_cell = ANY(:cells)"""),
                          {"now": now, "cells": [x["c"] for x in rows]})
                for i in range(0, len(rows), 2000):
                    s.execute(text("""INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon, risk_score, risk_bucket,
                                      model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to, score_lane)
                                      VALUES (:id,:c,8,'flood','baseline','current',:score,:b,:mv,:now,CAST(:shap AS jsonb),:now,:now,NULL,'standing')"""), rows[i:i + 2000])
        scored += len(rows); changed += [x["c"] for x in rows]
        print(f"  {name}: {len(rows)} written of {len(cs)} · total {scored} · {time.time() - t0:.0f}s", flush=True)
    ts.close()
    retired = []
    if retire:
        # a cell the current version cannot score keeps no older-version row alive (the same rule as the storm scorer)
        with get_session() as s:
            retired = s.execute(text("""UPDATE canonical_scores SET valid_to = :now WHERE hazard_type='flood' AND scenario='baseline' AND time_horizon='current'
                              AND valid_to IS NULL AND COALESCE(score_lane,'standing')='standing' AND h3_cell = ANY(:cells)
                              RETURNING h3_cell"""), {"now": now, "cells": retire}).scalars().all()
    print(f"wrote {scored} cells ({unchanged} unchanged kept their row); {missing} cells not readable; "
          f"{empty} had no land pixels; {len(retired)} live rows retired as undetermined")
    if project and (changed or retired):
        from scripts.project_scenarios import _asset_cells, project_cells
        with get_session() as s:                              # projections exist only for exposure cells (that job's scope)
            todo = sorted((set(changed) | set(retired)) & set(_asset_cells(s)))
            r = project_cells(s, todo, hazards=["flood"])
        print(f"re-projected flood forward for {r['cells']} changed exposure cells: {r['rows']} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(project="--project" in sys.argv))
