"""Volcanic hazard at an arbitrary point, fetch-free at runtime — Smithsonian GVP catalogue + radial physics.

SCREENING-tier. For a (lat, lon) we take every Holocene volcano in the GVP catalogue
(data/reference/gvp_holocene_volcanoes.json, scripts/fetch_gvp_catalogue.py) within INFLUENCE_KM and score the
worst one with the two-component physics in ml/scoring/volcanic_physics.py: a near-binary proximal zone
(lava / pyroclastic flow / lahar) and a gradual ashfall zone. Footprint radii come from, in order:
  1. a curated volcanic_hazard_zones row (published hazard map, per volcano)  → radii_source "curated:…"
  2. VEI-scaled defaults from the volcano's largest CONFIRMED Holocene eruption → "vei_scaled_from_catalogue"
  3. when GVP records no VEI for it at all, the VEI-3 default                   → "vei_unknown_default3"
Honesty posture, disclosed in shap_factors and core/hazard_taxonomy.py: radially symmetric (no wind direction,
no valley topography), eruption recency is REPORTED (last_eruption_year, eruptions since 1900) but NOT weighted
into the score — there is no defensible recurrence model for a location-level backtest, so this stays a
SCREENING indicator and never carries a € (see docs/VOLCANIC_HAZARD_METHODOLOGY.md). Geophysical: the score is
the same under every climate scenario/horizon. "No Holocene volcano within INFLUENCE_KM" is a real answer (score
0), not insufficient data; 'insufficient_data' is returned only when the catalogue file itself is missing.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.volcanic_physics import blended_volcanic_score, vei_to_zone_radii

MODEL_VERSION = "volcanic-gvp-radial-v1"
INFLUENCE_KM = 150.0        # beyond this even a VEI-7 ashfall footprint (~113 km radius) has decayed to background
_CATALOGUE_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "gvp_holocene_volcanoes.json"
_DEFAULT_VEI = 3.0          # what vei_to_zone_radii assumes when VEI is unknown — named here so the shap can say so

_catalogue: Optional[dict] = None


def _load_catalogue() -> Optional[dict]:
    global _catalogue
    if _catalogue is None and _CATALOGUE_PATH.exists():
        _catalogue = json.loads(_CATALOGUE_PATH.read_text())
    return _catalogue


def haversine_km(la1: float, lo1: float, la2: float, lo2: float) -> float:
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _curated_zones(session, volcano_number: int) -> Optional[tuple[float, float, str]]:
    rows = session.execute(text("""
        SELECT zone_type, CAST(radius_km AS FLOAT) radius_km, source
        FROM volcanic_hazard_zones WHERE volcano_number = :v
    """), {"v": volcano_number}).mappings().all()
    z = {r["zone_type"]: r for r in rows}
    if "proximal" in z and "ashfall" in z:
        return z["proximal"]["radius_km"], z["ashfall"]["radius_km"], f"curated:{z['proximal']['source']}"
    return None


def volcanic_exposure(lat: float, lon: float, volcanoes: list[dict],
                      curated: Callable[[int], Optional[tuple[float, float, str]]] = lambda n: None) -> dict:
    """Pure scorer (no DB, no I/O): worst-volcano blended score at (lat, lon) over `volcanoes` (catalogue rows).
    `curated(volcano_number)` may supply (r_proximal_km, r_ash_km, source) from a published hazard map.
    Returns {risk_score, shap} — risk_score 0 with the nearest volcano reported when none is within INFLUENCE_KM."""
    # candidate window = 3x the influence radius so a "nearest volcano" can still be named when none is in range
    dlat = 3.0 * INFLUENCE_KM / 111.0
    dlon = dlat / max(math.cos(math.radians(lat)), 0.05)
    best: Optional[dict] = None
    nearest: Optional[tuple[float, dict]] = None
    n_in_range = 0
    for v in volcanoes:
        if abs(v["lat"] - lat) > dlat or abs(v["lon"] - lon) > dlon:
            continue
        d = haversine_km(lat, lon, v["lat"], v["lon"])
        if nearest is None or d < nearest[0]:
            nearest = (d, v)
        if d > INFLUENCE_KM:
            continue
        n_in_range += 1
        zones = curated(v["volcano_number"])
        if zones:
            r_prox, r_ash, radii_source = zones
            vei_ref = v.get("max_vei")
        elif v.get("max_vei") is not None:
            vei_ref = float(v["max_vei"])
            r_prox, r_ash = vei_to_zone_radii(vei_ref)
            radii_source = "vei_scaled_from_catalogue"
        else:
            vei_ref = None
            r_prox, r_ash = vei_to_zone_radii(_DEFAULT_VEI)
            radii_source = "vei_unknown_default3"
        blended, prox, ash = blended_volcanic_score(d, r_prox, r_ash)
        score = float(blended)
        if best is None or score > best["risk_score"]:
            best = {"risk_score": score, "volcano": v["name"], "volcano_number": v["volcano_number"],
                    "country": v.get("country"), "volcano_type": v.get("type"), "driver_dist_km": round(d, 1),
                    "vei_reference": vei_ref, "radii_source": radii_source,
                    "r_proximal_km": round(r_prox, 1), "r_ashfall_km": round(r_ash, 1),
                    "proximal_score": round(float(prox), 1), "ashfall_score": round(float(ash), 1),
                    "last_eruption_year": v.get("last_eruption_year"),
                    "eruptions_since_1900": v.get("n_eruptions_since_1900", 0)}

    shap: dict = {"on_demand": True, "tier": "screening", "model": MODEL_VERSION,
                  "volcanoes_within_influence": n_in_range, "influence_km": INFLUENCE_KM,
                  "method": "Smithsonian GVP Holocene catalogue; worst volcano by radial proximal+ashfall physics, "
                            "footprint from curated hazard map else VEI-scaled default; radially symmetric (no wind / "
                            "topography); recency reported, not weighted; geophysical — no climate scenario response"}
    if best is None:
        shap["reason"] = f"no Holocene volcano within {INFLUENCE_KM:.0f} km"
        if nearest is not None:
            shap["nearest_volcano"], shap["nearest_volcano_km"] = nearest[1]["name"], round(nearest[0], 1)
        return {"risk_score": 0.0, "shap": shap}
    shap.update(best)
    return {"risk_score": round(best["risk_score"], 2), "shap": shap}


def score_volcanic_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Volcanic screening score at (lat, lon); caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'insufficient_data' only when the GVP catalogue is not landed."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='volcanic' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    cat = _load_catalogue()
    if cat is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "The volcano catalogue is not currently available."}

    with get_session() as s:
        out = volcanic_exposure(lat, lon, cat["volcanoes"], curated=lambda n: _curated_zones(s, n))
    risk, shap = out["risk_score"], out["shap"]
    shap["catalogue_fetched_at"] = cat.get("fetched_at")
    now = datetime.now(timezone.utc)
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'volcanic', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
