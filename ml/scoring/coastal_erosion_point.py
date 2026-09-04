"""Coastal-erosion hazard at an arbitrary point — reads the preprocessed shoreline-retreat H3 lookup.

A SCREENING-tier PROJECTION channel: the median projected long-term shoreline retreat (metres) at the asset's
coastal cell under a climate scenario × horizon, from Vousdoukas et al. (2020, JRC LISCOAST) — SLR + ambient
change. Only a RETREAT (negative shoreline change) is a hazard; accretion scores ~0. Because it is inherently
forward-looking and scenario-specific, it is defined ONLY under a projection scenario × horizon (baseline /
current return 'insufficient_data'), and only within ~res-8 of a modelled sandy coast (interior points return
'insufficient_data' — never a fabricated 0). The data lands via scripts/ingest_coastal_erosion.py.

Scenario/horizon → (RCP, year): the dataset carries RCP4.5 / RCP8.5 at 2050 / 2100. We map orderly/disorderly
→ RCP4.5, hot-house → RCP8.5; horizon 2030→2050 (nearest), 2050→2050, 2100→2100.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

MODEL_VERSION = "coastal-erosion-liscoast-v1"
_RETREAT_K = 72.0   # metres of retreat: 50→50, 100→75, 200→94 (saturating)

_SCENARIO_TO_RCP = {"orderly_1_5c": "rcp45", "disorderly_2c": "rcp45", "hot_house_3_5c": "rcp85"}
_HORIZON_TO_YEAR = {"2030": 2050, "2050": 2050, "2100": 2100}


def erosion_score(retreat_m: float) -> float:
    """Retreat magnitude (metres, only the erosion sign) → 0–100. Accretion (positive change) → 0."""
    if retreat_m >= 0:
        return 0.0
    return round(max(0.0, min(100.0, 100.0 * (1.0 - math.exp(-abs(float(retreat_m)) / _RETREAT_K)))), 2)


def _lookup(cell: str, rcp: str, year: int) -> Optional[float]:
    with get_session() as s:
        r = s.execute(text("""
            SELECT CAST(retreat_m AS FLOAT) rm FROM coastal_erosion_cell
            WHERE h3_cell=:c AND rcp=:rcp AND year=:y
        """), {"c": cell, "rcp": rcp, "y": year}).mappings().first()
    return r["rm"] if r else None


def score_coastal_erosion_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Projected coastal-erosion retreat at (lat, lon); caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'insufficient_data' at baseline/current, inland, or if unbuilt."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='coastal_erosion' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    rcp = _SCENARIO_TO_RCP.get(scenario)
    year = _HORIZON_TO_YEAR.get(horizon)
    if not (rcp and year):
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "coastal erosion is a forward projection — pick a projection scenario (orderly/disorderly/hot_house) × horizon (2050/2100)"}
    retreat = _lookup(h3.cell_to_parent(cell, 7), rcp, year)   # coastal_erosion_cell is keyed at res-7
    if retreat is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no modelled sandy-coast shoreline within this cell (interior point, or not a monitored coast)"}

    risk = erosion_score(retreat)
    now = datetime.now(timezone.utc)
    shap = {"projected_retreat_m": round(retreat, 1), "rcp": rcp, "year": year, "on_demand": True, "tier": "screening",
            "method": "Vousdoukas et al. (2020, JRC LISCOAST) median long-term shoreline change (SLR + ambient); retreat magnitude, screening"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'coastal_erosion', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
