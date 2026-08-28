"""Validation engine — run a registered backtest, compute the honest metric for its kind, and write an
append-only, fully-provenanced validation record.

Scalability by design: a validator is just a function `Session -> ValidationResult` registered under a key;
adding a hazard/target means writing one validator and `@register(...)`-ing it — the engine, metrics, gating,
recording and audit trail are shared. The engine picks the metric family from `kind` (regression → R²-gated;
discrimination → rank/AUC + band-monotonicity gated) so no model is judged by a metric that doesn't fit it.

The result is written to `validation_run` (immutable by DB trigger); optionally every (predicted, observed)
pair is written to `validation_sample` for full auditor drill-down. When the run is tied to a registered
model, its headline skill is the number the honesty gate / MLOps approval reads — closing the loop
backtest → gate → governance.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.validation import metrics as M

VALIDATION_VERSION = "val-v1"


@dataclass
class ValidationResult:
    hazard_type: str
    kind: str                       # 'regression' | 'discrimination'
    predicted: list                 # model output (score / predicted value)
    observed: list                  # the INDEPENDENT observed truth
    target_source: str              # where that truth came from (EMSC / IBTrACS / FAO / …)
    scope: Optional[str] = None     # region / commodity / 'global'
    horizon: Optional[str] = None
    method: str = "in_sample"       # in_sample | out_of_sample | temporal_holdout — labelled honestly
    model_id: Optional[str] = None  # a registered model, if this validates one
    data_vintage: Optional[str] = None
    notes: Optional[str] = None
    labels: Optional[list] = None   # per-sample ids, for the drill-down


Validator = Callable[[Session], ValidationResult]
REGISTRY: dict[str, Validator] = {}


def register(key: str):
    def deco(fn: Validator) -> Validator:
        REGISTRY[key] = fn
        return fn
    return deco


def _round(v):
    return round(v, 4) if isinstance(v, float) else v


def _compute(res: ValidationResult):
    """Return (metrics dict, grade, passed_gate, gate_label) using the honest metric for res.kind."""
    pred = np.asarray(res.predicted, float)
    obs = np.asarray(res.observed, float)
    n = int(len(pred))
    if res.kind == "regression":
        r2 = M.r2_oos(pred, obs)
        metrics = {"r2_oos": r2, "rmse": M.rmse(pred, obs), "mae": M.mae(pred, obs), "bias": M.bias(pred, obs)}
        grade = M.grade_regression(r2)
        passed = M.passes_regression_gate(r2)
        gate = f"regression_r2>={M.REGRESSION_GATE_R2}"
    elif res.kind == "discrimination":
        sp = M.spearman(pred, obs)
        a = M.auc(pred, obs > 0)
        # Fixed severity bands (0–25 / 25–50 / 50–75 / 75–100) — the product's own risk buckets, so
        # "do observed events rise with the score band?" is measured on meaningful, stable edges rather
        # than data-dependent quantiles (which go non-monotone on noise even at strong rank skill).
        bands: list = []
        if n >= 8:
            for lo, hi in ((0, 25), (25, 50), (50, 75), (75, 100.01)):
                mask = (pred >= lo) & (pred < hi)
                bands.append(_round(float(obs[mask].mean())) if mask.any() else None)
        mono = M.monotonic_nondecreasing(bands) if bands else None
        metrics = {"spearman": sp, "auc": a, "band_mean_observed": bands, "monotonic": mono}
        grade = M.grade_discrimination(sp, mono)
        passed = M.passes_discrimination_gate(sp, mono)
        gate = "discrimination_spearman>=0.35+monotone"
    else:
        raise ValueError(f"unknown validation kind '{res.kind}'")
    metrics = {k: _round(v) for k, v in metrics.items()}
    metrics["n"] = n
    return metrics, grade, passed, gate


def run_validation(session: Session, key: str, *, actor: Optional[str] = None,
                   persist_samples: bool = False) -> dict:
    """Run one registered validator, record the immutable result, and return its summary."""
    if key not in REGISTRY:
        raise KeyError(f"no validator registered under '{key}' (have: {sorted(REGISTRY)})")
    res = REGISTRY[key](session)
    metrics, grade, passed, gate = _compute(res)
    run_id = session.execute(text("""
        INSERT INTO validation_run (run_id, model_id, hazard_type, scope, horizon, kind, method,
            target_source, n_samples, metrics, skill_grade, passed_gate, gate, notes, code_version,
            data_vintage, created_by, created_at)
        VALUES (gen_random_uuid(), CAST(:mid AS uuid), :hz, :scope, :horz, :kind, :method, :src, :n,
            CAST(:metrics AS jsonb), :grade, :passed, :gate, :notes, :cv, :dv, :by, now())
        RETURNING run_id::text
    """), {"mid": res.model_id, "hz": res.hazard_type, "scope": res.scope, "horz": res.horizon,
           "kind": res.kind, "method": res.method, "src": res.target_source, "n": metrics["n"],
           "metrics": json.dumps(metrics), "grade": grade.value, "passed": passed, "gate": gate,
           "notes": res.notes, "cv": VALIDATION_VERSION, "dv": res.data_vintage, "by": actor}).scalar()

    if persist_samples and res.labels:
        rows = [{"r": run_id, "l": str(lab), "p": float(p), "o": float(o)}
                for lab, p, o in zip(res.labels, res.predicted, res.observed)]
        for i in range(0, len(rows), 2000):
            session.execute(text("""
                INSERT INTO validation_sample (sample_id, run_id, label, predicted, observed)
                VALUES (gen_random_uuid(), CAST(:r AS uuid), :l, :p, :o)
            """), rows[i:i + 2000])
    session.commit()
    return {"run_id": run_id, "hazard": res.hazard_type, "kind": res.kind, "scope": res.scope,
            "method": res.method, "target_source": res.target_source, "grade": grade.value,
            "passed_gate": passed, "gate": gate, "metrics": metrics, "n": metrics["n"]}


def list_runs(session: Session, hazard: Optional[str] = None, limit: int = 50) -> list[dict]:
    rows = session.execute(text(f"""
        SELECT run_id::text, model_id::text, hazard_type, scope, horizon, kind, method, target_source,
               n_samples, metrics, skill_grade, passed_gate, gate, code_version, data_vintage, created_at
        FROM validation_run {"WHERE hazard_type = :h" if hazard else ""}
        ORDER BY created_at DESC LIMIT :lim
    """), ({"h": hazard, "lim": limit} if hazard else {"lim": limit})).mappings().all()
    return [dict(r) for r in rows]


def latest_skill_for_model(session: Session, model_id: str) -> Optional[dict]:
    """The most recent validation run for a registered model — the number governance/gating should read."""
    row = session.execute(text("""
        SELECT metrics, skill_grade, passed_gate, kind, created_at FROM validation_run
        WHERE model_id = CAST(:m AS uuid) ORDER BY created_at DESC LIMIT 1
    """), {"m": model_id}).mappings().first()
    return dict(row) if row else None
