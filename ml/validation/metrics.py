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

MIN_N = 3                      # below this, no metric is honest
REGRESSION_GATE_R2 = 0.40     # the publish gate (matches the product's honesty standard)


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
    if sp is None:
        return Grade.INSUFFICIENT
    if sp >= 0.65 and monotonic:
        return Grade.STRONG
    if sp >= 0.35 and (monotonic is None or monotonic):
        return Grade.FAIR
    return Grade.WEAK


def passes_regression_gate(r2: Optional[float]) -> bool:
    """The publish gate for a continuous model: R² ≥ 0.40."""
    return r2 is not None and r2 >= REGRESSION_GATE_R2


def passes_discrimination_gate(sp: Optional[float], monotonic: Optional[bool]) -> bool:
    """The publish gate for a score-vs-event model: rank skill ≥ 0.35 and bands rise with the score."""
    return sp is not None and sp >= 0.35 and bool(monotonic)
