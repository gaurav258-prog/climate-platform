"""The model-governance publish gate — the honesty standard enforced as a promotion control.

Pure-function tests (no DB): a scoring model version can only be approved/activated when its out-of-sample
calibration r² clears the same 0.40 gate the product publishes on.
"""
from services.mlops.model_governance import PUBLISH_GATE_R2, meets_publish_gate


def test_gate_threshold_is_the_publish_standard():
    assert PUBLISH_GATE_R2 == 0.40


def test_gate_passes_at_or_above_040():
    assert meets_publish_gate(0.40) is True
    assert meets_publish_gate(0.61) is True
    assert meets_publish_gate(1.0) is True


def test_gate_fails_below_040_or_missing():
    assert meets_publish_gate(0.39) is False
    assert meets_publish_gate(0.0) is False
    assert meets_publish_gate(None) is False   # an uncalibrated model never clears the gate
