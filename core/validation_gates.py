"""Pre-registered validation gates — declared once, before any backtest is run, and stamped on every ledger row.

A gate that can be nudged after seeing a result is not a gate. Every threshold the validation engine enforces
lives HERE and nowhere else (`ml/validation/metrics.py` imports them), the spec carries a version and a content
hash, and the engine writes both onto every `validation_run`, so an auditor can prove which rules a result was
judged under. Changing any number below changes the hash — a visible, reviewable event.

What is and is NOT enforced (kept exactly true to the code, and asserted by tests/unit/test_validation_gates.py):
  • rank / discrimination gate: Spearman ρ ≥ RANK_GATE_SPEARMAN. Band monotonicity is REPORTED and lifts the grade
    to 'strong', but it is not a hard gate (MONOTONE_BANDS_REQUIRED = False): coarse bands are noisy on few events.
  • regression gate: out-of-sample R² ≥ REGRESSION_GATE_R2.

Global scope rules (regional claims): a single pooled number can hide a failing region, so a claim is judged
per macro-region, and 'global' is only claimed under the rule below — see core/hazard_regions.py.
"""
from __future__ import annotations

import hashlib
import json

GATE_SPEC_VERSION = "gates-v1"

# ── metric floors ──────────────────────────────────────────────────────────────────────────────────────
MIN_N_METRIC = 3                 # below this no metric is honest
MIN_N_REGRESSION_CLAIM = 5       # a continuous skill CLAIM needs more than the bare metric floor
REGRESSION_GATE_R2 = 0.40        # publish gate for a continuous model
RANK_GATE_SPEARMAN = 0.35        # publish gate for a score-vs-observed model
STRONG_SPEARMAN = 0.65           # grade 'strong' needs this AND monotone bands
MONOTONE_BANDS_REQUIRED = False  # reported + grade-lifting, NOT a hard gate (see module docstring)
MIN_N_BANDS = 8                  # below this no band check is honest
MONOTONE_FIXED_MIN_POPULATED = 3 # fixed 0-100 buckets are used only if >= this many are populated, else quartiles

# Monotone-band POLICY (pre-registered so it cannot be decided after seeing results): the band check is COMPUTED FOR
# EVERY RESULT and stored under metrics['monotone_check'] (per region too), but it is not a gate, not a grade input for
# that new key and not a headline until ALL conditions below hold and the policy is adopted as a new spec version.
MONOTONE_POLICY = "compute_always__not_gated__not_reported"
MONOTONE_REPORTING_CONDITIONS = (
    "per-region sample floor (MIN_N_REGION_CLAIM) met in >= GLOBAL_CLAIM_MIN_REGIONS macro-regions for the hazard",
    "any calc-model rework was evaluated on a held-out set frozen before the rework",
    "adopted as a new gate-spec version (new spec hash), never edited in place",
)

# ── regional / global scope ────────────────────────────────────────────────────────────────────────────
MACRO_REGIONS = ("europe", "north_america", "latin_america_caribbean", "africa", "asia", "oceania")
MIN_N_REGION_CLAIM = 20          # a per-region claim needs at least this many samples in that region
REGION_PASS_SPEARMAN = RANK_GATE_SPEARMAN
GLOBAL_CLAIM_MIN_REGIONS = 4     # 'global' = validated (status 'validated', not 'mixed') in >= this many macro-regions
GLOBAL_CLAIM_MUST_INCLUDE_ONE_OF = ("latin_america_caribbean", "africa", "asia")   # never a global claim from the Global North alone


def spec() -> dict:
    """The full pre-registered specification, as a plain dict (the thing that is hashed)."""
    return {
        "version": GATE_SPEC_VERSION,
        "min_n_metric": MIN_N_METRIC,
        "min_n_regression_claim": MIN_N_REGRESSION_CLAIM,
        "regression_gate_r2": REGRESSION_GATE_R2,
        "rank_gate_spearman": RANK_GATE_SPEARMAN,
        "strong_spearman": STRONG_SPEARMAN,
        "monotone_bands_required": MONOTONE_BANDS_REQUIRED,
        "min_n_bands": MIN_N_BANDS,
        "monotone_fixed_min_populated": MONOTONE_FIXED_MIN_POPULATED,
        "monotone_policy": MONOTONE_POLICY,
        "monotone_reporting_conditions": list(MONOTONE_REPORTING_CONDITIONS),
        "macro_regions": list(MACRO_REGIONS),
        "min_n_region_claim": MIN_N_REGION_CLAIM,
        "region_pass_spearman": REGION_PASS_SPEARMAN,
        "global_claim_min_regions": GLOBAL_CLAIM_MIN_REGIONS,
        "global_claim_must_include_one_of": list(GLOBAL_CLAIM_MUST_INCLUDE_ONE_OF),
    }


def spec_sha() -> str:
    """Content hash of the spec — any change to any threshold changes this."""
    return hashlib.sha256(json.dumps(spec(), sort_keys=True).encode()).hexdigest()
