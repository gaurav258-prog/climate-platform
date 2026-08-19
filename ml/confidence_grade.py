"""The Confidence Grade (A–E) — one transparent letter for how much to trust a crop's euro.

A credit-score-style summary that ADDS what a single r² misses — does it hold up out-of-sample,
is the published range honest, how deep is the evidence — and shows its work. It never replaces
the raw statistics; it aggregates them by a published rule so an auditor can reconstruct it.

FOUR CHECKS, each Strong (2) / Fair (1) / Weak (0):
  1. Predictive power   — does it hold up on years it did NOT learn from?
        ranged     : out-of-sample (leave-one-out) r²   ≥0.55 Strong · ≥0.35 Fair · else Weak
        backtested : how close it reproduced a real event   ≤5% Strong · ≤15% Fair · else Weak
  2. Evidence depth     — how much independent evidence?
        ranged     : usable years                        ≥25 Strong · ≥15 Fair · else Weak
        backtested : real events reproduced              ≥3 Strong · ≥1 Fair · else Weak
  3. Honest range       — does the band catch outcomes as often as it promises?
        ranged     : |68%-band actual coverage − 0.68|   ≤0.08 Strong · ≤0.15 Fair · else Weak
        backtested : a single event can't cross-check its own interval → Fair (caveat disclosed)
  4. Directness of proof
        backtested (reproduced a real, named failure) Strong · ranged (statistical) Fair · else Weak

GRADE = sum (0–8): A 7–8 · B 5–6 · C 3–4 · D 1–2 · E 0.
HONESTY CAP: if check 1 (predictive) is Weak, the grade cannot exceed C — no amount of history
or calibration makes an unpredictable euro trustworthy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

STRONG, FAIR, WEAK = 2, 1, 0
_LABEL = {STRONG: "strong", FAIR: "fair", WEAK: "weak"}


@dataclass
class GradeResult:
    grade: str                      # 'A'..'E'
    total: int                      # 0..8
    capped: bool                    # True if the honesty cap lowered the letter
    checks: list = field(default_factory=list)  # [{key, label, points, detail}]


def _band(value, strong, fair, higher_is_better=True) -> int:
    if higher_is_better:
        return STRONG if value >= strong else FAIR if value >= fair else WEAK
    return STRONG if value <= strong else FAIR if value <= fair else WEAK


def _letter(total: int) -> str:
    return "A" if total >= 7 else "B" if total >= 5 else "C" if total >= 3 else "D" if total >= 1 else "E"


def grade(*, tier: str,
          r2_oos: Optional[float] = None, n_years: Optional[int] = None,
          band_cov68: Optional[float] = None,
          reproduction_err_pct: Optional[float] = None, n_events: Optional[int] = None,
          corroboration: Optional[str] = None) -> GradeResult:
    """Compute the grade for one published crop. `tier` is 'backtested' or 'ranged'; the metrics
    used depend on it (see module docstring). Missing inputs score Weak, never silently pass.

    corroboration: the independent-challenger verdict ('agree'/'partial'/'diverge'/'insufficient')
    when a second method cross-checked the fit. It is surfaced as a check but NOT added to the /8
    total (so an existing grade is never silently upgraded by corroboration); a DIVERGENCE is a red
    flag that caps the letter at C, exactly like weak predictive power."""
    checks = []

    if tier == "backtested":
        c1 = _band(reproduction_err_pct if reproduction_err_pct is not None else 999, 5, 15,
                   higher_is_better=False)
        checks.append({"key": "predictive", "points": c1,
                       "detail": (f"reproduced a real event within {reproduction_err_pct:.1f}%"
                                  if reproduction_err_pct is not None else "no reproduction figure")})
        c2 = _band(n_events or 0, 3, 1)
        checks.append({"key": "evidence_depth", "points": c2,
                       "detail": f"{n_events or 0} real event(s) reproduced"})
        # a single event cannot cross-check its own uncertainty; the caveat is disclosed → Fair
        c3 = FAIR if (n_events or 0) < 3 else STRONG
        checks.append({"key": "honest_range", "points": c3,
                       "detail": "single-event uncertainty disclosed" if c3 == FAIR
                                 else "multiple events cross-check the interval"})
        c4 = STRONG
        checks.append({"key": "directness", "points": c4, "detail": "reproduced a real, named failure"})
    else:  # ranged (or anything published statistically)
        c1 = _band(r2_oos if r2_oos is not None else -1, 0.55, 0.35)
        checks.append({"key": "predictive", "points": c1,
                       "detail": (f"explains {round((r2_oos or 0)*100)}% out-of-sample"
                                  if r2_oos is not None else "no out-of-sample figure")})
        c2 = _band(n_years or 0, 25, 15)
        checks.append({"key": "evidence_depth", "points": c2, "detail": f"{n_years or 0} usable years"})
        c3 = (_band(abs((band_cov68 or 0) - 0.68), 0.08, 0.15, higher_is_better=False)
              if band_cov68 is not None else WEAK)
        checks.append({"key": "honest_range", "points": c3,
                       "detail": (f"68% band catches {round((band_cov68 or 0)*100)}% of outcomes"
                                  if band_cov68 is not None else "band coverage not measured")})
        c4 = FAIR
        checks.append({"key": "directness", "points": c4, "detail": "multi-year statistical fit"})

    for c in checks:
        c["label"] = _LABEL[c["points"]]

    total = sum(c["points"] for c in checks)  # the earned score is the 4 evidence checks (0–8)
    letter = _letter(total)
    # honesty cap: weak predictive power → cannot exceed C
    capped = False
    predictive_weak = checks[0]["points"] == WEAK
    if predictive_weak and letter in ("A", "B"):
        letter, capped = "C", True

    # Independent-challenger corroboration — surfaced (not additive), and a divergence caps at C.
    if corroboration:
        pts = {"agree": STRONG, "partial": FAIR}.get(corroboration, WEAK)
        detail = {
            "agree": "an independent method (isotonic) corroborates the fit",
            "partial": "an independent method partly corroborates the fit",
            "diverge": "an independent method DISAGREES with the fit — treat with caution",
            "insufficient": "independent cross-check inconclusive (too few years)",
        }.get(corroboration, str(corroboration))
        checks.append({"key": "corroboration", "points": pts, "label": _LABEL.get(pts, "weak"),
                       "detail": detail, "additive": False})
        if corroboration == "diverge" and letter in ("A", "B"):
            letter, capped = "C", True
    return GradeResult(grade=letter, total=total, capped=capped, checks=checks)
