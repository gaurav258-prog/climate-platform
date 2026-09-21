"""Global station-extremes validators — the cold-wave, chronic-heat and heavy-precipitation channels against what
weather stations measured in Africa, Asia, Latin America & the Caribbean and Oceania (NOAA GHCN-Daily, public domain,
1991–2020). Extends services/validation/validators/station_extremes.py (EU+US) outside those two regions.

PRE-REGISTERED DESIGN (written before any score was computed; no tuning after seeing results)
  Observed targets — identical to the EU+US validator (extremes computed by scripts/ingest_ghcn_extremes.extremes):
    cold_wave     vs 1-in-10 coldest night (10th percentile of annual minimum TMIN), sign flipped (colder = higher);
    heat_chronic  vs mean days per year with TMAX >= 30 °C;
    heavy_precip  vs mean annual maximum 1-day precipitation (mm).
  Stations — scripts/ingest_ghcn_global.py: one per 1° box, >=20 complete years (>=330 daily values of TMIN/TMAX/PRCP)
    in 1991–2020, deterministic hash-ordered cap of 150 boxes per macro-region (data/ghcn_global/MANIFEST.md).
  Predicted — the PRODUCTION channel score at the station (on-demand point scorers of services/scoring/on_demand.py,
    baseline / current; canonical_scores when already scored). A station whose channel returns no score
    (status insufficient_data / error) is DROPPED from that channel — never filled.
  Metric — Spearman rank (kind 'rank'), pooled and per macro-region via strata; the platform's gates
    (core/validation_gates.py: pooled and per-region floors, min n for a regional claim, monotone bands, hides_failure)
    apply unchanged. Ledger hazard_type is the channel's own name; scope 'global_stations'. Method out_of_sample.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

DATA = Path(__file__).resolve().parents[3] / "data" / "ghcn_global" / "extremes.json"


def usable_score(res: Optional[dict]) -> Optional[float]:
    """The channel score from a point-scorer result, or None when it has no real score (never a fill)."""
    if not isinstance(res, dict) or res.get("status") not in ("scored", "cached_hit"):
        return None
    v = res.get("risk_score")
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def assemble(stations: list, obs_key: str, scores: dict, sign: float = 1.0) -> tuple:
    """Aligned (labels, predicted, observed, strata) for stations that have both an observation and a score."""
    lab, pred, obs, strata = [], [], [], []
    for s in stations:
        sc, o = scores.get(s["station_id"]), s.get(obs_key)
        if sc is None or o is None:
            continue
        lab.append(f"{s['station_id']} {s['name']}"); pred.append(float(sc)); obs.append(sign * float(o)); strata.append(s["region"])
    return lab, pred, obs, strata


def _scorer(hazard: str) -> Callable:
    from services.scoring.on_demand import SYNC_ON_DEMAND_SCORERS
    return SYNC_ON_DEMAND_SCORERS[hazard]


def _global_rank(hazard: str, obs_key: str, target: str, sign: float = 1.0):
    def run(session: Session) -> ValidationResult:
        stations = json.loads(DATA.read_text())["stations"]
        scorer = _scorer(hazard)
        scores: dict = {}
        for s in stations:
            try:
                scores[s["station_id"]] = usable_score(scorer(s["latitude"], s["longitude"]))
            except Exception:
                scores[s["station_id"]] = None
        lab, pred, obs, strata = assemble(stations, obs_key, scores, sign)
        return ValidationResult(
            hazard_type=hazard, kind="rank", predicted=pred, observed=obs, labels=lab, strata=strata,
            target_source=f"NOAA GHCN-Daily station observations 1991–2020 (Africa, Asia, Latin America, Oceania) — {target}",
            scope="global_stations", method="out_of_sample",
            data_vintage=f"{len(pred)}/{len(stations)} stations, 1 per 1° box, >=20 yr",
            notes=("production channel score at the station vs the independently observed extreme; rank skill pooled and per macro-region; "
                   "stations the channel could not score are dropped, never filled"),
        )
    return run


register("cold_wave_stations_global")(_global_rank("cold_wave", "coldest_1in10_c", "1-in-10 coldest night (°C)", sign=-1.0))
register("heat_chronic_stations_global")(_global_rank("heat_chronic", "hot_days_per_yr", "days ≥ 30 °C per year"))
register("heavy_precip_stations_global")(_global_rank("heavy_precip", "prcp_1day_max_mm", "mean annual max 1-day precip"))
