"""Reading a hazard between two maps by warming (services.loss.projection; the product owner's decisions of 2026-10-22
and 2026-10-23): a flood map's water depth is blended, a dry pixel's depth being none, and the pixel is wet where the
blend is above the source's dry level; a wind map's wind at each return period is blended. The central figure is the
member the source names, else the median of the members (the mean of the two middle ones when they are even)."""
from __future__ import annotations

import pytest

from services.loss.projection import blend, central

FLOOD = {"metric": "water_depth", "dry_below": 0.0, "use": {}}
WIND = {"metric": "max_sustained_wind_10min", "use": {}}


def _map(**depths):
    return {int(rp): {"status": "sampled", "cell_fraction": 1.0 if d > 0 else 0.0, "cell_mean": d} for rp, d in depths.items()}


def test_wet_maps_blend_their_depths():
    out = blend(_map(**{"100": 1.0}), _map(**{"100": 2.0}), 0.25, FLOOD)
    assert out[100] == {"status": "sampled", "cell_fraction": 1.0, "cell_mean": pytest.approx(1.25)}


def test_a_dry_map_is_depth_none_and_the_blend_is_wet_where_water_remains():
    out = blend(_map(**{"10": 0.0, "100": 0.0}), _map(**{"10": 0.0, "100": 2.0}), 0.1, FLOOD)
    assert out[10]["cell_fraction"] == 0.0 and out[10]["cell_mean"] == 0.0
    assert out[100]["cell_fraction"] == 1.0 and out[100]["cell_mean"] == pytest.approx(0.2)


def test_weight_zero_is_the_lower_map_and_one_the_upper():
    lo, hi = _map(**{"100": 0.5}), _map(**{"100": 1.5})
    assert blend(lo, hi, 0.0, FLOOD)[100]["cell_mean"] == 0.5 and blend(lo, hi, 1.0, FLOOD)[100]["cell_mean"] == 1.5


def test_a_wind_map_blends_the_wind_at_each_return_period_held_by_both():
    lo = {10: {"status": "sampled", "value": 30.0}, 100: {"status": "sampled", "value": 50.0}}
    hi = {100: {"status": "sampled", "value": 60.0}, 500: {"status": "sampled", "value": 70.0}}
    out = blend(lo, hi, 0.3, WIND)
    assert set(out) == {100} and out[100]["value"] == pytest.approx(53.0)


def _fig(eal, at100):
    return {"eal_eur": eal, "loss_at_rp": {"100": {"central": at100}}}


def test_an_odd_number_of_members_reads_the_middle_one():
    m = {"a": _fig(1.0, 10.0), "b": _fig(3.0, 30.0), "c": _fig(2.0, 20.0)}
    assert central(m, {"use": {}}) is m["c"]


def test_an_even_number_of_members_reads_the_mean_of_the_two_middle_ones():
    m = {"a": _fig(1.0, 10.0), "b": _fig(4.0, 40.0), "c": _fig(2.0, 20.0), "d": _fig(3.0, 30.0)}
    got = central(m, {"use": {}})
    assert got["eal_eur"] == pytest.approx(2.5) and got["loss_at_rp"]["100"]["central"] == pytest.approx(25.0)


def test_a_named_central_member_is_read_whatever_its_rank():
    m = {"p05": _fig(1.0, 10.0), "p50": _fig(9.0, 90.0), "p95": _fig(5.0, 50.0)}
    assert central(m, {"use": {"central_member": "p50"}}) is m["p50"]


def test_a_projected_run_samples_its_book_on_every_map_of_each_source_and_the_present_it_reads(monkeypatch):
    from services.loss import intensity
    calls = []
    monkeypatch.setattr(intensity, "sample_projection", lambda s, key, pts: calls.append(("maps", key, pts)) or {})
    monkeypatch.setattr(intensity, "sample", lambda s, key, pts: calls.append(("today", key, pts)) or {})
    assets = [{"latitude": 1.0, "longitude": 2.0}, {"latitude": None, "longitude": None}]
    intensity.prepare_book(None, assets, ["flood", "coastal_flood", "storm"], projected=True)
    assert ("maps", "aqueduct_river_flood", [(1.0, 2.0)]) in calls
    assert ("maps", "aqueduct_coastal_flood", [(1.0, 2.0)]) in calls
    assert ("maps", "storm_cc_wind", [(1.0, 2.0)]) in calls and ("today", "storm_v4_wind", [(1.0, 2.0)]) in calls
