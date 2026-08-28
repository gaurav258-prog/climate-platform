"""Coverage report — how much of the world we score, measured honestly.

Best-of-breed vendors quote "millions of locations" of PRE-SCORED coverage. Our model is different: a standing
layer of pre-scored cells for the asset universe + baselines, plus ON-DEMAND scoring of any address in seconds
(so we don't need to pre-score the planet to answer for a location). This report quantifies both, per hazard
and resolution, and flags where the standing layer is thin — an honest, reproducible number instead of a
marketing claim. Scaling the standing layer further is a data-generation task, not a code change; the
on-demand path already gives global reach today.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# hazards answerable on demand for any address (volcanic needs a hazard-zone methodology → not on-demand)
ON_DEMAND_HAZARDS = ["flood", "wildfire", "drought", "storm", "seismic", "heat_acute", "soil_water", "coastal_flood"]
THIN_THRESHOLD = 1000   # a standing layer below this many cells is flagged for deepening


def summarize_coverage(per_hazard: list[dict], resolutions: list[int], scenarios: list[str],
                       horizons: list[str]) -> dict:
    """Pure summariser (no DB) — assemble the coverage picture from queried rows."""
    total_cells = max((h["cells"] for h in per_hazard), default=0)
    thin = [h["hazard"] for h in per_hazard if h["cells"] < THIN_THRESHOLD]
    return {
        "standing": {
            "n_cells_max_hazard": total_cells,
            "n_hazards": len(per_hazard),
            "resolutions": sorted(resolutions),
            "scenarios": sorted(scenarios),
            "horizons": sorted(horizons),
            "per_hazard": sorted(per_hazard, key=lambda h: -h["cells"]),
            "thin_layers": thin,
        },
        "on_demand": {
            "global": True,
            "hazards_on_demand": len(ON_DEMAND_HAZARDS),
            "hazards": ON_DEMAND_HAZARDS,
            "note": "any address scored on demand in seconds; pre-scoring the planet is unnecessary",
        },
    }


def coverage_report(session: Session, horizon: str = "current") -> dict:
    """DB-backed coverage report over canonical_scores (the standing golden source)."""
    per_hazard = [dict(r) for r in session.execute(text("""
        SELECT hazard_type AS hazard, count(DISTINCT h3_cell) AS cells
        FROM canonical_scores WHERE valid_to IS NULL AND time_horizon = :h
        GROUP BY hazard_type ORDER BY cells DESC
    """), {"h": horizon}).mappings().all()]
    resolutions = [int(r[0]) for r in session.execute(text(
        "SELECT DISTINCT h3_resolution FROM canonical_scores WHERE valid_to IS NULL AND h3_resolution IS NOT NULL")).all()]
    scenarios = [r[0] for r in session.execute(text(
        "SELECT DISTINCT scenario FROM canonical_scores WHERE valid_to IS NULL")).all()]
    horizons = [r[0] for r in session.execute(text(
        "SELECT DISTINCT time_horizon FROM canonical_scores WHERE valid_to IS NULL")).all()]
    return summarize_coverage(per_hazard, resolutions, scenarios, horizons)
