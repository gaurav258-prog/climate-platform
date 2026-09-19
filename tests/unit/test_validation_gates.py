"""The pre-registered gates must be exactly what the code enforces — no drift, no docs that overstate the gate."""
import numpy as np

from core import validation_gates as G
from ml.validation import metrics as M
from services.validation.engine import ValidationResult, _compute


def test_spec_hash_is_stable_and_sensitive(monkeypatch):
    base = G.spec_sha()
    assert base == G.spec_sha() and len(base) == 64
    monkeypatch.setattr(G, "RANK_GATE_SPEARMAN", 0.30)
    assert G.spec_sha() != base          # loosening any threshold is a visible, hash-changing event


def test_metrics_enforce_exactly_the_declared_gates():
    assert M.RANK_GATE_SPEARMAN == G.RANK_GATE_SPEARMAN == 0.35
    assert M.REGRESSION_GATE_R2 == G.REGRESSION_GATE_R2 == 0.40
    assert M.MIN_N == G.MIN_N_METRIC and M.REGRESSION_MIN_N == G.MIN_N_REGRESSION_CLAIM
    assert M.passes_discrimination_gate(0.35, None) and not M.passes_discrimination_gate(0.3499, True)
    assert M.passes_regression_gate(0.40) and not M.passes_regression_gate(0.3999)


def test_monotone_bands_are_reported_not_gated():
    """The spec says monotonicity is not a hard gate; prove the code agrees, so no doc/label can claim otherwise."""
    assert G.MONOTONE_BANDS_REQUIRED is False
    assert M.passes_discrimination_gate(0.90, False) is True


def test_ledger_gate_label_is_truthful():
    rng = np.random.default_rng(0)
    pred = rng.uniform(0, 100, 60)
    obs = pred + rng.normal(0, 10, 60)
    for kind in ("rank", "discrimination"):
        res = ValidationResult(hazard_type="x", kind=kind, predicted=list(pred), observed=list(obs if kind == "rank" else (obs > 50).astype(float)),
                               target_source="synthetic")
        gate = _compute(res)[3]
        assert f">={G.RANK_GATE_SPEARMAN}" in gate and "monotone reported" in gate and "+monotone" not in gate
        assert len(gate) <= 60           # validation_run.gate is varchar(60)


def test_global_rule_requires_more_than_the_global_north():
    assert G.GLOBAL_CLAIM_MIN_REGIONS >= 4
    assert set(G.GLOBAL_CLAIM_MUST_INCLUDE_ONE_OF) <= set(G.MACRO_REGIONS)
    assert not ({"europe", "north_america"} & set(G.GLOBAL_CLAIM_MUST_INCLUDE_ONE_OF))


class _StubSession:
    """Captures the ledger INSERT without a database (the real ledger is append-only — no test rows in it)."""
    def __init__(self):
        self.params = None

    def execute(self, stmt, params=None):
        self.params = params

        class _R:
            def scalar(self_inner):
                return "run-123"
        return _R()

    def commit(self):
        pass


def _rank_result(strata=None):
    rng = np.random.default_rng(3)
    pred = rng.uniform(0, 100, 80)
    return ValidationResult(hazard_type="x", kind="rank", predicted=list(pred), observed=list(pred + rng.normal(0, 8, 80)),
                            target_source="synthetic", strata=strata)


def test_every_ledger_row_carries_the_gate_spec():
    import json
    from services.validation.engine import record_result
    s = _StubSession()
    record_result(s, _rank_result())
    m = json.loads(s.params["metrics"])
    assert m["gate_spec"] == G.GATE_SPEC_VERSION and m["gate_spec_sha"] == G.spec_sha()[:16]
    assert "stratified" not in m            # only present when a validator supplies strata


def test_strata_are_recorded_per_region_on_the_ledger_row():
    import json
    from services.validation.engine import record_result
    s = _StubSession()
    record_result(s, _rank_result(strata=["europe"] * 50 + ["asia"] * 30))
    m = json.loads(s.params["metrics"])
    assert set(m["stratified"]["by_stratum"]) == {"europe", "asia"}
    assert m["stratified"]["by_stratum"]["europe"]["status"] == "validated"


def test_misaligned_strata_are_rejected():
    import pytest
    from services.validation.engine import record_result
    with pytest.raises(ValueError):
        record_result(_StubSession(), _rank_result(strata=["europe"] * 10))


# ── always-on band-monotone check (policy: computed for every result; not gated / graded / reported) ─────────────
def test_band_monotone_fixed_scale_rising_and_falling():
    p = np.linspace(0, 99, 80)
    up = M.band_monotone(p, p * 0.5)
    assert up["method"] == "fixed_0_100" and up["monotone"] is True and sum(up["band_n"]) == 80
    down = M.band_monotone(p, -p)
    assert down["monotone"] is False


def test_band_monotone_falls_back_to_quartiles_off_the_0_100_scale():
    spei_like = np.linspace(-3, 3, 40)          # e.g. a drought index: not a 0-100 score
    r = M.band_monotone(spei_like, spei_like * 2 + 1)
    assert r["method"] == "quartile" and r["monotone"] is True and r["n_bands"] == 4


def test_band_monotone_falls_back_when_the_score_is_bunched():
    r = M.band_monotone(np.linspace(10, 30, 40), np.linspace(0, 1, 40))    # on scale, but only 1-2 fixed buckets populated
    assert r["method"] == "quartile" and r["n_bands"] >= 3


def test_band_monotone_is_none_never_a_guess():
    assert M.band_monotone([1, 2, 3], [1, 2, 3]) == {"method": None, "band_mean_observed": [], "band_n": [], "n_bands": 0,
                                                    "monotone": None, "reason": f"n<{G.MIN_N_BANDS}"}
    flat = M.band_monotone(np.full(20, 50.0), np.arange(20.0))
    assert flat["monotone"] is None and "two populated bands" in flat["reason"]
    assert M.band_monotone([np.nan] * 3 + list(range(10)), [1] * 3 + list(range(10)))["band_n"] is not None   # NaN pairs dropped


def test_new_key_fills_the_blank_without_changing_the_old_key_or_grade():
    """Predictions off the 0-100 scale: the legacy `monotonic` stays None (unchanged behaviour), grade unchanged, and
    the always-on check now carries a value."""
    x = np.linspace(-3, 3, 40)
    res = ValidationResult(hazard_type="x", kind="rank", predicted=list(x), observed=list(x * 2), target_source="synthetic")
    metrics, grade, passed, gate = _compute(res)
    assert metrics["monotonic"] is None                                                   # legacy fixed-band result: unchanged
    assert sum(b is not None for b in metrics["band_mean_observed"]) == 1                 # only the 0-25 bucket catches any data
    assert metrics["monotone_check"]["monotone"] is True and metrics["monotone_check"]["method"] == "quartile"
    assert passed is True                                                                 # gate untouched
    reg = _compute(ValidationResult(hazard_type="x", kind="regression", predicted=list(x), observed=list(x), target_source="s"))[0]
    assert "monotone_check" not in reg                                                    # only rank/discrimination results


def test_monotone_policy_is_pre_registered(monkeypatch):
    s = G.spec()
    assert s["monotone_policy"] == "compute_always__not_gated__not_reported" and s["monotone_bands_required"] is False
    assert len(s["monotone_reporting_conditions"]) == 3
    base = G.spec_sha()
    monkeypatch.setattr(G, "MONOTONE_POLICY", "report")
    assert G.spec_sha() != base                # switching the policy on is a hash-changing, reviewable event


def test_per_region_monotone_is_recorded():
    from ml.validation import regional as R
    x = np.linspace(0, 99, 60)
    rep = R.stratified_report(x, x, ["europe"] * 40 + ["asia"] * 20)
    assert rep["by_stratum"]["europe"]["monotone"] is True and rep["by_stratum"]["europe"]["monotone_method"]
