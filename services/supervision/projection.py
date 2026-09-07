"""Scenario projections for a supervisor's SHADOW BOOK — the same two paths a bank's own cells take.

A bank's own cells get forward values two ways: (1) every fetch-free point scorer accepts (scenario, horizon)
and computes the anchor itself (heat, coastal / sea level, heavy precip, CMIP6 'changing-x' channels …);
(2) flood / storm / wildfire are projected from today's score through local CMIP6 deltas
(scripts/project_scenarios.project_cells). A fresh shadow book only has baseline/current, so the lens cannot
separate a 'basis' effect. This module runs both paths for the shadow cells, in a daemon thread, and reports
coverage so the intake screen can say how far along the projections are. Nothing is fabricated: a scorer that
does not vary with scenario returns the same standing value under every anchor — and says so in its own row.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import h3
from sqlalchemy import text

from core.db.session import get_session

SCENARIOS = ["baseline", "orderly_1_5c", "disorderly_2c", "hot_house_3_5c"]
HORIZONS = ["current", "2030", "2050", "2100"]
ANCHORS = [(sc, hz) for sc in SCENARIOS for hz in HORIZONS if (sc, hz) != ("baseline", "current")]


def shadow_cells(session, regulator_org_id: str, subject_org_id: str) -> list[str]:
    return [r[0] for r in session.execute(text("""
        SELECT DISTINCT h3_cell FROM portfolio_entities
        WHERE org_id = CAST(:r AS uuid) AND source = 'supervisor_shadow' AND subject_org_id = CAST(:s AS uuid) AND h3_cell IS NOT NULL
    """), {"r": regulator_org_id, "s": subject_org_id})]


def _score_anchor(lat: float, lon: float, scenario: str, horizon: str) -> None:
    from services.scoring.on_demand import SYNC_ON_DEMAND_SCORERS
    for scorer in SYNC_ON_DEMAND_SCORERS.values():
        try:
            scorer(lat, lon, scenario=scenario, horizon=horizon)
        except TypeError:
            pass          # scenario-invariant scorer with a (lat, lon) signature: its baseline row already exists
        except Exception:
            pass          # one hazard on one cell must never abort the projection


def project_cells_now(cells: list[str]) -> dict:
    """Synchronous: point scorers at every anchor (thread pool) + CMIP6 projection for flood/storm/wildfire."""
    if not cells:
        return {"cells": 0, "anchors": len(ANCHORS), "cmip6_rows": 0}
    coords = {c: h3.cell_to_latlng(c) for c in cells}
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="shadow-proj") as ex:
        for lat, lon in coords.values():
            for sc, hz in ANCHORS:
                ex.submit(_score_anchor, lat, lon, sc, hz)
    from scripts.project_scenarios import project_cells
    with get_session() as s:
        r = project_cells(s, cells)
    return {"cells": len(cells), "anchors": len(ANCHORS), "cmip6_rows": r["rows"]}


def schedule_projection(cells: list[str]) -> None:
    """Fire-and-forget (daemon thread) — the intake screen polls coverage while it runs."""
    if cells:
        threading.Thread(target=project_cells_now, args=(list(cells),), name="shadow-projection", daemon=True).start()


def projection_coverage(session, cells: list[str]) -> dict:
    """How many (scenario, horizon) anchors each shadow cell has at least one standing row for — 15 = complete."""
    if not cells:
        return {"cells": 0, "anchors_total": len(ANCHORS), "anchors_covered_mean": 0, "complete": False}
    rows = session.execute(text("""
        SELECT h3_cell, count(DISTINCT (scenario, time_horizon)) AS n
        FROM canonical_scores WHERE valid_to IS NULL AND COALESCE(score_lane,'standing') = 'standing'
          AND h3_cell = ANY(:cells) AND NOT (scenario = 'baseline' AND time_horizon = 'current')
        GROUP BY h3_cell
    """), {"cells": list(cells)}).all()
    per = {c: 0 for c in cells}
    for c, n in rows:
        per[c] = int(n)
    mean = round(sum(per.values()) / len(per), 1)
    return {"cells": len(cells), "anchors_total": len(ANCHORS), "anchors_covered_mean": mean,
            "cells_complete": sum(1 for v in per.values() if v >= len(ANCHORS)), "complete": all(v >= len(ANCHORS) for v in per.values())}
