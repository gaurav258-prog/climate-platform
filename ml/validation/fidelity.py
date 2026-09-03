"""Ground-Truth Fidelity — Tellumen's name and presentation for the validation fit.

This is NOT a new statistic. It is a faithful presentation layer over the numbers ml/validation/metrics.py
already computes, so a reader sees "how faithfully our score matches independently-observed reality" instead
of a bare "R² = 0.60" (which a critic wrongly assumes is the flattering in-sample kind — ours is the strict
out-of-sample / Nash–Sutcliffe form). Two families, one shared band vocabulary:

  • GROUND-TRUTH FIDELITY (Φ)  — continuous outcomes. Φ = out-of-sample R² × 100 (clamped 0–100 for display;
    a negative R² shows as 0 / Held). Publish floor 40 (the R² ≥ 0.40 gate). Confidence steps 60, 80.
  • RANKING FIDELITY           — event/occurrence outcomes, where R² is not meaningful. = Spearman ρ × 100.
    Publish floor 35 (the ρ ≥ 0.35 gate). Confidence steps 50, 65 (matches grade_discrimination's 0.65).

Same band WORDS across both; the numeric cut-offs differ because the two tests have different gates — that is
honest, and disclosed. The floor of each family is exactly its publish gate: below it, nothing is published.
A glossary line travels with the metric: "Φ = out-of-sample R² (Nash–Sutcliffe); Ranking Fidelity = ρ×100".
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class FidelityBand(str, Enum):
    NOT_TESTABLE = "not_testable"   # the test physically can't judge (insufficient / no variance)
    HELD = "held"                   # below the publish floor — withheld, no number shown
    DIRECTIONAL = "directional"     # cleared the floor — published as a band
    RELIABLE = "reliable"           # published as firm figures
    STRONG = "strong"               # high confidence


class FidelityFamily(str, Enum):
    GROUND_TRUTH = "ground_truth"   # variance explained (regression)
    RANKING = "ranking"             # rank agreement (discrimination / rank)


BAND_LABEL: dict[FidelityBand, str] = {
    FidelityBand.NOT_TESTABLE: "Not testable",
    FidelityBand.HELD: "Held",
    FidelityBand.DIRECTIONAL: "Directional",
    FidelityBand.RELIABLE: "Reliable",
    FidelityBand.STRONG: "Strong",
}

FAMILY_LABEL: dict[FidelityFamily, str] = {
    FidelityFamily.GROUND_TRUTH: "Ground-Truth Fidelity",
    FidelityFamily.RANKING: "Ranking Fidelity",
}

# per-family band cut-offs on the 0–100 scale: (floor = publish gate, reliable step, strong step)
_CUTOFFS: dict[FidelityFamily, tuple[float, float, float]] = {
    FidelityFamily.GROUND_TRUTH: (40.0, 60.0, 80.0),   # R² gate 0.40; strong 0.60
    FidelityFamily.RANKING: (35.0, 50.0, 65.0),        # ρ gate 0.35; strong 0.65
}


def _band(value: Optional[float], cutoffs: tuple[float, float, float]) -> FidelityBand:
    floor, mid, hi = cutoffs
    if value is None:
        return FidelityBand.NOT_TESTABLE
    if value < floor:
        return FidelityBand.HELD
    if value < mid:
        return FidelityBand.DIRECTIONAL
    if value < hi:
        return FidelityBand.RELIABLE
    return FidelityBand.STRONG


def fidelity(kind: str, r2_oos: Optional[float] = None, spearman: Optional[float] = None,
             auc: Optional[float] = None) -> dict:
    """Map a validation result to its Fidelity presentation.

    kind: 'regression' → Ground-Truth Fidelity from r2_oos; 'discrimination'/'rank' → Ranking Fidelity from
    spearman (auc carried for context). Returns a self-describing dict the API/UI render directly.
    """
    if kind == "regression":
        family = FidelityFamily.GROUND_TRUTH
        raw = r2_oos
    else:
        family = FidelityFamily.RANKING
        raw = spearman
    cutoffs = _CUTOFFS[family]
    value = None if raw is None else round(max(0.0, min(100.0, raw * 100.0)), 1)
    band = _band(value, cutoffs)
    published = band in (FidelityBand.DIRECTIONAL, FidelityBand.RELIABLE, FidelityBand.STRONG)
    return {
        "family": family.value,
        "family_label": FAMILY_LABEL[family],
        "symbol": "Φ" if family is FidelityFamily.GROUND_TRUTH else "RF",
        "value": value,                       # 0–100, or None when not testable
        "band": band.value,
        "band_label": BAND_LABEL[band],
        "published": published,               # did it clear the publish floor?
        "floor": cutoffs[0],                  # the publish gate, on the 0–100 scale
        "basis": ("out-of-sample R² (Nash–Sutcliffe) × 100" if family is FidelityFamily.GROUND_TRUTH
                  else "Spearman rank correlation × 100"),
        # raw statistics carried through, so nothing is hidden
        "r2_oos": r2_oos,
        "spearman": spearman,
        "auc": auc,
    }
