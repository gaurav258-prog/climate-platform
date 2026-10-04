"""Driver scores from the global weather build (E163): {harvest year: 0–100 score} for a target's season — the months of
the harvest year, and of the previous year for a season crossing the new year. A year missing any season month is not
scored.

  drought  drought_score of the season-mean SPEI-6 rounded to 2 dp (as the legacy box builder)
  heat     heat_anomaly_score of the season-mean temperature anomaly (rounded to 2 dp) standardised by the 1991–2020
           seasons' mean and sample sd — the WMO normal SPEI uses, so a new year is judged against a fixed reference
"""
from __future__ import annotations

import math

from sqlalchemy.orm import Session

from ml.scoring.drought_climatology import drought_score
from ml.scoring.heat_climatology import heat_anomaly_score
from services.calibration import crop_area_weights as W
from services.calibration import crop_weather

HEAT_REFERENCE = crop_weather.BASELINE


def map_key(commodity: str) -> str | None:
    cm = W.crop_map(commodity)
    return f"{cm['map']}:{'+'.join(cm['layers'])}" if cm else None


def seasonal(mon: dict, months: list[int], prev: list[int]) -> dict[int, tuple[float, float]]:
    """{harvest year: (season-mean SPEI-6, season-mean temperature anomaly)} — years with every season month."""
    out = {}
    for y in sorted({k[0] for k in mon}):
        vals = [mon.get(k) for k in [(y - 1, m) for m in prev] + [(y, m) for m in months]]
        if any(v is None or v[0] is None or v[1] is None for v in vals):
            continue
        out[y] = (sum(v[0] for v in vals) / len(vals), sum(v[1] for v in vals) / len(vals))
    return out


def driver_scores(seas: dict[int, tuple[float, float]], driver: str) -> dict[int, float]:
    if driver == "drought":
        return {y: drought_score(round(s, 2)) for y, (s, _t) in seas.items()}
    if driver == "heat":
        anoms = {y: round(t, 2) for y, (_s, t) in seas.items()}
        ref = [a for y, a in anoms.items() if HEAT_REFERENCE[0] <= y <= HEAT_REFERENCE[1]]
        if len(ref) < 3:
            return {}
        mean = sum(ref) / len(ref)
        sd = math.sqrt(sum((a - mean) ** 2 for a in ref) / (len(ref) - 1))
        return {y: heat_anomaly_score((a - mean) / sd) for y, a in anoms.items()} if sd > 0 else {}
    raise ValueError(f"driver '{driver}' has no panel from the weather build")


def target_of(sp: dict) -> str:
    if sp["weather_kind"] == "crop_area":
        return crop_weather.crop_target(sp["commodity"], sp["origin"])
    return crop_weather.box_target(sp["weather_key"])


def scores(session: Session, sp: dict) -> tuple[dict[int, float], dict]:
    """({year: score}, inputs read) for a recipe read from the weather build."""
    target = target_of(sp)
    inputs = {"kind": sp["weather_kind"], "key": sp["weather_key"], "target": target}
    if sp["driver"] == "drought" and sp["spei_scale"] != crop_weather.SCALE:
        return {}, {**inputs, "refused": f"the weather build holds SPEI-{crop_weather.SCALE}, the recipe asks SPEI-{sp['spei_scale']}"}
    if sp["weather_kind"] == "crop_area" and map_key(sp["commodity"]) != sp["weather_key"]:
        return {}, {**inputs, "refused": f"the registry's crop map is now '{map_key(sp['commodity'])}' — a new recipe "
                                         "replaces this one"}
    b = crop_weather.latest(session, target)
    if b is None:
        return {}, {**inputs, "build_id": None}
    inputs.update(build_id=b["build_id"], cells=b["cells"], weight=b["weight"], last_month=str(b["last_month"]))
    seas = seasonal(crop_weather.monthly(session, b["build_id"], target), list(sp["season_months"]),
                    list(sp["season_prev_months"]))
    return driver_scores(seas, sp["driver"]), inputs
