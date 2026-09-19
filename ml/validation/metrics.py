"""Validation metrics — the accuracy core of the backtesting framework.

Pure, deterministic, DB-free functions so they can be unit-tested exhaustively against known answers. Two
families, because two kinds of model output are validated differently and it would be dishonest to force one
metric on both:

  • REGRESSION  — a continuous prediction vs a continuous observed value (e.g. €-at-risk, crop shock).
                  Skill = out-of-sample R² against the observed mean. The publish gate is R² ≥ 0.40.
  • DISCRIMINATION — a score vs an observed event (count or occurrence), e.g. hazard score vs near-field
                  catalogue events. Skill = rank correlation (Spearman) + AUC + band monotonicity. R² is not
                  meaningful here, so it is not computed.

Every function returns None (never a fabricated number) when the sample is too small or has no variance —
"Insufficient", not a false pass. The rank/Spearman/AUC implementations match services/intelligence/
model_validation.py exactly (single source of truth for the numerics).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

import numpy as np

from core.validation_gates import (   # the pre-registered gates — one source of truth (core/validation_gates.py)
    MIN_N_BANDS,
    MIN_N_METRIC as MIN_N,
    MONOTONE_FIXED_MIN_POPULATED,
    MIN_N_REGRESSION_CLAIM as REGRESSION_MIN_N,
    RANK_GATE_SPEARMAN,
    REGRESSION_GATE_R2,
    STRONG_SPEARMAN,
)


class Grade(str, Enum):
    STRONG = "strong"
    FAIR = "fair"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


# ── rank / discrimination (identical to model_validation.py) ─────────────────────────────────────
def rank(x: np.ndarray) -> np.ndarray:
    """Average-tied ranks (1..n)."""
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=float)
    ranks[order] = np.arange(1, len(x) + 1)
    xs = x[order]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks


def spearman(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < MIN_N or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    ra, rb = rank(a), rank(b)
    return float(np.corrcoef(ra, rb)[0, 1])


def auc(scores: np.ndarray, positive: np.ndarray) -> Optional[float]:
    """Mann–Whitney AUC: P(score of a positive > score of a negative)."""
    scores = np.asarray(scores, float)
    pos = np.asarray(positive, bool)
    n_pos = int(pos.sum())
    n_neg = len(scores) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = rank(scores)
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


# ── regression ───────────────────────────────────────────────────────────────────────────────────
def r2_oos(pred: np.ndarray, obs: np.ndarray) -> Optional[float]:
    """Out-of-sample R² vs the observed mean: 1 − SS_res / SS_tot. None if <MIN_N or observed has no
    variance. Can go negative (worse than predicting the mean) — reported honestly, not clipped."""
    pred, obs = np.asarray(pred, float), np.asarray(obs, float)
    if len(pred) < MIN_N or len(pred) != len(obs):
        return None
    ss_tot = float(np.sum((obs - obs.mean()) ** 2))
    if ss_tot == 0:
        return None
    ss_res = float(np.sum((obs - pred) ** 2))
    return 1.0 - ss_res / ss_tot


def rmse(pred: np.ndarray, obs: np.ndarray) -> Optional[float]:
    pred, obs = np.asarray(pred, float), np.asarray(obs, float)
    if len(pred) == 0 or len(pred) != len(obs):
        return None
    return float(np.sqrt(np.mean((pred - obs) ** 2)))


def mae(pred: np.ndarray, obs: np.ndarray) -> Optional[float]:
    pred, obs = np.asarray(pred, float), np.asarray(obs, float)
    if len(pred) == 0 or len(pred) != len(obs):
        return None
    return float(np.mean(np.abs(pred - obs)))


def bias(pred: np.ndarray, obs: np.ndarray) -> Optional[float]:
    """Mean signed error (pred − obs): + = over-prediction."""
    pred, obs = np.asarray(pred, float), np.asarray(obs, float)
    if len(pred) == 0 or len(pred) != len(obs):
        return None
    return float(np.mean(pred - obs))


def brier(prob: np.ndarray, outcome: np.ndarray) -> Optional[float]:
    """Brier score for probabilistic forecasts (0 best, 1 worst). `prob` in [0,1], `outcome` in {0,1}."""
    prob, outcome = np.asarray(prob, float), np.asarray(outcome, float)
    if len(prob) == 0 or len(prob) != len(outcome):
        return None
    return float(np.mean((prob - outcome) ** 2))


def monotonic_nondecreasing(values: list) -> Optional[bool]:
    """Do the (band-ordered) values rise monotonically? None if <2 comparable values."""
    v = [x for x in values if x is not None]
    if len(v) < 2:
        return None
    return all(v[i] <= v[i + 1] for i in range(len(v) - 1))


FIXED_BANDS = ((0, 25), (25, 50), (50, 75), (75, 100.01))   # the product's own Low/Medium/High/Very-High buckets


def band_monotone(pred, obs) -> dict:
    """Do the observed outcomes rise with the score band? Computed for EVERY result (policy: core/validation_gates.py).

    Bands are the product's fixed 0–25/25–50/50–75/75–100 buckets when the score is on the 0–100 scale and at least
    MONOTONE_FIXED_MIN_POPULATED of them hold data; otherwise quartiles of the score (equal scores share a band), so a
    result whose predictions are not on that scale — or are bunched — still gets a value instead of a blank. The
    method used and the sample count per band are returned, because bands of a handful of samples are noisy and a
    reader must be able to see that. `monotone` is None (never a guess) when there are < MIN_N_BANDS samples or fewer
    than two populated bands. This does NOT feed the gate, the grade or any headline."""
    p = np.asarray(pred, float)
    o = np.asarray(obs, float)
    ok = np.isfinite(p) & np.isfinite(o)
    p, o = p[ok], o[ok]
    out: dict = {"method": None, "band_mean_observed": [], "band_n": [], "n_bands": 0, "monotone": None, "reason": None}
    if len(p) < MIN_N_BANDS:
        out["reason"] = f"n<{MIN_N_BANDS}"
        return out

    def _by(idx: np.ndarray, k: int) -> tuple[list, list]:
        means, ns = [], []
        for b in range(k):
            m = idx == b
            ns.append(int(m.sum()))
            means.append(round(float(o[m].mean()), 4) if m.any() else None)
        return means, ns

    method = None
    if p.min() >= 0 and p.max() <= 100:
        idx = np.digitize(p, [e[1] for e in FIXED_BANDS[:-1]])
        means, ns = _by(idx, 4)
        if sum(1 for x in ns if x) >= MONOTONE_FIXED_MIN_POPULATED:
            method = "fixed_0_100"
    if method is None:
        idx = np.digitize(p, np.quantile(p, [0.25, 0.5, 0.75]))
        means, ns = _by(idx, 4)
        method = "quartile"
    out.update({"method": method, "band_mean_observed": means, "band_n": ns,
                "n_bands": sum(1 for x in ns if x), "monotone": monotonic_nondecreasing(means)})
    if out["monotone"] is None:
        out["reason"] = "fewer than two populated bands"
    return out


# ── grading + gates ────────────────────────────────────────────────────────────────────────────
def grade_regression(r2: Optional[float]) -> Grade:
    if r2 is None:
        return Grade.INSUFFICIENT
    if r2 >= 0.60:
        return Grade.STRONG
    if r2 >= REGRESSION_GATE_R2:
        return Grade.FAIR
    return Grade.WEAK


def grade_discrimination(sp: Optional[float], monotonic: Optional[bool]) -> Grade:
    # Rank skill (Spearman) is the robust signal; band monotonicity only ELEVATES a strong rank to STRONG.
    # A strongly rank-correlated model whose coarse bands go noisy (few events) is FAIR, never WEAK.
    if sp is None:
        return Grade.INSUFFICIENT
    if sp >= STRONG_SPEARMAN and monotonic:
        return Grade.STRONG
    if sp >= RANK_GATE_SPEARMAN:
        return Grade.FAIR
    return Grade.WEAK


def passes_regression_gate(r2: Optional[float]) -> bool:
    """The publish gate for a continuous model: R² ≥ 0.40."""
    return r2 is not None and r2 >= REGRESSION_GATE_R2


def passes_discrimination_gate(sp: Optional[float], monotonic: Optional[bool]) -> bool:
    """The publish gate for a score-vs-event model: rank skill ≥ 0.35. Monotonicity is reported and lifts the
    GRADE to strong, but is not a hard gate — coarse-band monotonicity is noisy on few events and must not
    fail a genuinely rank-correlated model (the `monotonic` arg is kept for signature symmetry)."""
    return sp is not None and sp >= RANK_GATE_SPEARMAN


# ── applicability guard — is the test even CAPABLE of judging this model? ─────────────────────────
# The rule for "such cases": a weak number must first be diagnosed — model, or test? When the observed
# target is saturated (nearly everywhere has an event, e.g. a wide/frequent hazard tested by near-field
# counting) or has no variance, or the score has no spread, the test cannot discriminate. Such a run is
# NOT-TESTABLE (→ Insufficient), never "weak/fail" — so we never mislabel a sound model as bad.
SATURATION_HI = 0.85   # ≥85% of locations having an event → nothing left to discriminate
SATURATION_LO = 0.02   # ≤2% → too few events to discriminate


def event_prevalence(obs: np.ndarray) -> float:
    a = np.asarray(obs, float)
    return float(np.mean(a > 0)) if len(a) else 0.0


def discrimination_applicable(pred: np.ndarray, obs: np.ndarray) -> tuple[bool, str]:
    """Can a score-vs-EVENT (occurrence/count) test discriminate here?"""
    pred = np.asarray(pred, float)
    if len(pred) < MIN_N:
        return False, "too few samples"
    if np.ptp(pred) == 0:
        return False, "score has no spread"
    prev = event_prevalence(obs)
    if prev >= SATURATION_HI:
        return False, (f"target saturated — {prev:.0%} of locations have an event; near-field counting "
                       f"cannot discriminate a wide/frequent hazard (use a severity-based test instead)")
    if prev <= SATURATION_LO:
        return False, f"target too sparse — only {prev:.1%} of locations have an event to discriminate"
    return True, ""


def continuous_applicable(pred: np.ndarray, obs: np.ndarray) -> tuple[bool, str]:
    """Can a continuous test (regression, or rank vs a continuous observed quantity like intensity) run?"""
    pred, obs = np.asarray(pred, float), np.asarray(obs, float)
    if len(pred) != len(obs) or len(pred) < REGRESSION_MIN_N:
        return False, f"too few samples to claim skill (n={len(pred)}, need ≥{REGRESSION_MIN_N})"
    if np.ptp(pred) == 0:
        return False, "score has no spread"
    if np.var(obs) == 0:
        return False, "observed values have no variance"
    return True, ""
