"""Champion out-of-sample runs — put the euro engine's OWN leave-one-out skill onto the audit record.

The published crop calibration (`sc_commodity_fit`) already carries a genuine leave-one-out cross-validated
r² (`ml/features/crop_fit.py`), and the ranged tier only publishes a euro when that number clears the 0.40
floor. But that honest number lived only in the fit table — not in the append-only `validation_run` ledger the
validation framework and auditors read. This module closes that gap: for each published fit it rebuilds the
SAME panel (identical score builder, production, cycle handling) the calibration used, recomputes the champion
leave-one-out, and records the per-year (predicted, observed) pairs into the ledger with `method='loo_cv'`.

It does not trust that the rebuild matches — it VERIFIES: the source that reproduces the stored r²_oos within
tolerance is the one recorded, and the reconciliation (recomputed vs stored) is written into the run's notes.
So the number the product gates on and the number on the audit record are provably the same, with drill-down.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.features.crop_cycle import is_alternate_bearing
from ml.features.crop_fit import CropFit, fit_climate_on_score
from ml.features.crop_panel import scores_for
from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR
from services.validation.engine import ValidationResult, record_result

NC_MONTHLY = "data/era5_baseline/{region}_1991_2024_monthly.nc"
RECONCILE_TOL = 0.02   # recomputed leave-one-out r² must match the published stored number within this


@dataclass
class Outcome:
    result: ValidationResult
    scope: str
    reconciled: bool
    stored_oos: Optional[float]
    recomputed_oos: float
    gap: float
    source: str                 # the production series that best reproduces the stored fit
    fit_meta: dict              # commodity/origin/region/driver/spei_scale/months — to re-fit if drifted

    @property
    def publish_flip(self) -> bool:
        """Does the recomputed OOS cross the publish floor in the OTHER direction from the stored value?
        A True here is a product decision (a euro would start or stop publishing), not a silent code change."""
        if self.stored_oos is None:
            return False
        return (self.recomputed_oos >= RANGED_PUBLISH_FLOOR) != (self.stored_oos >= RANGED_PUBLISH_FLOOR)


def _fits(session: Session):
    return session.execute(text("""
        SELECT c.name, f.origin, f.region_key, f.hazard_driver, f.season_months, f.spei_scale,
               f.r2, f.r2_oos, f.n_years
        FROM sc_commodity_fit f JOIN sc_commodities c ON c.commodity_id = f.commodity_id
        WHERE f.region_key IS NOT NULL AND f.hazard_driver IS NOT NULL
        ORDER BY c.name, f.origin
    """)).mappings().all()


def _production_by_source(session: Session, commodity: str, origin: str) -> dict:
    """{source: {year: production_tonnes}}. The fit used one source; we pick the source that reproduces the
    stored fit rather than guessing, because some origins carry two agencies' series (e.g. FAOSTAT + EUROSTAT)."""
    rows = session.execute(text("""
        SELECT source, season_year, production_tonnes FROM crop_yield_observations
        WHERE commodity = :c AND country = :o AND production_tonnes IS NOT NULL
        ORDER BY season_year
    """), {"c": commodity, "o": origin}).all()
    out: dict = {}
    for src, yr, p in rows:
        out.setdefault(src, {})[int(yr)] = float(p)
    return out


def build_result(session: Session, fit) -> Optional[Outcome]:
    """Reconstruct one published fit's champion leave-one-out. Returns an Outcome (result + reconciliation),
    or None when the region's ERA5 panel isn't on disk / no source yields a fittable panel."""
    region, driver = fit["region_key"], fit["hazard_driver"]
    months = list(fit["season_months"] or [])
    if not months or not os.path.exists(NC_MONTHLY.format(region=region)):
        return None
    scores = scores_for(region, driver, months, fit["spei_scale"] or 6)
    if not scores:
        return None
    allow_cycle = is_alternate_bearing(fit["name"])
    stored_oos = float(fit["r2_oos"]) if fit["r2_oos"] is not None else None

    best: Optional[tuple[float, str, CropFit]] = None
    for src, prod in _production_by_source(session, fit["name"], fit["origin"]).items():
        cf = fit_climate_on_score(prod, scores, driver, allow_cycle=allow_cycle)
        if cf is None or not cf.loo_samples:
            continue
        gap = abs((cf.r2_oos or 0.0) - (stored_oos if stored_oos is not None else (cf.r2_oos or 0.0)))
        if best is None or gap < best[0]:
            best = (gap, src, cf)
    if best is None:
        return None

    gap, src, cf = best
    reconciled = stored_oos is not None and gap <= RECONCILE_TOL
    scope = f"{fit['name']}/{fit['origin']}"
    years = [y for (y, _p, _o) in cf.loo_samples]
    preds = [p for (_y, p, _o) in cf.loo_samples]
    obs = [o for (_y, _p, o) in cf.loo_samples]
    recon = ("reconciled with the published fit" if reconciled
             else f"differs from stored r²_oos={fit['r2_oos']} by {gap:.3f} — fit table stale vs current "
                  f"ERA5/spec; NOT recorded until re-fit" if stored_oos is not None
             else "no stored r²_oos to reconcile against")
    res = ValidationResult(
        hazard_type=f"crop_{driver}", kind="regression",
        predicted=preds, observed=obs, labels=[str(y) for y in years],
        target_source=f"{fit['name']} ({fit['origin']}) observed yield — leave-one-out CV",
        scope=scope, method="loo_cv",
        data_vintage=f"leave-one-out over {cf.n_years} years",
        notes=(f"euro champion ({driver}→yield anomaly, {region}, months {months}) leave-one-out over "
               f"{cf.n_years} years — the SAME out-of-sample test the ranged tier publishes on, now on the "
               f"audit record. Recomputed r²_oos={cf.r2_oos} vs stored {fit['r2_oos']}: {recon}. "
               f"Production source '{src}'; cycle-decompose={allow_cycle}."),
    )
    return Outcome(result=res, scope=scope, reconciled=reconciled, stored_oos=stored_oos,
                   recomputed_oos=cf.r2_oos or 0.0, gap=gap, source=src,
                   fit_meta={"commodity": fit["name"], "origin": fit["origin"], "region": region,
                             "driver": driver, "spei_scale": fit["spei_scale"] or 6, "months": months})


def record_all(session: Session, *, actor: str = "champion_oos", persist_samples: bool = True,
               require_reconciled: bool = True) -> dict:
    """Record a champion leave-one-out run into the immutable ledger for every published fit that reconstructs
    AND reconciles with its published number (`require_reconciled`, the default — we never write a number that
    disagrees with what the product publishes). Returns {recorded, skipped} so the caller can surface the
    drifted fits for a controlled re-fit rather than silently recording a divergent value."""
    recorded: list[dict] = []
    skipped: list[dict] = []
    for fit in _fits(session):
        o = build_result(session, fit)
        if o is None:
            continue
        if require_reconciled and not o.reconciled:
            skipped.append({"scope": o.scope, "stored_oos": o.stored_oos, "recomputed_oos": o.recomputed_oos,
                            "gap": round(o.gap, 4), "publish_flip": o.publish_flip})
            continue
        summary = record_result(session, o.result, actor=actor, persist_samples=persist_samples)
        summary["scope"] = o.scope
        recorded.append(summary)
    return {"recorded": recorded, "skipped": skipped}
