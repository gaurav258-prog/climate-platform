"""Run one calibration recipe on the data of the day (E162): read its yield series and weather, fit, judge both gates,
write the run and its audit-ledger entry together. A run never publishes anything — publication is reviewed
(services.calibration.publish).
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.features import yield_series
from ml.features.crop_fit import CropFit, fit_climate_on_score
from services.calibration import gates, weather
from services.validation.engine import ValidationResult, record_result

_SPEC_COLS = ("spec_id::text AS spec_id, commodity, origin, yield_source, yield_region, driver, weather_kind, "
              "weather_key, season_months, season_prev_months, spei_scale, allow_cycle, basis, protocol")


def spec(session: Session, spec_id: str) -> dict:
    r = session.execute(text(f"SELECT {_SPEC_COLS} FROM crop_calibration_specs WHERE spec_id = CAST(:s AS uuid)"),
                        {"s": spec_id}).mappings().first()
    if r is None:
        raise KeyError(f"calibration recipe {spec_id} not found")
    return dict(r)


def active_specs(session: Session) -> list[dict]:
    return [dict(r) for r in session.execute(text(f"""
        SELECT {_SPEC_COLS} FROM crop_calibration_specs WHERE retired_at IS NULL
        ORDER BY commodity, origin, yield_region, driver""")).mappings()]


def _fingerprint(series: dict) -> str:
    return hashlib.sha256(json.dumps(sorted(series.items())).encode()).hexdigest()[:16]


def _last_landed(session: Session, source: str) -> Optional[str]:
    return session.execute(text("""SELECT release_id::text FROM crop_yield_releases WHERE source = :s AND status = 'landed'
                                   ORDER BY seq DESC LIMIT 1"""), {"s": source}).scalar()


def evaluate(session: Session, sp: dict) -> dict:
    """The run's figures for a recipe — nothing written. {outcome, reason, fit, scores, upside, inputs}."""
    production = yield_series.series(session, sp["commodity"], sp["origin"], sp["yield_source"], sp["yield_region"])
    scores, weather_inputs = weather.scores(session, sp)
    inputs = {"yield": {"source": sp["yield_source"], "region": sp["yield_region"],
                        "years": [min(production), max(production)] if production else None,
                        "series_sha": _fingerprint(production), "last_landed_release": _last_landed(session, sp["yield_source"])},
              "weather": weather_inputs, "protocol": gates.protocol()["protocol"]}
    if not scores:
        return {"outcome": "no_panel", "reason": "no weather panel for the recipe", "inputs": inputs}
    if not production:
        return {"outcome": "no_panel", "reason": f"{sp['yield_source']} holds no series for the crop and origin",
                "inputs": inputs}
    fit: Optional[CropFit] = fit_climate_on_score(production, scores, sp["driver"], allow_cycle=sp["allow_cycle"])
    if fit is None:
        return {"outcome": "too_few_years", "reason": "fewer than 12 years with a full trend window and a score",
                "inputs": inputs}
    if not gates.downside_pass(fit.r2_oos):          # the upside is judged only on a fit that passes the downside gate
        up = {"pass": False, "judged": False, "failed": ["not judged — the fit does not pass the downside gate"]}
    else:
        pts = [(scores[y], obs, y) for (y, _p, obs) in fit.loo_samples]
        area = yield_series.series(session, sp["commodity"], sp["origin"], sp["yield_source"], sp["yield_region"],
                                   field="area_harvested_ha")
        up = {**gates.upside(pts, area), "judged": True}
    return {"outcome": "fitted", "reason": None, "fit": fit, "scores": scores, "upside": up, "inputs": inputs}


def _ledger(session: Session, sp: dict, fit: CropFit) -> str:
    years = [y for (y, _p, _o) in fit.loo_samples]
    res = ValidationResult(
        hazard_type=f"crop_{sp['driver']}", kind="regression",
        predicted=[p for (_y, p, _o) in fit.loo_samples], observed=[o for (_y, _p, o) in fit.loo_samples],
        labels=[str(y) for y in years], target_source=f"{sp['commodity']} ({sp['origin']}) observed yield — leave-one-out CV",
        scope=f"{sp['commodity']}/{sp['origin']}", method="loo_cv",
        data_vintage=f"leave-one-out over {fit.n_years} years",
        notes=(f"calibration pipeline run of recipe {sp['spec_id']} ({sp['protocol']}): {sp['driver']} → yield anomaly, "
               f"weather {sp['weather_kind']} '{sp['weather_key']}', months {list(sp['season_months'])}"
               + (f" + previous-year {list(sp['season_prev_months'])}" if sp["season_prev_months"] else "")
               + f"; r²_oos={fit.r2_oos}. Production source '{sp['yield_source']}'"
               + (f" region {sp['yield_region']}" if sp["yield_region"] else "") + f"; cycle-decompose={sp['allow_cycle']}."))
    return record_result(session, res, actor="calibration_pipeline", persist_samples=True, commit=False)["run_id"]


def run(session: Session, sp: dict) -> dict:
    """Evaluate a recipe and record the run (status 'recorded') with its ledger entry. Not committed here."""
    ev = evaluate(session, sp)
    fit: Optional[CropFit] = ev.get("fit")
    row = {"spec": sp["spec_id"], "inputs": json.dumps(ev["inputs"]), "outcome": ev["outcome"], "reason": ev["reason"],
           "n": None, "bf": None, "bt": None, "slope": None, "intercept": None, "r2": None, "r2oos": None, "rmse": None,
           "mean": None, "sxx": None, "cov": None, "down": False, "upside": None, "up": False, "vr": None}
    if fit is not None:
        up = ev["upside"]
        down = gates.downside_pass(fit.r2_oos)
        row.update(n=fit.n_years, bf=fit.years[0], bt=fit.years[-1], slope=round(fit.slope, 5),
                   intercept=round(fit.intercept, 5), r2=round(fit.r2, 4), r2oos=fit.r2_oos, rmse=round(fit.rmse, 5),
                   mean=round(fit.score_mean, 5), sxx=round(fit.score_sxx, 5), cov=fit.band_cov68, down=down,
                   upside=json.dumps(up), up=bool(up["pass"]), vr=_ledger(session, sp, fit))
    run_id = session.execute(text("""
        INSERT INTO crop_calibration_runs (spec_id, inputs, outcome, reason, n_years, baseline_from, baseline_to, slope,
               intercept, r2, r2_oos, rmse, score_mean, score_sxx, band_cov68, downside_pass, upside, upside_pass,
               validation_run_id)
        VALUES (CAST(:spec AS uuid), CAST(:inputs AS jsonb), :outcome, :reason, :n, :bf, :bt, :slope, :intercept, :r2,
                :r2oos, :rmse, :mean, :sxx, :cov, :down, CAST(:upside AS jsonb), :up, CAST(:vr AS uuid))
        RETURNING run_id::text"""), row).scalar()
    return {"run_id": run_id, "spec_id": sp["spec_id"], "commodity": sp["commodity"], "origin": sp["origin"],
            "driver": sp["driver"], "outcome": ev["outcome"], "r2_oos": row["r2oos"], "downside_pass": row["down"],
            "upside_pass": row["up"], "upside_failed": (ev.get("upside") or {}).get("failed")}
