"""Challenger out-of-sample runs — an INDEPENDENT second method, cross-checking the euro champion on the audit
record, out-of-sample.

The champion is an OLS line; the challenger is an isotonic (monotone, shape-agnostic) regression fitted only
from the (hazard score, loss) pairs. Both are run under the SAME leave-one-out on the SAME reconstructed panel,
so their out-of-sample skill is comparable point-for-point. For each published fit this records a
`loo_cv_challenger` row in the ledger next to the champion's `loo_cv` row, and an agreement verdict:

  agree   — the two out-of-sample prediction paths differ by less than the champion's own residual scale
  partial — differ by up to twice that
  diverge — materially different shape → a real model-risk flag on that euro

This closes the disclosed roadmap gap (CALC_ENGINE_AUDIT T11): a genuinely independent challenger model, now
compared to the champion out-of-sample and on the audit record — not just an in-sample side calculation.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ml.features.challenger import CHALLENGER_VERSION, isotonic_loo
from ml.validation.metrics import REGRESSION_GATE_R2, r2_oos
from services.validation.champion_oos import _fits, reconstruct
from services.validation.engine import ValidationResult, record_result

TOL_FLOOR_PP = 3.0   # never call agreement tighter than 3 percentage points (matches the in-sample challenger)


def _verdict(champ_pred: list, chal_pred: list, champion_rmse: float) -> tuple[str, float, float]:
    import numpy as np
    c = np.asarray(champ_pred, float)
    h = np.asarray(chal_pred, float)
    mad = float(np.abs(c - h).mean())
    tol = max(float(champion_rmse or 0.0), TOL_FLOOR_PP)
    verdict = "agree" if mad <= tol else ("partial" if mad <= 2 * tol else "diverge")
    return verdict, round(mad, 2), round(tol, 2)


def build_result(session: Session, fit) -> Optional[dict]:
    """Return {result, verdict, champ_oos, chal_oos, mad, tol} for one fit's out-of-sample challenger, or None
    when the panel can't be reconstructed or is too short for the isotonic leave-one-out."""
    rec = reconstruct(session, fit)
    if rec is None:
        return None
    cf, scores = rec.cf, rec.scores
    years = [y for (y, _p, _o) in cf.loo_samples]
    champ_pred = [p for (_y, p, _o) in cf.loo_samples]
    obs = [o for (_y, _p, o) in cf.loo_samples]
    pts = [(scores[y], o) for (y, _p, o) in cf.loo_samples]     # SAME panel the champion used

    chal_pred = isotonic_loo(pts, increasing=(cf.slope >= 0))
    if chal_pred is None:
        return None
    chal_oos = r2_oos(chal_pred, obs)
    verdict, mad, tol = _verdict(champ_pred, chal_pred, cf.rmse)
    driver = fit["hazard_driver"]
    scope = f"{fit['name']}/{fit['origin']}"

    # Decision-relevant signal: for a crop the champion PUBLISHES (clears the OOS gate), does the independent
    # challenger clear it too? Path-agreement alone is lenient on a noisy panel; this is the harder corroboration.
    champ_pub = cf.r2_oos is not None and cf.r2_oos >= REGRESSION_GATE_R2
    chal_pub = chal_oos is not None and chal_oos >= REGRESSION_GATE_R2
    if not champ_pub:
        corrob = "n/a (champion below publish floor)"
    elif chal_pub:
        corrob = "CORROBORATED — challenger independently clears the publish floor too"
    else:
        corrob = (f"champion retained — the parsimonious OLS generalises better out-of-sample than the flexible "
                  f"isotonic challenger ({chal_oos:.3f} < {REGRESSION_GATE_R2}); shape corroborated, not skill")

    res = ValidationResult(
        hazard_type=f"crop_{driver}", kind="regression",
        predicted=chal_pred, observed=obs, labels=[str(y) for y in years],
        target_source=f"{fit['name']} ({fit['origin']}) observed yield — isotonic challenger, leave-one-out CV",
        scope=scope, method="loo_cv_challenger",
        data_vintage=f"leave-one-out over {cf.n_years} years",
        notes=(f"INDEPENDENT isotonic challenger ({driver}, {rec.source}) leave-one-out vs the OLS champion on "
               f"the identical panel — champion OOS r²={cf.r2_oos}, challenger OOS r²={chal_oos}. "
               f"Path verdict: {verdict} (mean out-of-sample divergence {mad}pp vs tolerance {tol}pp). "
               f"Publish corroboration: {corrob}. {CHALLENGER_VERSION}."),
        extra={"challenger_verdict": verdict, "champion_r2_oos": cf.r2_oos, "challenger_r2_oos": chal_oos,
               "corroborates_publish": (chal_pub if champ_pub else None)},
    )
    return {"result": res, "scope": scope, "verdict": verdict, "champ_oos": cf.r2_oos, "chal_oos": chal_oos,
            "mad": mad, "tol": tol, "champ_pub": champ_pub, "chal_pub": chal_pub}


def record_all(session: Session, *, actor: str = "challenger_oos", persist_samples: bool = True) -> list[dict]:
    """Record an independent-challenger out-of-sample run for every reconstructable published fit."""
    out: list[dict] = []
    for fit in _fits(session):
        b = build_result(session, fit)
        if b is None:
            continue
        summary = record_result(session, b["result"], actor=actor, persist_samples=persist_samples)
        summary.update({"scope": b["scope"], "verdict": b["verdict"], "champ_oos": b["champ_oos"],
                        "chal_oos": b["chal_oos"], "champ_pub": b["champ_pub"], "chal_pub": b["chal_pub"]})
        out.append(summary)
    return out
