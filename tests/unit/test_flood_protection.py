"""Flood defences (product owner's decisions, 2026-10-16; loss_protocol 'flood_protection'): the protection line on the
loss–exceedance curve, the coverage of the European maps, the archive and check guards, and the protection map's
three readings (a level, no value, off the map)."""
from __future__ import annotations

from pathlib import Path

import pytest

from services.loss import engine, europe_check, protection, registry

CURVE = {10: 100.0, 100: 1000.0, 500: 5000.0}


def test_a_line_at_or_below_the_most_frequent_period_removes_nothing():
    assert protection.defended_eal(CURVE, 2) == pytest.approx(engine.eal(CURVE))
    assert protection.defended_eal(CURVE, 10) == pytest.approx(engine.eal(CURVE))


def test_damage_from_floods_more_frequent_than_the_line_is_set_to_zero():
    # line at 1-in-100: the tail beyond 1-in-500 plus the trapezoid between 1-in-500 and 1-in-100
    assert protection.defended_eal(CURVE, 100) == pytest.approx(0.002 * 5000 + 0.008 * (1000 + 5000) / 2)


def test_a_line_between_two_periods_reads_the_curve_on_its_straight_line():
    # 1-in-50 lies between 1-in-10 and 1-in-100: the loss there is read on the line through them (900)
    at_50 = 100 + (1000 - 100) * (0.02 - 0.1) / (0.01 - 0.1)
    assert at_50 == pytest.approx(900)
    assert protection.defended_eal(CURVE, 50) == pytest.approx(0.002 * 5000 + 0.008 * 3000 + 0.01 * (1000 + at_50) / 2)


def test_a_line_rarer_than_the_rarest_period_leaves_only_the_held_tail():
    assert protection.defended_eal(CURVE, 10000) == pytest.approx(0.0001 * 5000)


def test_higher_defences_never_raise_the_loss():
    got = [protection.defended_eal(CURVE, rp) for rp in (2, 10, 20, 50, 100, 153, 200, 500, 1000, 10000)]
    assert all(a >= b for a, b in zip(got, got[1:])) and got[0] == pytest.approx(engine.eal(CURVE))


def test_the_european_maps_serve_europe_less_russia_belarus_and_ukraine(monkeypatch):
    c = registry.coverage_countries("jrc_river_flood_europe")
    assert {"DE", "NL", "IT", "ES", "PL", "NO"} <= c and not ({"RU", "BY", "UA", "TR", "US"} & c)
    layers = {**registry.layers(), "x": {**registry.layer("jrc_river_flood_europe"), "coverage_countries": "the EU"}}
    monkeypatch.setattr(registry, "layers", lambda: layers)
    with pytest.raises(registry.RegistryError):
        registry.coverage_countries("x")


def test_a_replacement_serves_only_once_in_use_and_only_in_its_countries(monkeypatch):
    assert engine.replacement("flood", "DE") is None or registry.layer("jrc_river_flood_europe")["status"] == "in_use"
    L = {**registry.layers()}
    L["jrc_river_flood_europe"] = {**L["jrc_river_flood_europe"], "status": "in_use"}
    monkeypatch.setattr(registry, "layers", lambda: L)
    assert engine.replacement("flood", "DE") == "jrc_river_flood_europe"
    assert engine.replacement("flood", "US") is None and engine.replacement("flood", "TR") is None
    assert engine.replacement("storm", "DE") is None


def test_an_archive_member_that_would_land_outside_its_folder_is_refused():
    from scripts.fetch_jrc_flood_europe import unpack_refusal
    assert unpack_refusal(["floodProtection_v2019_paper3.tif", "sub/readme.txt"]) is None
    assert unpack_refusal(["../evil.py"]) and unpack_refusal(["/etc/passwd"]) and unpack_refusal(["C:/x.tif"])


def test_the_check_refuses_only_a_map_worse_beyond_sampling_noise():
    assert europe_check.verdict({"rho": [-0.03, 0.02], "auc": [-0.01, 0.04]})        # inside noise: not worse
    assert europe_check.verdict({"rho": [0.01, 0.05], "auc": [0.0, 0.02]})            # better
    assert not europe_check.verdict({"rho": [-0.08, -0.01], "auc": [-0.01, 0.03]})    # rank correlation worse
    assert not europe_check.verdict({"rho": [-0.01, 0.02], "auc": [-0.05, -0.002]})   # AUC worse


@pytest.mark.skipif(not Path(registry.ROOT / protection.layer()["file"]).exists(),
                    reason="the JRC protection map is not on this machine")
def test_the_protection_map_reads_a_level_no_value_or_off_the_map():
    got = protection.rows([(53.55, 9.99), (40.0, 5.0), (40.71, -74.0)])     # Hamburg, the open sea, New York
    assert [g["status"] for g in got] == ["sampled", "no_value", "outside_coverage"]
    assert got[0]["design_rp_years"] == 153.0 and got[1]["design_rp_years"] is None
