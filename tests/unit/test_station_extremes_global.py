from __future__ import annotations

from services.validation.validators.station_extremes_global import assemble, usable_score


def test_usable_score():
    assert usable_score({"status": "scored", "risk_score": 42.0}) == 42.0
    assert usable_score({"status": "cached_hit", "risk_score": "7"}) == 7.0
    assert usable_score({"status": "insufficient_data", "reason": "x"}) is None
    assert usable_score({"status": "scored", "risk_score": None}) is None
    assert usable_score({"status": "scored", "risk_score": float("nan")}) is None
    assert usable_score(None) is None


def test_assemble_drops_unscored_and_flips_sign():
    st = [{"station_id": "A", "name": "a", "region": "africa", "c": -5.0},
          {"station_id": "B", "name": "b", "region": "asia", "c": -10.0},
          {"station_id": "C", "name": "c", "region": "asia", "c": None}]
    lab, pred, obs, strata = assemble(st, "c", {"A": 10.0, "B": None, "C": 5.0}, sign=-1.0)
    assert lab == ["A a"] and pred == [10.0] and obs == [5.0] and strata == ["africa"]
