"""Ground-Truth Fidelity presentation — must map faithfully to the real validation numbers."""
from __future__ import annotations

from ml.validation.fidelity import fidelity


def test_ground_truth_bands():
    # cocoa R²=0.60 → Φ 60 → Reliable; Morocco 0.67 → 67 Reliable; strong at 0.80+
    assert fidelity("regression", r2_oos=0.60)["value"] == 60.0
    assert fidelity("regression", r2_oos=0.60)["band"] == "reliable"
    assert fidelity("regression", r2_oos=0.67)["band"] == "reliable"
    assert fidelity("regression", r2_oos=0.85)["band"] == "strong"
    # fair band (published as directional)
    assert fidelity("regression", r2_oos=0.45)["band"] == "directional"


def test_ground_truth_floor_and_negative():
    # exactly at the 0.40 gate → floor 40 → directional (published)
    at_gate = fidelity("regression", r2_oos=0.40)
    assert at_gate["value"] == 40.0 and at_gate["band"] == "directional" and at_gate["published"]
    # below the gate → Held, withheld
    below = fidelity("regression", r2_oos=0.30)
    assert below["band"] == "held" and not below["published"]
    # negative R² (US maize -0.06) → clamped to 0 → Held
    neg = fidelity("regression", r2_oos=-0.06)
    assert neg["value"] == 0.0 and neg["band"] == "held" and not neg["published"]


def test_ranking_family():
    # seismic ρ=0.81, AUC 0.96 → RF 81 → Strong
    seis = fidelity("discrimination", spearman=0.81, auc=0.96)
    assert seis["family"] == "ranking" and seis["value"] == 81.0 and seis["band"] == "strong"
    assert seis["auc"] == 0.96
    # storm ρ=0.47 → Directional (35–49); floor 35
    storm = fidelity("rank", spearman=0.47)
    assert storm["band"] == "directional" and storm["floor"] == 35.0 and storm["published"]
    # ρ below its 0.35 gate → Held
    assert fidelity("discrimination", spearman=0.30)["band"] == "held"


def test_not_testable():
    nt = fidelity("regression", r2_oos=None)
    assert nt["value"] is None and nt["band"] == "not_testable" and not nt["published"]


def test_carries_context():
    f = fidelity("regression", r2_oos=0.60)
    assert f["family_label"] == "Ground-Truth Fidelity" and f["symbol"] == "Φ"
    assert "Nash" in f["basis"]
