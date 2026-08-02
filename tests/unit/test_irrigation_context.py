"""Irrigation is an honest water-management CONTEXT flag — never a fabricated euro modifier."""
from api.routers.supply import _norm_irrigation, irrigation_context


def test_irrigated_with_water_hazard_flags_upper_bound():
    c = irrigation_context("irrigated", ["drought", "flood"])
    assert c["status"] == "irrigated"
    assert "drought" in c["buffers"]
    assert "upper bound" in c["note"].lower()


def test_rain_fed_is_fully_exposed():
    c = irrigation_context("rain_fed", ["soil_water"])
    assert c["status"] == "rain_fed" and c["buffers"] == []


def test_undeclared_is_none():
    assert irrigation_context(None, ["drought"]) is None


def test_irrigated_without_a_water_hazard_has_no_buffer():
    c = irrigation_context("irrigated", ["flood", "storm"])
    assert c["status"] == "irrigated" and c["buffers"] == []


def test_norm_rejects_unknown_and_normalises():
    assert _norm_irrigation("drip???") is None      # unrecognised → undeclared, never guessed
    assert _norm_irrigation("Irrigated") == "irrigated"
    assert _norm_irrigation(None) is None
