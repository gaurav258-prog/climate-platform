"""Cold wave is a building scale with physical anchors; severe convective is anchored to observed damaging-event
frequency; the insurer intake carries the same canonical ids as the bank's."""
import json

from ml.scoring.cold_wave_point import DESIGN_DEFICIT_ONSET_C, FREEZE_ONSET_C, cold_wave_score
from ml.scoring.severe_convective_point import damage_anchored_score


def test_cold_wave_anchors_are_physical_and_monotone():
    mild = [2.0 + 0.1 * i for i in range(30)]                 # Lisbon-like: never near freezing
    assert cold_wave_score(mild, 4.0)[0] == 0.0
    temperate = sorted([-19.0 + 0.4 * i for i in range(30)])  # Frankfurt-like: 1-in-10 night ≈ −18 °C
    sc, d = cold_wave_score(temperate, -12.5)
    assert 25 < sc < 50 and d["coldest_night_1in10_c"] < FREEZE_ONSET_C and d["design_deficit_c"] > DESIGN_DEFICIT_ONSET_C
    nordic = sorted([-30.0 + 0.5 * i for i in range(30)])     # designed for cold: big absolute term, small design exceedance
    sc2, d2 = cold_wave_score(nordic, -25.0)
    assert sc2 > sc and d2["design_exceedance"] < 0.2
    assert cold_wave_score(temperate, -12.5, warming_c=3.0)[0] < sc     # warming lowers the score, never raises it


def test_convective_score_is_the_anchored_annual_probability():
    a = json.load(open("data/convective/convective_anchor.json"))
    assert a["held_out"]["auc_event_most_years"] >= 0.75 and a["held_out"]["spearman_fitted"] >= 0.45
    scores = [damage_anchored_score(p) for p in (0, 20, 40, 60, 80, 100)]
    assert scores == sorted(scores) and scores[0] == 0.0 and scores[-1] <= 100.0
    assert abs(damage_anchored_score(60) - 100 * a["mapping"]["annual_probability"][30]) < 1e-6


def test_insurer_intake_uses_the_canonical_ids():
    d = json.load(open("data/reference/supervision_profiles.json"))
    bank, ins = d["sectors"]["bank"]["intake"], d["sectors"]["insurer"]["intake"]
    assert {f["id"] for f in ins["submission"]["cell_fields"]} == {f["id"] for f in bank["submission"]["cell_fields"]}
    assert {f["id"] for f in ins["granular"]["row_fields"]} == {f["id"] for f in bank["granular"]["row_fields"]}
    assert ins["submission"]["framework"] == "insurer_climate" and "Sum insured" in ins["submission"]["cell_fields"][2]["label"]
