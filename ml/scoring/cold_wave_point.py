"""Cold-wave hazard at an arbitrary point — extreme cold as a BUILDING hazard, not the crop-frost scale.

What damages a building in a cold wave is cold beyond what it was built for: frozen and burst pipes, heating
failure, ice loading. Two things therefore set the score, both from 30 years (1991–2020) of daily 2 m minimum
temperature at the location (NASA POWER, MERRA-2, read on demand):

  • absolute severity  a = how far the 1-in-10 coldest night (10th percentile of the 30 annual minima) falls below
    the pipe-freeze onset of −6.7 °C (20 °F, IBHS/plumbing-code guidance), saturating at −30 °C;
  • design exceedance  d = how far that 1-in-10 night falls below the location's own 99.6 % heating design
    temperature (ASHRAE convention: the 0.4th percentile of daily minima) — beyond about 4 °C the tail is
    heavier than the stock was built for, saturating at 12 °C (Texas, February 2021: ≈ 12–15 °C below design).

score = 100 · (0.6·a + 0.4·d), clipped. Warming shifts the coldest night up by the same parametric delta the frost
channel uses (AR6, latitude-amplified). A location the API cannot serve returns insufficient_data — never a 0.
Screening tier: physically anchored thresholds, not yet backtested against an insured cold-loss record.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

MODEL_VERSION = "cold-wave-power-tmin-v1"
FREEZE_ONSET_C, FREEZE_SEVERE_C = -6.7, -30.0
DESIGN_DEFICIT_ONSET_C, DESIGN_DEFICIT_SEVERE_C = 4.0, 12.0


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _daily_tmin(lat_r: float, lon_r: float) -> Optional[dict]:
    """{'annual_min': [...], 'design_c': float, 'n_days': int, 'n_years': int} from NASA POWER, or None."""
    from ml.scoring.power_daily import daily_by_year
    by_year = daily_by_year(lat_r, lon_r, "T2M_MIN")
    if not by_year:
        return None
    all_days = sorted(v for vals in by_year.values() for v in vals)
    annual_min = sorted(min(vals) for vals in by_year.values())
    return {"annual_min": annual_min, "design_c": all_days[max(0, int(0.004 * len(all_days)) - 1)], "n_days": len(all_days), "n_years": len(by_year)}


def cold_wave_score(annual_min: list[float], design_c: float, warming_c: float = 0.0) -> tuple[float, dict]:
    t10 = annual_min[max(0, int(0.10 * len(annual_min)) - 1)] + warming_c            # 1-in-10 coldest night, warmed
    a = _clip01((FREEZE_ONSET_C - t10) / (FREEZE_ONSET_C - FREEZE_SEVERE_C))
    deficit = (design_c + warming_c) - t10
    d = _clip01((deficit - DESIGN_DEFICIT_ONSET_C) / (DESIGN_DEFICIT_SEVERE_C - DESIGN_DEFICIT_ONSET_C))
    score = round(100.0 * (0.6 * a + 0.4 * d), 2)
    return score, {"coldest_night_1in10_c": round(t10, 2), "design_temperature_c": round(design_c + warming_c, 2), "design_deficit_c": round(deficit, 2),
                   "absolute_severity": round(a, 3), "design_exceedance": round(d, 3), "warming_shift_c": round(warming_c, 2)}


def score_cold_wave_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
                               WHERE hazard_type='cold_wave' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL"""),
                       {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}
    clat, clon = h3.cell_to_latlng(cell)
    stats = _daily_tmin(round(clat, 3), round(clon, 3))
    if stats is None:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "NASA POWER daily minimum temperature is not available for this location."}
    from ml.scoring.frost_climatology import warming_delta
    risk, detail = cold_wave_score(stats["annual_min"], stats["design_c"], warming_delta(scenario, horizon, lat))
    now = datetime.now(timezone.utc)
    shap = {**detail, "n_years": stats["n_years"], "on_demand": True, "source": "NASA POWER (MERRA-2) daily T2M_MIN 1991–2020",
            "method": "1-in-10 coldest night vs pipe-freeze onset −6.7 °C (0.6) and vs the location's 99.6 % design temperature (0.4); parametric warming shift"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'cold_wave', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane) WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk, "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
