"""The CALIBRATED gate: a hazard may be tiered CALIBRATED only if it declares an INDEPENDENT-target validation.

This guards against the circularity leak found in the 2026-09-05 audit — seismic and cyclone were tiered
CALIBRATED off IN-SAMPLE near-field consistency (score built from the same catalogue it was tested against).
The rule: every CALIBRATED hazard must appear in core.hazard_taxonomy.CALIBRATED_VALIDATION naming the
independent observed target it was validated against, and nothing else may. A channel cannot be promoted to
CALIBRATED without consciously declaring how it earned it.
"""
from core.hazard_taxonomy import CALIBRATED_VALIDATION, EU_TAXONOMY, EXTRA_CHANNELS, MaturityTier

_ALL = list(EU_TAXONOMY) + list(EXTRA_CHANNELS)


def test_every_calibrated_hazard_declares_an_independent_validation():
    calibrated = {h.id for h in _ALL if h.tier == MaturityTier.CALIBRATED}
    missing = calibrated - set(CALIBRATED_VALIDATION)
    assert not missing, (
        f"CALIBRATED without a declared independent-target validation: {sorted(missing)}. "
        "Add it to CALIBRATED_VALIDATION (with its independent target + backtest) or drop the tier."
    )


def test_no_stale_validation_entries():
    calibrated = {h.id for h in _ALL if h.tier == MaturityTier.CALIBRATED}
    stale = set(CALIBRATED_VALIDATION) - calibrated
    assert not stale, f"CALIBRATED_VALIDATION lists non-calibrated hazards: {sorted(stale)}"


def test_each_validation_names_an_independent_target():
    for hz, v in CALIBRATED_VALIDATION.items():
        assert v.get("target"), f"{hz}: validation must name its independent observed target"
        assert v.get("script"), f"{hz}: validation must reference its backtest script"
        assert "out_of_sample" in v, f"{hz}: validation must state out_of_sample true/false"


def test_known_in_sample_channels_are_not_calibrated():
    # seismic + cyclone are built from the catalogue they are checked against — never CALIBRATED on that basis.
    tier = {h.id: h.tier for h in _ALL}
    for hz in ("seismic", "cyclone"):
        assert tier.get(hz) != MaturityTier.CALIBRATED, f"{hz} is in-sample only — must not be CALIBRATED"
